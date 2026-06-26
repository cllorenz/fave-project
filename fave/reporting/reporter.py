#!/usr/bin/env python3

from __future__ import annotations

import time
import threading

from typing import Any, Dict, List, Optional, Tuple

from util.ip6np_util import bitvector_to_field_value
from netplumber.mapping import FIELD_SIZES, Mapping
from netplumber.vector import Vector, get_field_from_vector
#from enum import Enum

#Log = Enum('Log', ['Compliance', 'Anomalies'])
class Log:
    Compliance = 0
    Anomalies = 1


def _parse_log_line(tokens: List[str]) -> Optional[Tuple[Any, ...]]:
    """ Turn a tokenised NetPlumber log line into an event tuple, or None.

    The positional indices mirror NetPlumber's DefaultComplianceLogger /
    DefaultAnomalyLogger output format. Extracted from Reporter.run() so the
    (fragile, position-dependent) parse can be tested without the log-tailing
    thread; run() just appends whatever this returns.
    """
    if "DefaultComplianceLogger" in tokens:
        negated = 1 if tokens[16] == '!' else 0
        from_ = tokens[16 + negated]
        to_ = tokens[18 + negated]
        cond = tokens[20 + negated] if len(tokens) >= 21 + negated else None
        return (Log.Compliance, negated == 1, from_, to_, cond)

    if "DefaultAnomalyLogger" in tokens:
        np_rid = int(tokens[14].rstrip(')'))
        return (Log.Anomalies, np_rid)

    return None


def _parse_cond(cond: str, mapping: Mapping) -> List[Tuple[str, str]]:
    vec = Vector.from_vector_str(cond)

    result = []
    for name in mapping:
        field = get_field_from_vector(mapping, vec, name)
        if field != 'x' * FIELD_SIZES[name]:
            value = bitvector_to_field_value(field, name)
            assert value is not None  # a non-all-x field has a concrete value
            result.append((name, value))
    return result


class Reporter(threading.Thread):
    def __init__(self, fave: Any, np_log: str) -> None:
        super(Reporter, self).__init__()

        self.events: List[Any] = []
        self.last_compliance = 0
        self.last_anomalies = 0
        self.stop_reporter = False
        self.fave = fave
        self.np_log = open(np_log, 'r')


    def dump_report(self, dump: str) -> None:
        # name : (idx, sid, model)
        id_to_generator = {g[1] : n for n, g in list(self.fave.verification_engine.generators.items())}

        # name : (idx, pid, model)
        id_to_probe = {g[1] : n for n, g in list(self.fave.verification_engine.probes.items())}

        report = [
            "# Report",
            "<introductionary text>"
        ]

        cur_event = len(self.events)

        # fetch recent compliance and anomaly events
        compliance_events = [entry for entry in self.events[self.last_compliance:cur_event] if entry[0] == Log.Compliance]

        anomaly_events = [entry for entry in self.events[self.last_anomalies:cur_event] if entry[0] == Log.Anomalies]

        # generate report
        report.append("\n## Compliance Check")
        if compliance_events:
            report.append("The following compliance violations have been found:\n")
            for event in compliance_events:
                _, negated, from_, to_, cond = event
                report.append("- `{}` {} `{}`{}".format(
                    id_to_generator[int(from_)],
                    "reaches" if not negated else "does not reach",
                    id_to_probe[int(to_)],
                    " with \n    - " + '\n    - '.join(
                        ['='.join(fv) for fv in _parse_cond(cond, self.fave.verification_engine.mapping)]
                    ) if cond else ""
                ))
        else:
            report.append("No compliance violations have been found.")

        report.append("\n## Anomaly Check")
        if anomaly_events:
            report.append("The following anomalies have been found:\n")

            inv_rids = {}
            for fave_rid, np_rids in list(self.fave.verification_engine.rule_ids.items()):
                for np_rid in np_rids:
                    inv_rids[np_rid] = fave_rid

            shadowed_rids: Dict[Any, List[Any]] = {}
            for _, np_rid in anomaly_events:
                fave_rid = inv_rids[np_rid]
                shadowed_rids.setdefault(fave_rid, [])
                shadowed_rids[fave_rid].append(np_rid)

            id_to_table = {
                self.fave.verification_engine.tables[k]:k for k in self.fave.verification_engine.tables
            }

            for fave_rid, np_rids in list(shadowed_rids.items()):
                if set(np_rids) == set(self.fave.verification_engine.rule_ids[fave_rid]):
                    table_id = fave_rid >> 32
                    model_name = '.'.join(id_to_table[table_id].split('.')[:-1])
                    rule_id = (fave_rid & 0xffffffff) >> 12
                    rules = self.fave.models[model_name].tables[id_to_table[table_id]]
                    rule = [r for r in rules if r.idx == rule_id and r.raw_line is not None]

                    if not rule:
                        continue

                    report.append("- shadowed rule at line {}:\n\n    `{}`".format(rule[0].raw_line_no, rule[0].raw_line))

        else:
            report.append("No anomalies have been found.")

        with open(dump, 'w') as of:
            of.write('\n'.join(report) + '\n')


    def mark_compliance(self) -> None:
        self.last_compliance = len(self.events)


    def mark_anomalies(self) -> None:
        self.last_anomalies = len(self.events)


    def stop(self) -> None:
        self.stop_reporter = True


    def run(self) -> None:
        while not self.stop_reporter:
            raw_line = self.np_log.readline()

            if not raw_line:
                time.sleep(0.001)
                continue

            # parse line
            tokens = raw_line.rstrip().split()

            # check if reportable
            line = _parse_log_line(tokens)
            if line is None:
                continue

            # add to event buffer
            self.events.append(line)

        self.np_log.close()
