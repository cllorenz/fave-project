#!/usr/bin/env python3

from __future__ import annotations

import os
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

            # A field can also be PARTIALLY determined -- some bits pinned, the
            # rest free -- which has no single value to print. Every condition
            # the suite could produce before was exact (a service names one
            # port), so this used to assert; a COMPLEMENT condition
            # ("anything but port 80", bench/reach_csv_to_checks.py
            # --complement) is partial by construction and killed the whole
            # report task. Printing the pattern is less readable than a number
            # and is the truth about the flow -- a witness nobody can see is
            # worse than an ugly one. See test/test_reporter_partial_condition.py.
            result.append((name, value if value is not None else field))
    return result


def _backend_checks_anomalies(fave: Any) -> bool:
    """ Whether the aggregator's backend implements anomaly detection.

    Read off the SERVICE rather than probed on the engine: `Ad6Adapter` has a
    `check_anomalies` that raises NotImplementedError, so `hasattr` would say
    yes and the report would claim a clean anomaly verdict for a step the
    benchmark deliberately skipped. Defaults to True so the NetPlumber path and
    every existing caller are unaffected. """
    from aggregator.aggregator_service import BACKENDS_WITH_ANOMALIES
    backend = getattr(fave, 'backend', None)
    return backend is None or backend in BACKENDS_WITH_ANOMALIES


def _render_cond(cond: Any) -> List[str]:
    """ An engine-reported condition as "name=value" strings.

    An engine hands back whatever `check_compliance` was given: `Ad6Adapter`
    normalises to `RuleField.to_json()` dicts, `APKeepAdapter` echoes the
    `RuleField` objects the aggregator built. Both shapes render; anything else
    prints as itself, because a report is a presentation artifact and an
    unfamiliar shape should not abort the run that produced the verdict. """
    if not cond:
        return []
    if isinstance(cond, str):
        return [cond]
    rendered = []
    for field in cond:
        if isinstance(field, dict) and 'name' in field:
            rendered.append("%s=%s" % (field['name'], field.get('value')))
        elif getattr(field, 'name', None) is not None:
            rendered.append("%s=%s" % (field.name, getattr(field, 'value', None)))
        else:
            rendered.append(str(field))
    return rendered


class Reporter(threading.Thread):
    def __init__(self, fave: Any, np_log: Optional[str]) -> None:
        super(Reporter, self).__init__()

        self.events: List[Any] = []
        self.last_compliance = 0
        self.last_anomalies = 0
        self.stop_reporter = False
        self.fave = fave
        self.np_log_path: Optional[str] = np_log
        # AD6_PLAN.md §9.28: the log tail is OPTIONAL. It exists to read
        # net_plumber's own verdict out of its stdout; an engine that reports
        # its own results (ad6, APKeep) has no such log, and this used to
        # `open()` unconditionally.
        #
        # A STALE log is the reason `np_log=None` is a real mode rather than
        # just tolerated absence: this opens at offset 0, so a leftover
        # /dev/shm/np/stdout.log from an earlier NetPlumber run would be
        # replayed in full as THIS run's compliance events. Silently attributing
        # one engine's verdict to another is exactly the class of error
        # §9.23 is a post-mortem of.
        self.np_log = None
        if np_log is not None:
            try:
                self.np_log = open(np_log, 'r')
            except (IOError, OSError):
                # Absent is not fatal: nothing to tail, and `dump_report` falls
                # back to whatever the engine reports for itself.
                self.np_log = None
        # Bytes of np_log this tailer has actually consumed; compared against
        # the file size by `drain()`.
        self.consumed = self.np_log.tell() if self.np_log is not None else 0


    def drain(self, poll: float = 0.01) -> None:
        """ Block until this tailer has consumed everything net_plumber wrote.

        `dump_report` renders `self.events`, which `run()` parses out of
        net_plumber's log on a separate thread. Rendering before that thread has
        caught up would yield a PARTIAL verdict, so the ordering has to be
        forced rather than assumed.

        This closes a LATENT race, not an observed failure: on the measured
        wl_i2 run the tailer was already at EOF (this returned in <1 ms) because
        the 339 s model build gave it ample slack. A faster engine, a larger
        log, or a slower parse would remove that slack, and nothing else in the
        pipeline orders the two.

        Terminating ONLY because the caller has already passed the request
        barrier for the compliance/anomaly check, and those RPCs are synchronous
        down to net_plumber (`jsonrpc._asend_recv`): the writer has stopped and
        the file has a final size, so this converges. Do not call it while the
        engine is still producing events.

        Like the barrier itself, it waits on evidence (bytes remaining) rather
        than on a clock -- there is no timeout.
        """
        if self.np_log is None or self.np_log_path is None:
            return              # nothing is being tailed

        path = self.np_log_path
        while not self.stop_reporter:
            try:
                size = os.path.getsize(path)
            except OSError:
                return
            if self.consumed >= size:
                return
            time.sleep(poll)


    def _engine_violations(self) -> Optional[List[str]]:
        """ The rendered violation lines an engine reports for ITSELF, or None
        if it reports none of its own and the log tail is the source of truth.

        AD6_PLAN.md §9.28. `get_compliance_results()` returns name-based
        `(source, probe, must_reach, cond)` tuples -- no net_plumber node ids
        and no header-space vector, so none of the id/mapping resolution below
        applies (and `NetPlumberAdapter` has no such method at all, which is
        what selects between the two paths).

        `must_reach` is the polarity of the CHECK, and every tuple here is a
        VIOLATION of it: a must-reach check that was violated reads "does not
        reach", and a must-not-reach check that was violated reads "reaches".
        """
        results = getattr(self.fave.verification_engine, 'get_compliance_results', None)
        if not callable(results):
            return None

        lines = []
        for source, probe, must_reach, cond in results():
            lines.append("- `{}` {} `{}`{}".format(
                source,
                "does not reach" if must_reach else "reaches",
                probe,
                " with \n    - " + '\n    - '.join(_render_cond(cond)) if cond else ""
            ))
        return lines


    def dump_report(self, dump: str) -> None:
        report = [
            "# Report",
            "<introductionary text>"
        ]

        cur_event = len(self.events)

        # fetch recent compliance and anomaly events
        compliance_events = [entry for entry in self.events[self.last_compliance:cur_event] if entry[0] == Log.Compliance]

        anomaly_events = [entry for entry in self.events[self.last_anomalies:cur_event] if entry[0] == Log.Anomalies]

        engine_violations = self._engine_violations()

        # generate report
        report.append("\n## Compliance Check")
        if engine_violations is not None:
            # The engine computed its own verdict; the log tail is not
            # consulted at all, so a stale one cannot leak into it.
            if engine_violations:
                report.append("The following compliance violations have been found:\n")
                report.extend(engine_violations)
            else:
                report.append("No compliance violations have been found.")
        elif compliance_events:
            # name : (idx, sid, model)
            id_to_generator = {g[1] : n for n, g in list(self.fave.verification_engine.generators.items())}

            # name : (idx, pid, model)
            id_to_probe = {g[1] : n for n, g in list(self.fave.verification_engine.probes.items())}

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
        if not _backend_checks_anomalies(self.fave):
            # AD6_PLAN.md §9.28: the benchmark SKIPS this step for an engine
            # that does not implement it, so "none found" would be a verdict
            # nobody computed. Say which it was.
            report.append(
                "Not checked: the %s backend does not implement anomaly "
                "detection." % getattr(self.fave, 'backend', 'selected'))
        elif anomaly_events:
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
        if self.np_log is None:
            return              # no log to tail; the engine reports itself

        while not self.stop_reporter:
            raw_line = self.np_log.readline()

            if not raw_line:
                time.sleep(0.001)
                continue

            self.consumed = self.np_log.tell()

            # parse line
            tokens = raw_line.rstrip().split()

            # check if reportable
            line = _parse_log_line(tokens)
            if line is None:
                continue

            # add to event buffer
            self.events.append(line)

        self.np_log.close()
