#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" wl_cloud BDD-APKeep build measurement, under the APKEEP_NDD_EVAL.md 2.6b
    protocol (CLOUD_BENCH_PLAN.md 1.7.3).

WHY THIS EXISTS. 1.7.3 recorded "the BDD engine did not complete the build
within 40 minutes" and left NOTHING behind -- no profiler trace, no ap_num
trajectory, no result file, and no written stopping rule. That is an unrecorded
observation, not a measurement: a build killed at an operator-chosen moment has
not been shown not to finish, and with no trace there is not even a tail rate
from which to derive a completion LOWER BOUND. This driver produces what 2.6b's
faithful runs have and 1.7.3 does not.

THE PROTOCOL, and what each piece is for:

  * A DECLARED deadline (--deadline-s, default 4 h), recorded in the result and
    enforced by a watchdog thread. The build is one synchronous JPype call that
    Python cannot interrupt, so the watchdog does not try: it writes the partial
    result and hard-exits. `status` is then "deadline" -- never "stopped", and
    never an operator kill, which is the whole point.

  * A STREAMING trace. APKEEP_BUILD_PROFILE makes the Java-side sampler
    (apkeep.utils.BuildProfiler) append one flushed JSON line per interval, so
    a run that is killed -- by the deadline, by the OOM killer, by anything --
    still leaves a complete growth curve behind. The adapter issues exactly ONE
    `lib.run(all_rules)` call, so the profiler starts once and the trace is
    never truncated mid-build (BuildProfiler opens with append=false).

  * DERIVED TRENDS, written as the run progresses rather than reconstructed
    afterwards (--status-every-s, default 60). Each tick appends one line to
    <out>.status.jsonl and rewrites <out>.status.txt and the partial <out>,
    each atomically. So at any instant, including after a SIGKILL, the latest
    derived state is on disk AND its whole history is too. The derived fields
    are the ones 2.6b needs: tail rule-rate, AP-per-rule slope over several
    windows, the extrapolated ap_num, and the completion lower bound.

  * NO JVM CALLS OFF THE BUILD THREAD. The watchdog and status threads read the
    profiler's JSONL and nothing else. Touching a concurrently-mutated APKeeper
    from a second thread is how you get a crash that looks like a finding.

READING THE RESULT. `status` is one of:
    completed  -- the build (and query) finished inside the deadline. A real
                  upper bound; report the wall time.
    deadline   -- the declared deadline hit. NOT evidence of non-termination;
                  report `bound_h` (a lower bound at the tail rate) and say so.
    error      -- something threw; `error` carries it. Not a cost result.

Usage (from fave/, PYTHONPATH=., venv active, apkeep jar built):
  FAVE_JVM_XMX=8g PYTHONPATH=. python3 bench/cloud_bdd_measure.py \
      --engine bdd --deadline-s 14400 --out bench/wl_cloud/eval/bdd_build.json
"""

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
import time


_PREFIX = "bench/wl_cloud"
_INPUTS = ("topology.json", "routes.json", "policies.json", "sources.json",
           "mapping.json")

#: Windows (seconds) the status tick reports rule-rate and AP-slope over. Short
#: windows are noisy -- APKEEP_NDD_EVAL.md 2.6b found the faithful-stanford AP
#: slope ranging -0.52 to +7.92 AP/rule depending on window -- so several are
#: emitted and a claim may only rest on one that is stable across them.
_WINDOWS = (300, 900, 1800, 3600)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_atomic(path, text):
    """ Write via <path>.tmp + rename, so a reader (or a kill) never sees a
    half-written status file. """
    tmp = "%s.tmp" % path
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _read_samples(profile_path):
    """ Every complete JSONL sample written so far. A partial trailing line is
    possible in principle (BuildProfiler flushes whole lines, but a reader can
    still race a write), so it is skipped rather than fatal. """
    out = []
    try:
        with open(profile_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except IOError:
        pass
    return out


def _trend(samples):
    """ The derived view 2.6b reports: where the build is, how fast it is still
    going, and what that implies. Computed over several windows because a single
    window is not a trend.

    `bound_h` is a completion LOWER BOUND *at the observed tail rate* -- it is a
    true lower bound only while that rate is falling, which `rate_falling` says.
    """
    if not samples:
        return {"samples": 0}
    last = samples[-1]
    total = last.get("total_rules") or 0
    done = last.get("rules") or 0
    left = max(total - done, 0)
    t = {
        "samples": len(samples),
        "elapsed_s": round((last.get("ms") or 0) / 1000.0, 1),
        "rules": done,
        "total_rules": total,
        "pct_rules": round(100.0 * done / total, 2) if total else None,
        "ap_num": last.get("ap_num"),
        "elements": last.get("elements"),
        "ppm_entries": last.get("ppm_entries"),
        "bdd_mem_mib": round((last.get("bdd_mem") or 0) / 2**20, 1),
        "encode_ms": last.get("encode_ms"),
        "insert_ms": last.get("insert_ms"),
        "ppm_ms": last.get("ppm_ms"),
        "merge_ms": last.get("merge_ms"),
        "split_count": last.get("split_count"),
        "windows": {},
    }
    for win in _WINDOWS:
        head = [s for s in samples if (s.get("ms") or 0) >= (last.get("ms") or 0) - win * 1000]
        if len(head) < 2:
            continue
        d_rules = (head[-1].get("rules") or 0) - (head[0].get("rules") or 0)
        d_s = ((head[-1].get("ms") or 0) - (head[0].get("ms") or 0)) / 1000.0
        if d_s <= 0:
            continue
        a0, a1 = head[0].get("ap_num"), head[-1].get("ap_num")
        d_ap = (a1 - a0) if (a0 is not None and a1 is not None) else None
        t["windows"]["%ds" % win] = {
            "d_rules": d_rules,
            "span_s": round(d_s, 1),
            "rate_per_s": round(d_rules / d_s, 4),
            "d_ap": d_ap,
            "ap_per_rule": round(d_ap / d_rules, 3) if (d_ap is not None and d_rules) else None,
            # True once the run is longer than the window; until then this row
            # covers the WHOLE run and is not a tail measurement at all.
            "is_tail": (last.get("ms") or 0) > win * 1000,
        }
    w = t["windows"]
    # Prefer the LONGEST window that is actually a tail -- a window still
    # covering the whole run averages in the fast opening phase and understates
    # the bound by orders of magnitude while the build is already crawling.
    tails = [w["%ds" % win] for win in sorted(_WINDOWS, reverse=True)
             if w.get("%ds" % win) and w["%ds" % win].get("is_tail")]
    tail = tails[0] if tails else (w.get("900s") or w.get("300s"))
    if tail and tail["rate_per_s"] > 0 and left:
        t["rules_left"] = left
        t["bound_h"] = round(left / tail["rate_per_s"] / 3600.0, 2)
        t["bound_basis"] = "tail rate %.4f rules/s over the window it is keyed to" \
                           % tail["rate_per_s"]
        if tail["ap_per_rule"]:
            t["ap_num_projected"] = int((t["ap_num"] or 0) + tail["ap_per_rule"] * left)
        wide = w.get("3600s") or w.get("1800s")
        # Comparing two windows that cover the SAME samples says nothing -- early
        # in a run every window spans the whole of it. Require the wide window to
        # actually reach further back before reading a direction off the pair.
        if (wide and wide["rate_per_s"] > 0
                and wide["span_s"] > tail["span_s"] * 1.5):
            # Falling tail rate => bound_h is a true lower bound. Flat/rising =>
            # it holds only while the rate holds (2.6b: i2 vs stanford).
            t["rate_falling"] = tail["rate_per_s"] < wide["rate_per_s"] * 0.95
    elif left == 0:
        t["rules_left"] = 0
    return t


def _status_text(result, trend):
    lines = [
        "wl_cloud BDD build -- live status (APKEEP_NDD_EVAL.md 2.6b protocol)",
        "engine=%s  deadline=%ss  started=%s" % (
            result.get("engine"), result.get("deadline_s"), result.get("started_utc")),
        "",
        "elapsed        %.1f s (%.2f h)" % (trend.get("elapsed_s") or 0,
                                            (trend.get("elapsed_s") or 0) / 3600.0),
        "rules applied  %s / %s  (%s %%)" % (trend.get("rules"), trend.get("total_rules"),
                                             trend.get("pct_rules")),
        "ap_num         %s" % trend.get("ap_num"),
        "elements       %s   ppm_entries %s   split_count %s" % (
            trend.get("elements"), trend.get("ppm_entries"), trend.get("split_count")),
        "bdd table      %s MiB" % trend.get("bdd_mem_mib"),
        "timers (ms)    encode=%s insert=%s ppm=%s merge=%s" % (
            trend.get("encode_ms"), trend.get("insert_ms"),
            trend.get("ppm_ms"), trend.get("merge_ms")),
        "",
        "window    d_rules   rate/s   d_ap   AP/rule   tail?",
    ]
    for win in _WINDOWS:
        d = trend.get("windows", {}).get("%ds" % win)
        if d:
            lines.append("%-8s  %7s  %7s  %5s  %8s   %s" % (
                "%ds" % win, d["d_rules"], d["rate_per_s"], d["d_ap"],
                d["ap_per_rule"], "yes" if d.get("is_tail") else "WHOLE RUN"))
    if trend.get("bound_h") is not None:
        if "rate_falling" not in trend:
            direction = "windows still overlap -> no direction readable yet"
        elif trend["rate_falling"]:
            direction = "rate still falling -> true lower bound"
        else:
            direction = "rate flat/rising -> holds only while that rate holds"
        lines += [
            "",
            "rules left     %s" % trend.get("rules_left"),
            "COMPLETION     >= %.2f h at the tail rate (%s)" % (
                trend["bound_h"], direction),
            "ap_num proj.   %s (extrapolation, not a measurement)" % trend.get("ap_num_projected"),
        ]
    return "\n".join(lines) + "\n"


def _dump(result, trend, out_path, status_jsonl, status_txt):
    """ One durable snapshot: the partial result, one appended history line, and
    the human-readable view. Called on every tick, on deadline and at the end. """
    snap = dict(result)
    snap["trend"] = trend
    if out_path:
        _write_atomic(out_path, json.dumps(snap, indent=2) + "\n")
    if status_jsonl:
        with open(status_jsonl, "a") as fh:
            fh.write(json.dumps({"t": time.time(), "status": result.get("status"),
                                 **trend}, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    if status_txt:
        _write_atomic(status_txt, _status_text(snap, trend))


def measure(args):
    from apkeep.adapter import APKeepAdapter
    from util.in_process_driver import InProcessFaVe

    profile = args.profile or (args.out + ".profile.jsonl" if args.out else None)
    status_jsonl = args.out + ".status.jsonl" if args.out else None
    status_txt = args.out + ".status.txt" if args.out else None
    if profile:
        os.environ["APKEEP_BUILD_PROFILE"] = profile
        os.environ.setdefault("APKEEP_BUILD_PROFILE_MS", str(args.profile_ms))

    # The oracle-phase and matrix-phase models share bench/wl_cloud/*.json and
    # whichever ran last wins, so measuring without regenerating can silently
    # size a different network (test_apkeep_cloud_differential does the same).
    if not args.no_regen:
        regen = subprocess.run(
            ["bash", "test/gen_wl_cloud_inputs.sh"], cwd=os.getcwd(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHON=sys.executable), timeout=900)
        if regen.returncode != 0:
            raise SystemExit("could not regenerate wl_cloud inputs:\n%s"
                             % regen.stdout.decode()[-3000:])

    result = {
        "bench": "wl_cloud",
        "engine": args.engine,
        "deadline_s": args.deadline_s,
        "status": "starting",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "xmx": os.environ.get("FAVE_JVM_XMX"),
        "profile": profile,
        "regenerated_inputs": not args.no_regen,
        "inputs_sha256": {f: _sha256(os.path.join(_PREFIX, f)) for f in _INPUTS},
        "jar_sha256": None,
    }
    # Pin the engine binary the same way lib_apkeep resolves it, so the result
    # says WHICH jar produced it (both engines share the process-global JVM).
    from apkeep import lib_apkeep as _lib_apkeep
    for key, jar in (("jar_sha256", getattr(_lib_apkeep, "_APKEEP_JAR", None)),
                     ("ndd_jar_sha256", getattr(_lib_apkeep, "_NDD_JAR", None))):
        if jar and os.path.isfile(jar):
            result[key] = _sha256(jar)

    stop_threads = threading.Event()
    wall0 = time.time()

    def _tick():
        """ Periodic durable dump. Reads ONLY the profiler's JSONL -- never the
        JVM -- because the build thread owns every APKeep structure. """
        while not stop_threads.wait(args.status_every_s):
            trend = _trend(_read_samples(profile)) if profile else {"samples": 0}
            _dump(result, trend, args.out, status_jsonl, status_txt)
            sys.stderr.write(
                "[%6.1f min] rules=%s/%s ap_num=%s bound>=%sh\n" % (
                    (time.time() - wall0) / 60.0, trend.get("rules"),
                    trend.get("total_rules"), trend.get("ap_num"),
                    trend.get("bound_h")))
            sys.stderr.flush()

    def _watchdog():
        """ The DECLARED deadline. The build is one synchronous JPype call, so
        there is nothing to interrupt politely: dump and hard-exit. os._exit
        skips JVM shutdown deliberately -- the trace is already on disk, and a
        clean shutdown here would only risk hanging on the build thread. """
        if stop_threads.wait(args.deadline_s):
            return
        result["status"] = "deadline"
        result["wall_s"] = round(time.time() - wall0, 3)
        trend = _trend(_read_samples(profile)) if profile else {"samples": 0}
        _dump(result, trend, args.out, status_jsonl, status_txt)
        sys.stderr.write("DEADLINE %ss reached; partial result written to %s\n"
                         % (args.deadline_s, args.out))
        sys.stderr.flush()
        os._exit(2)

    for fn in (_tick, _watchdog):
        th = threading.Thread(target=fn, name=fn.__name__, daemon=True)
        th.start()

    log = logging.getLogger("cloud_bdd")
    log.setLevel(logging.WARNING)
    mapping = json.load(open(os.path.join(_PREFIX, "mapping.json")))
    eng = APKeepAdapter(log, mapping=mapping, engine=args.engine)

    try:
        with InProcessFaVe(eng) as fave:
            t_replay = time.time()
            fave.replay(_PREFIX)
            result["replay_s"] = round(time.time() - t_replay, 3)
            sources = sorted(eng._generators)
            probes = sorted(eng._probes)
            result["sources"] = len(sources)
            result["probes"] = len(probes)
            result["status"] = "building"

            t_build = time.time()
            eng.single_universe()          # forces _build() -> the BDD/AP build
            result["build_s"] = round(time.time() - t_build, 3)
            # BDD-only introspection: ap_num IS the atomic-predicate partition
            # whose growth is the thing under measurement. lib_ndd has no such
            # global partition (that is the point), so an --engine ndd control
            # run simply records nothing here rather than failing.
            if hasattr(eng._lib, "ap_num"):
                result["ap_num"] = int(eng._lib.ap_num())
            if hasattr(eng._lib, "element_metrics"):
                result["element_metrics"] = dict(eng._lib.element_metrics())
            result["status"] = "querying"
            _dump(result, _trend(_read_samples(profile)) if profile else {},
                  args.out, status_jsonl, status_txt)

            t_query = time.time()
            fave.check_compliance({p: [[s, False, []] for s in sources] for p in probes})
            result["query_s"] = round(time.time() - t_query, 3)

        not_reach = {(s, p) for (s, p, _m, _c) in eng.get_compliance_results()}
        result["reachable_pairs"] = sum(
            1 for p in probes for s in sources if (s, p) not in not_reach)
        result["status"] = "completed"
    except BaseException as exc:                     # noqa: BLE001 - recorded, not swallowed
        result["status"] = "error"
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        raise
    finally:
        stop_threads.set()
        result["wall_s"] = round(time.time() - wall0, 3)
        trend = _trend(_read_samples(profile)) if profile else {"samples": 0}
        _dump(result, trend, args.out, status_jsonl, status_txt)
        print(json.dumps({k: v for k, v in result.items() if k != "inputs_sha256"},
                         indent=2))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--engine", default="bdd", choices=("bdd", "ndd"))
    p.add_argument("--deadline-s", type=int, default=14400,
                   help="DECLARED deadline in seconds (default 14400 = 4 h)")
    p.add_argument("--status-every-s", type=int, default=60,
                   help="how often to dump a durable status snapshot")
    p.add_argument("--profile-ms", type=int, default=30000,
                   help="APKEEP_BUILD_PROFILE_MS sampling interval")
    p.add_argument("--profile", help="profiler JSONL path (default <out>.profile.jsonl)")
    p.add_argument("--no-regen", action="store_true",
                   help="use bench/wl_cloud/*.json as they are on disk")
    p.add_argument("--out", required=True, help="result JSON (also <out>.status.{jsonl,txt})")
    args = p.parse_args(argv)
    measure(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
