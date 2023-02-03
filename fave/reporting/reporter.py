#!/usr/bin/env python3

import time
import threading

from util.ip6np_util import bitvector_to_field_value
from netplumber.mapping import FIELD_SIZES
from netplumber.vector import Vector, get_field_from_vector
#from enum import Enum

#Log = Enum('Log', ['Compliance', 'Anomalies'])
class Log:
    Compliance = 0
    Anomalies = 1


def _parse_cond(cond, mapping):
    vec = Vector.from_vector_str(cond)

    return [
        (
            name,
            bitvector_to_field_value(
                get_field_from_vector(mapping, vec, name),
                name
            )
        ) for name in mapping if get_field_from_vector(
            mapping, vec, name
        ) != 'x' * FIELD_SIZES[name]
    ]


class Reporter(threading.Thread):
    def __init__(self, fave, np_log):
        super(Reporter, self).__init__()

        self.events = []
        self.last_compliance = 0
        self.last_anomalies = 0
        self.stop_reporter = False
        self.fave = fave
        self.np_log = open(np_log, 'r')


    def dump_report(self, dump):
        # name : (idx, sid, model)
        id_to_generator = {g[1] : n for n, g in list(self.fave.net_plumber.generators.items())}

        # name : (idx, pid, model)
        id_to_probe = {g[1] : n for n, g in list(self.fave.net_plumber.probes.items())}

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
        report.append("The following compliance violations have been found:\n")

        for event in compliance_events:
            _, from_, to_, cond = event
            report.append("- `{} -> {}{}`".format(
                id_to_generator[int(from_)],
                id_to_probe[int(to_)],
                " && " + ','.join(
                    ['='.join(fv) for fv in _parse_cond(cond, self.fave.net_plumber.mapping)]
                ) if cond else ""
            ))

        report.append("\n## Anomaly Check")
        report.append("The following anomalies have been found:\n")


        inv_rids = {}
        for fave_rid, np_rids in list(self.fave.net_plumber.rule_ids.items()):
            for np_rid in np_rids:
                inv_rids[np_rid] = fave_rid

        shadowed_rids = {}
        for np_rid in anomaly_events:
            fave_rid = inv_rids[np_rid]
            shadowed_rids.setdefault(fave_rid, [])
            shadowed_rids[fave_rid].append(np_rid)

        for fave_rid, np_rids in list(shadowed_rids.items()):
            if set(np_rids) == set(self.fave.net_plumber.rule_ids[fave_rid]):
                report.append("- {}".format(fave_rid))

        with open(dump, 'w') as of:
            of.write('\n'.join(report) + '\n')


    def mark_compliance(self):
        self.last_compliance = len(self.events)


    def mark_anomalies(self):
        self.last_anomalies = len(self.events)


    def stop(self):
        self.stop_reporter = True


    def run(self):
        while not self.stop_reporter:
            raw_line = self.np_log.readline()

            if not raw_line:
                time.sleep(0.001)
                continue

            # parse line
            tokens = raw_line.rstrip().split()

            # check if reportable
            if "DefaultComplianceLogger" in tokens:
                negated = 1 if tokens[16] == '!' else 0
                from_ = tokens[16 + negated]
                to_ = tokens[18 + negated]
                cond = tokens[20 + negated] if len(tokens) >= 21 + negated else None

                line = (Log.Compliance, from_, to_, cond)

            elif "DefaultAnomalyLogger" in tokens:
                np_rid = tokens[13]

                line = (Log.Anomalies, np_rid)
            else:
                continue

            # add to event buffer
            self.events.append(line)

        self.np_log.close()
