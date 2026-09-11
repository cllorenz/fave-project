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

""" AD6_PLAN.md §5.5 C1/C2: wl_i2 (Internet2) plain-mode differential +
tractability measurement -- the i2 counterpart to `bench/ad6_faithful_measure.py`
(wl_stanford's own B3 script), same instrumentation (instantiate/DIMACS-build/
solve split, CNF clause count, peak RSS), but PLAIN mode (faithful_vlan=False)
and against i2's full 77,841-route model directly (no router-subsetting tool
exists for i2, unlike Stanford's induced N=2/3/5 slices -- see AD6_PLAN.md §5.5).

WORKLOAD SCOPE -- READ BEFORE COMPARING THESE NUMBERS WITH ANOTHER ENGINE'S
(AD6_PLAN.md §5.5, WORKLOAD-PARITY FINDING 2026-09-09). This script measures
dst-IP-ONLY reachability, NOT the workload NetPlumber and the faithful NDD run
answer on the same model. An earlier version of this docstring claimed "i2's
out-tables are a clean dst-IP FIB ... no VLAN modelling needed per §5.5's own C3
gate"; that is right about the MATCH side and wrong about the ACTION side.
`bench/wl_i2/i2-json/routes.json` holds 390 `in.X` rules that match `vlan=N` and
nothing else (VLAN admission) plus 77,451 `out.X` rules that match `ipv4_dst` and
carry TWO actions -- e.g. `["rw=vlan:10", "fd=out.atla.120030"]`, the dst FIB AND
a per-route egress-VLAN rewrite. NetPlumber translates every one of those
rewrites (`netplumber/adapter.py:452-501`, no collapse flag on that path) and
`test/test_apkeep_ndd_fwd.py:166` runs i2 with faithful=True. ad6 drops both
halves, and NOT only because of the flag below: `fave/ad6/adapter.py` has no
`_capture_out_rewrite` at all (`apkeep/adapter.py:470` does), so the egress
rewrites are lost in EITHER mode, and the vlan-only admission rules never become
routes (`_translate_fwd_rule` returns early at `fave/ad6/adapter.py:326` because
`dst is None`). Numbers from this script are therefore sound for comparing ad6
against ad6 -- e.g. the SAT-backend comparison, which used one identical encoding
throughout -- but must not be placed beside a NetPlumber or APKeep/NDD i2 figure
without that qualifier. Closing the gap is §5.5's C4.

C1 is the differential: does ad6's plain-mode reachability match
`bench/wl_i2/reachable.json` (the SAME oracle test_apkeep_i2.py validates
FaVe+APKeep against -- full mesh, 72/72 pairs reachable)? C2 is this same run's
own timing/clause-count/RSS instrumentation, since C1 already requires the full
build+solve.

ENVIRONMENT GUARDRAIL (AD6_PLAN.md, cross-cutting guardrails): wall-clock/
peak-RSS numbers from this script are only trusted on the controlled bare-metal
environment -- a sandboxed (yolobox) run can confirm the model builds/solves
correctly and give a DIRECTIONAL signal, but is never the tractability verdict
this stage's GO/NO-GO gate needs.

THE THREE-QUERY FAITHFUL EXPERIMENT (AD6_PLAN.md §5.5 "C3 REOPENED", owner
decision 2026-09-09). Everything this script needs to run it now exists; the
run itself has not been made. The question: FaVe+NetPlumber reports 11 of 72
pairs UNREACHABLE on wl_i2 where the policy expects 0, and both engines that
say 72/72 (ad6 plain, APKeep "VLAN as link identity") relax exactly the
dimension those 11 turn on. Relaxing a constraint can only ADD reachability,
so their agreement is not independent confirmation -- it is the same
simplification counted twice. A faithful ad6 run breaks the tie.

Three distinct models can now come out of this script, and a result file
stamps which one it is (`faithful_vlan` / `probe_untag`; `probe_vlan` records
what the probes DECLARE, separately from whether it was ENFORCED):

  1. plain            -- the default; reproduces every recorded artifact.
  2. faithful         -- + in-stage VLAN admission and the 77,451 out-stage
                         `rw=vlan:M` egress rewrites (C4 part 1).
  3. faithful + untag -- + the access-port untag on arrival (C4 part 2).

RUN 2 BEFORE 3, and do not skip straight to 3. Model 2 is the LIKE-FOR-LIKE
configuration against NetPlumber's 11: neither NetPlumber nor APKeep enforces
the untag on i2 (§5.5's PROBE-UNTAG PARITY FINDING -- NetPlumber computes the
header space and then discards it behind two `XXX: deactivate ... memory
explosion` guards; APKeep gates `tvlan` on `self._stanford and
self._faithful_vlan`), so model 3 is STRICTER than anything it would be
compared against. Running 3 first would answer a question no other engine has
been asked, and any disagreement would be uninterpretable. Run 3 second, and
its delta against 2 is then a deliberate measurement of what NetPlumber's
memory-explosion workaround costs in fidelity.

Recipe, cheapest step first (from fave/, PYTHONPATH=., venv active):

  # a. validate the configuration -- ~6 s, no instantiate, no solve. Catches
  #    a misspelled router name, and stamps the model shape (expect
  #    out_rw_rewrites: 77451 in faithful mode, 0 in plain, and
  #    in_admission_port_scoped: true with 223 ports / 596 (port, vlan)
  #    pairs -- `faithful_vlan: true` alone does NOT identify the encoding,
  #    see _admission_stamp).
  python3 bench/ad6_i2_measure.py --dry-run --faithful-vlan \\
      --pairs hous>salt,chic>salt,chic>seat

  # b. the control ALONE -- proves the faithful model builds and solves at
  #    all, before either discriminator's unknown-cost UNSAT is committed to.
  python3 bench/ad6_i2_measure.py --faithful-vlan --lite-acyclic \\
      --pairs hous>salt,chic>salt,chic>seat --max-queries 1 \\
      --solver cadical195 --checkpoint-every 1 --out i2_faithful_control.json

  # c. the experiment, untag OFF -- the like-for-like run.
  python3 bench/ad6_i2_measure.py --faithful-vlan --lite-acyclic \\
      --pairs hous>salt,chic>salt,chic>seat \\
      --solver cadical195 --checkpoint-every 1 --out i2_faithful_untag_off.json

  # d. the same three queries with the untag ON -- the deliberate delta.
  python3 bench/ad6_i2_measure.py --faithful-vlan --probe-untag --lite-acyclic \\
      --pairs hous>salt,chic>salt,chic>seat \\
      --solver cadical195 --checkpoint-every 1 --out i2_faithful_untag_on.json

`--lite-acyclic` IS REQUIRED ON i2, notwithstanding the flag's own
"EXPERIMENTAL, opt-in only" help text -- that wording is about not promoting
it to a default path, not about avoiding it here. The general
`_CreateAcyclicConstraints` does not complete on i2 in this environment (it
had not finished after 7-14 min: i2's Kripke graph is one giant non-trivial
SCC covering 99.3% of nodes, so it never gets the "orders of magnitude" cut
that makes the general encoding affordable on wl_stanford), and its per-edge
lxml/Tseitin machinery retains ~0.14-0.18 MB/edge on top. The lite path emits
the IDENTICAL clause set -- pinned by
`testAcyclicRankConstraintLiteMatchesGeneralEncoding` -- in ~15-21 s, and it
is what EVERY recorded i2 artifact was produced with (`lite_acyclic: true` in
all four of `bench/wl_i2/eval/ad6_i2_*.json`), so it is also the choice that
keeps a faithful run comparable with the plain figures. Do NOT reach for
`--skip-acyclic` instead: that drops the floating-cycle soundness fix
altogether and is orientation-only.

WHERE THE VERDICTS ARE IN A RESULT FILE: `query_log`, a list of
`{index, source, probe, elapsed_s, sat}`. NOT `queries` -- that key exists
only in `--dry-run` output, where it lists the PLANNED pairs. A reader (or a
progress monitor) that looks for verdicts under `queries` gets an absent key
and therefore an empty list, which is indistinguishable from "no query has
finished yet" -- the same silent-empty failure mode `_forced_literals` exists
to prevent on the literal side. This cost a real misreading on 2026-09-10: a
completed control query was reported for five hours as "still running", and a
28x solver slowdown was inferred from the silence. `queries_done`,
`last_query` and `last_query_s` are the cheap progress fields.

Reading the outcome of (c). `hous->salt` is the agreement control (both
engines call it reachable; 1.11 s in plain mode, the fastest of the 72).
`chic->salt` and `chic->seat` are the discriminators NetPlumber calls
unreachable.

  * control SAT, both discriminators UNSAT -> plain mode is insufficient for
    i2 (C3 NO-GO), and NetPlumber's 11 are corroborated by an independent
    engine.
  * control SAT, discriminators still SAT -> the disagreement localises to
    one engine and must be root-caused before either is trusted.
  * control UNSAT -> the faithful encoding is broken; stop, do not interpret
    the discriminators. This is what step (b) exists to find early.

Caveats to carry into the reading. All 72 recorded plain queries are
`sat: true`, so every recorded time is a SAT time and a LOWER BOUND -- the
discriminators are expected to flip to UNSAT, a regime this workload has
never exercised and whose cost is unknown. Fixed cost is ~405 s per run
regardless of query count, and the recorded per-query spread is 1.11 s to
1688.8 s, so do not extrapolate a full-set runtime from three queries drawn
deliberately from the fast tail. Memory is build/DIMACS-dominated and
therefore query-count-INDEPENDENT, and on a 20 GB box the faithful encoding
DOES NOT FIT as this script stands -- measured 2026-09-09 by step (b), which
reached `acyclic_constraints_built` at 18,067 MB RESIDENT with DIMACS
conversion and solver bootstrap (plain: +5.2 GB) still ahead. The graph is
unchanged (`kripke_nodes` 78,078 and `acyclic_extra_clauses` 14,201,913 in
BOTH modes); the whole delta is `_CreateMutationConstraints`, which takes
`build_s` from 358 to 700 s and pre-DIMACS resident from 8,271 to 18,067 MB.
Of that climb +5.4 GB is the `combined = deepcopy(encoding)` below -- dead
weight on this path, see its own comment -- so removing it may bring the run
inside 20 GB. Full trajectory: AD6_PLAN.md Sec 5.5. RSS is checkpointed after
every phase; a killed run leaves a usable partial result.

Note the ENVIRONMENT GUARDRAIL below applies to the TIMINGS, not to the
verdicts: SAT/UNSAT is what this experiment is for, and it is
environment-independent.

Usage (from fave/, PYTHONPATH=., venv active):
  python3 bench/ad6_i2_measure.py --out i2_plain.json
"""

import argparse
import gc
import json
import logging
import os
import resource
import sys
import time

from bench.ad6_stamp import admission_stamp

sys.setrecursionlimit(10 ** 6)

_HERE = os.path.dirname(os.path.abspath(__file__))     # .../fave/bench
_FAVE = os.path.dirname(_HERE)                          # .../fave
_ROOT = os.path.dirname(_FAVE)                           # repo root
_AD6 = os.path.join(_ROOT, 'ad6')

_I2_PREFIX = os.path.join("bench", "wl_i2", "i2-json")
_ORACLE = os.path.join("bench", "wl_i2", "reachable.json")


def _base(name):
    return name.split('.', 1)[1] if name.startswith(('source.', 'probe.')) else name


def _qualify(name, kind, known):
    """ Accept either a bare router base name (`chic`) or the fully-qualified
    model name (`source.chic`), and reject anything else BY NAME. The point
    is that an unknown name must not degrade into an empty selection:
    `--pair-filter` could only ever narrow a fixed 81-pair product, but a
    free-text pair list can name a router that does not exist, and a typo
    that merely selected nothing would cost the whole run. """
    candidates = [n for n in known if n == name or _base(n) == name]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError("unknown %s %r -- available: %s" % (
        kind, name, ", ".join(sorted(_base(n) for n in known))))


def _parse_pairs(spec, sources, probes):
    """ `--pairs` -- an explicit, ORDER-PRESERVING query list, e.g.
    "hous>salt,chic>salt,chic>seat" (AD6_PLAN.md §5.5's three-query faithful
    experiment). `--pair-filter` cannot express this: it only chooses between
    the self pairs and the cross pairs of the full product. """
    entries = spec.split(',')
    if not spec.strip() or any(not entry.strip() for entry in entries):
        raise ValueError(
            "--pairs must be a non-empty comma-separated list of SOURCE>PROBE "
            "pairs, e.g. hous>salt,chic>salt,chic>seat")
    queries = []
    for entry in entries:
        if entry.count('>') != 1:
            raise ValueError("malformed --pairs entry %r -- expected SOURCE>PROBE, "
                             "e.g. chic>salt" % entry.strip())
        source, probe = (part.strip() for part in entry.split('>'))
        queries.append({"source": _qualify(source, 'source', sources),
                        "probe": _qualify(probe, 'probe', probes)})
    return queries


def _select_queries(sources, probes, pair_filter=None, pairs=None, max_queries=None):
    """ The run's query list. The default -- the full product, probe-outer and
    source-inner -- is the order every archived `query_log` was written in, so
    a query `index` stays comparable across runs; do not sort it. """
    if pairs is not None and pair_filter is not None:
        raise ValueError("--pairs and --pair-filter are mutually exclusive: they "
                         "select queries in contradictory ways and one would "
                         "silently win")
    if pairs is not None:
        queries = _parse_pairs(pairs, sources, probes)
    else:
        queries = [{"source": s, "probe": p} for p in probes for s in sources]
        if pair_filter == "self-only":
            queries = [q for q in queries if _base(q['source']) == _base(q['probe'])]
        elif pair_filter == "exclude-self":
            queries = [q for q in queries if _base(q['source']) != _base(q['probe'])]
    if max_queries is not None:
        queries = queries[:max_queries]
    return queries


def _forced_literals(name_negated, name_to_index, context):
    """ Resolve already-canonical (variable name, negated) pairs against THIS
    run's DIMACS index, refusing any name the base encoding does not contain.

    That refusal is the whole reason this is a function. `index_for()` below
    -- like `IncrementalSession._index_for`, which it mirrors -- INVENTS a
    fresh index for an unknown name, and a freshly invented variable is
    otherwise unconstrained, so a misaddressed forced literal is satisfiable
    by construction. A `--probe-untag` run whose literals missed would
    therefore report itself as untagged while answering the untagless
    question, silently and after hours of compute. `ad6/test/parser/
    favemodeltest.py::FaithfulVlanProbeUntagTest.test_the_forced_variables_
    exist_in_the_base_encoding` makes the same check against a real encoding;
    this makes it a hard failure in the measurement path too. """
    literals = []
    missing = []
    for name, negated in name_negated:
        index = name_to_index.get(name)
        if index is None:
            missing.append(name)
            continue
        literals.append(-index if negated else index)
    if missing:
        raise RuntimeError(
            "%s: %d forced variable(s) absent from the base encoding: %s. Forcing "
            "them would be VACUOUS (an unknown name gets a fresh, unconstrained "
            "index), so the run would silently answer the UNFORCED question." % (
                context, len(missing), ", ".join(missing)))
    return literals


def _is_full_sweep(answered, sources, probes):
    """ Did this run ask every non-self pair? Decided from the queries
    ACTUALLY answered, not from which narrowing flags were passed, because
    the two are not equivalent: `--pair-filter exclude-self` narrows nothing
    that the differential cares about (`reach_matrix` drops self pairs by
    construction and the oracle has none), so a flag-based test would stamp a
    complete 72-pair sweep as partial. Self pairs are ignored on both
    sides. """
    expected = {(_base(s), _base(p)) for s in sources for p in probes
                if _base(s) != _base(p)}
    asked = {(_base(s), _base(p)) for s, p in answered if _base(s) != _base(p)}
    return asked >= expected


def _extract_witness(solver, sat, witness, index_to_name, source, destination, ir,
                     favemodel):
    """ The traversed FaVe devices for one SAT solve, or None.

    `favemodel` is passed IN rather than imported here, for two reasons. It is
    imported inside `measure()` (this script defers every ad6 import until
    after it has put `ad6/` on sys.path), so a module-level helper cannot see
    it -- an earlier version of this function referenced it as a global and
    died with NameError on the first SAT query, 877 s into a run. And passing
    it makes this function injectable, so `fave/test/test_ad6_i2_measure.py`
    can exercise it in milliseconds instead of the flag-plumbing tests being
    the only coverage.

    Reports `witness_edges_total` alongside the walk deliberately: a SAT model
    is not a path (see `favemodel.witness_path`), so the count of true
    transition edges is how a reader sees how much slack the model carried.
    `witness_path_nodes` is the ad6 node count, `witness_devices` the FaVe
    device hop sequence the NetPlumber flow-tree-leaf comparison consumes.

    UNSAT has no model, so nothing is extracted -- which is precisely why this
    is useful where the i2 disagreement sits: all three faithful answers are
    SAT, so every disputed pair carries a witness. """
    if not (witness and sat):
        return None
    model = solver.get_model()
    if model is None:
        return {"witness_error": "solver returned no model"}
    edges = favemodel.witness_edges(model, index_to_name)
    path = favemodel.witness_path(edges, source, destination)
    record = {"witness_edges_total": len(edges)}
    if path is None:
        # The solve said SAT, so the destination IS reachable; a missing walk
        # means the true-edge set holds none. Report that rather than
        # silently emitting an empty path.
        record["witness_error"] = "no %s -> %s walk inside the true-edge set" % (
            source, destination)
        return record
    record["witness_path_nodes"] = len(path)
    record["witness_devices"] = favemodel.witness_devices(path, ir)
    return record


def _oracle_diff(reach_matrix, oracle, queried_pairs):
    """ C1's differential against `bench/wl_i2/reachable.json`, SCOPED to the
    pairs the run actually asked about.

    `queried_pairs` is None for a full run (compare everything, the original
    behaviour that produced every archived figure) or the list of
    (source, probe) keys otherwise.

    The scoping is not a refinement, it is a correctness fix, and it was
    found by archiving the first real three-query result. `reach_matrix` is
    built over ALL sources and probes and reports a pair as unreachable when
    it was simply never queried, so diffing a 3-query run against the
    72-pair oracle stamped `oracle_match: false` on a run whose three answers
    were all consistent with the oracle. An artifact outlives the invocation
    that explains it, so that field would have read as "ad6 failed the
    differential" indefinitely. `oracle_full_set` records which question the
    verdict answers, so a partial agreement can never be mistaken for the
    full one -- the same separation `probe_vlan` (declared) and `probe_untag`
    (enforced) already keep.

    Scoping must not become a way of never failing: within the pairs actually
    queried a divergence still surfaces (test_a_scoped_run_still_catches_a_
    real_disagreement). Self pairs are excluded on both sides -- `reach_matrix`
    drops them by construction and the oracle has none. """
    ad6_m = {p: set(srcs) for p, srcs in reach_matrix.items()}
    or_m = {p: set(srcs) for p, srcs in oracle.items()}

    if queried_pairs is None:
        scope = None
    else:
        scope = {}
        for source, probe in queried_pairs:
            s_base, p_base = _base(source), _base(probe)
            if s_base != p_base:
                scope.setdefault(p_base, set()).add(s_base)

    def _sides(probe):
        got = ad6_m.get(probe, set())
        want = or_m.get(probe, set())
        if scope is not None:
            allowed = scope.get(probe, set())
            got, want = got & allowed, want & allowed
        return got, want

    probes = set(ad6_m) | set(or_m) if scope is None else set(scope)
    missing, extra, compared = {}, {}, 0
    for probe in probes:
        got, want = _sides(probe)
        compared += len(want | got) if scope is None else len(scope.get(probe, set()))
        if want - got:
            missing[probe] = sorted(want - got)
        if got - want:
            extra[probe] = sorted(got - want)
    return {"oracle_missing": missing, "oracle_extra": extra,
            "oracle_match": not missing and not extra,
            "oracle_pairs_compared": compared,
            "oracle_full_set": scope is None}


def _peak_rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def _current_rss_mb():
    """ ru_maxrss (used everywhere else in this script) is the HIGH-WATER MARK --
    monotonically non-decreasing, so it can't show a `del`+gc.collect() actually
    freeing memory. Only used around the explicit memory-release points below, to
    confirm they work; _peak_rss_mb() stays the script's primary reported metric. """
    try:
        with open('/proc/self/status') as fh:
            for line in fh:
                if line.startswith('VmRSS:'):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return None


# Moved to bench/ad6_stamp.py 2026-09-11 so `bench/ad6_faithful_measure.py`
# stamps admission by the IDENTICAL rule rather than a second implementation of
# it -- two drivers computing "port-scoped" slightly differently would defeat
# the stamp more quietly than omitting it. Re-exported under the original
# private name: this module's own callers and tests are unchanged.
_admission_stamp = admission_stamp


def _build_ir(faithful_vlan=False, probe_untag=False):
    """ AD6_PLAN.md §5.5 C0/C1: Ad6Adapter._build_ir() output for the real,
    full-scale wl_i2 model.

    BOTH FLAGS DEFAULT OFF, for two different reasons.

    `faithful_vlan` used to be hardcoded off, and until 2026-09-09 that was
    load-bearing: turning it on would NOT have produced a faithful i2 model,
    because `Ad6Adapter` had no `_capture_out_rewrite`, so i2's 77,451
    per-route egress-VLAN rewrites were dropped in either mode and faithful
    mode would have added in-stage VLAN admission with no matching egress
    rewrite -- an incoherent model rather than a faithful one. §5.5's C4 part
    1 closed that, so the flag is now a real choice and the caller makes it.
    It still defaults off because every recorded i2 artifact
    (`bench/wl_i2/eval/ad6_i2_*.json`) is `faithful_vlan: false`, and the
    default has to keep reproducing them.

    `probe_untag` (§5.5 C4 part 2) defaults off because NEITHER comparison
    backend enforces the access-port untag on i2 -- `netplumber/adapter.py`
    computes the header space from `test_fields` and then discards it behind
    two `XXX: deactivate ... memory explosion` guards, and
    `apkeep/adapter.py` gates `tvlan` on `self._stanford and
    self._faithful_vlan` -- so enforcing it here unconditionally would make
    ad6 the strictest of the three engines. See §5.5's PROBE-UNTAG PARITY
    FINDING; it is a workload-parity switch, and the difference between on
    and off is a measurement.

    What is NOT gated on either flag: plain mode matching `reachable.json`
    proves nothing about VLAN necessity, because dropping a VLAN admission
    gate can only ADD reachability and that oracle is an all-reachable 72/72
    mesh with zero expected-unreachable pairs. See the module docstring's
    WORKLOAD SCOPE note and §5.5's WORKLOAD-PARITY FINDING. """
    from ad6.adapter import Ad6Adapter
    from util.in_process_driver import InProcessFaVe

    log = logging.getLogger("ad6_i2_measure")
    log.setLevel(logging.WARNING)
    engine = Ad6Adapter(log, faithful_vlan=faithful_vlan, probe_untag=probe_untag)

    files = {"topology": "device_topology.json", "routes": "routes.json",
             "policies": "probes.json", "sources": "sources.json"}
    with InProcessFaVe(engine) as fave:
        fave.replay(_I2_PREFIX, files=files)
        sources = sorted(engine._generators)
        probes = sorted(engine._probes)
        ir = engine._build_ir()
    return ir, sources, probes


def _checkpoint(result, out_path, stage):
    """ Write progress-so-far to out_path and stderr after each phase, so a
    process killed mid-run (observed: a background nohup survives SIGHUP but
    not a sandbox/session teardown SIGKILL) still leaves a usable partial
    result instead of the silent zero-output loss hit on the first attempt. """
    result["status"] = "running:%s" % stage
    print("[checkpoint] %s wall_s=%.1f peak_rss_mb=%.1f" % (
        stage, time.time() - result["_wall0"], _peak_rss_mb()), file=sys.stderr, flush=True)
    if out_path:
        payload = {k: v for k, v in result.items() if not k.startswith("_")}
        with open(out_path, "w") as fh:
            json.dump(payload, fh, indent=2)


_SOLVERS = ("minisat22", "glucose4", "cadical195", "kissat404")


def measure(out_path, skip_acyclic=False, lite_acyclic=False, solver_name="minisat22",
            max_queries=None, checkpoint_every=10, pair_filter=None, fresh_per_query=False,
            flow_path=False,
            faithful_vlan=False, probe_untag=False, pairs=None, dry_run=False,
            witness=False):
    if probe_untag and not faithful_vlan:
        raise ValueError(
            "probe_untag requires faithful_vlan: probe_vlan_literals() returns nothing "
            "on a plain IR, so the run would stamp probe_untag while measuring the "
            "untagless model (AD6_PLAN.md §5.5 C4 part 2)")
    # The model identity is stamped BEFORE anything can fail, and the two
    # halves are stamped separately on purpose: `probe_vlan` below records what
    # the probes DECLARE, these record what was ENFORCED. Three distinct models
    # can now come out of this script, and a result file has to say which one
    # it is without reference to the command line that produced it.
    result = {"bench": "i2", "engine": "ad6",
              "faithful_vlan": faithful_vlan, "probe_untag": probe_untag}
    wall0 = time.time()
    result["_wall0"] = wall0

    ir, sources, probes = _build_ir(faithful_vlan=faithful_vlan, probe_untag=probe_untag)
    result["sources"] = len(sources)
    result["probes"] = len(probes)
    result["devices"] = len(ir["devices"])
    result["fwd_rules"] = len(ir["fwd_rules"])
    result["out_rw_rewrites"] = sum(len(v) for v in (ir.get("out_rw") or {}).values())
    # AD6_PLAN.md §5.5: which ADMISSION model this is -- `faithful_vlan` alone
    # no longer identifies the encoding. See _admission_stamp.
    result.update(_admission_stamp(ir))
    result["probe_vlan"] = dict(ir.get("probe_vlan") or {})

    # Resolve the query list HERE, off the freshly-built IR's real source/probe
    # names -- i.e. before the multi-minute instantiate and the multi-hour
    # solve, so an unknown router name in `--pairs` costs the ~5 s replay
    # rather than the run.
    queries = _select_queries(sources, probes, pair_filter=pair_filter, pairs=pairs,
                              max_queries=max_queries)
    result["query_count"] = len(queries)
    result["max_queries"] = max_queries
    result["pair_filter"] = pair_filter
    result["pairs"] = pairs
    _checkpoint(result, out_path, "ir_built")

    result["dry_run"] = dry_run
    if dry_run:
        # The cheapest possible validation of a run configuration: replay the
        # model, resolve and validate the query list, stamp the model identity
        # -- then stop. Every mistake the guards above can catch is caught for
        # the price of the replay instead of the run.
        result["status"] = "dry_run"
        result["queries"] = queries
        result["wall_s"] = round(time.time() - wall0, 3)
        result["peak_rss_mb"] = _peak_rss_mb()
        result.pop("_wall0", None)
        print(json.dumps(result, indent=2))
        if out_path:
            with open(out_path, "w") as fh:
                json.dump(result, fh, indent=2)
            print("wrote %s" % out_path, file=sys.stderr)
        return result

    sys.path.insert(0, _AD6)
    from src.core.instantiator import Instantiator
    from src.parser import favemodel
    from src.solver.minisat import MiniSATAdapter
    from src.xml.xmlutils import XMLUtils
    from pysat.solvers import Minisat22, Glucose4, Cadical195, Kissat404
    solver_cls = {
        "minisat22": Minisat22, "glucose4": Glucose4,
        "cadical195": Cadical195, "kissat404": Kissat404,
    }[solver_name]
    result["solver"] = solver_name
    from copy import deepcopy

    cwd = os.getcwd()
    os.chdir(_AD6)
    try:
        t0 = time.time()
        config = favemodel.build_config(ir)
        XMLUtils.deannotate(config)
        kripke, encoding = favemodel.instantiate_base(config, ir)
        result["kripke_nodes"] = len(list(kripke.IterNodes()))
        result["build_s"] = round(time.time() - t0, 3)
        # `config` (the lxml config tree build_config/deannotate produced) is provably
        # unused past this point: instantiate_base's own ConvertToKripke call is the
        # only consumer, and it builds `kripke` as a self-contained, dict-based
        # structure (structure.py) that holds no reference back into `config`. lxml
        # Elements form parent/child reference cycles, so a plain `del` alone isn't
        # enough to reclaim them promptly -- gc.collect() is needed too (this was
        # confirmed NOT to be a no-op cost here: the earlier gc_probe finding that
        # _CreateAcyclicConstraints's own retained objects are genuine, not garbage,
        # doesn't apply to `config`, which really is dead weight from here on).
        del config
        gc.collect()
        _checkpoint(result, out_path, "kripke_built")

        result["skip_acyclic"] = skip_acyclic
        result["lite_acyclic"] = lite_acyclic
        # MEASURED DEAD WEIGHT, 2026-09-09 -- the original line is kept
        # commented rather than deleted, because it is the one difference
        # between this script's memory profile and that of every artifact in
        # `bench/wl_i2/eval/`, and a reader comparing them needs to see it:
        #
        #     combined = deepcopy(encoding)
        #
        # It cost +5.4 GB of resident memory on the faithful i2 encoding (RSS
        # trajectory t=706->725 s of the control run; full decomposition in
        # AD6_PLAN.md §5.5's MEMORY ENVELOPE block) and bought nothing. Three
        # facts make the copy unnecessary, and all three have to hold:
        #
        #  1. `encoding` is a FRESH per-call object -- `favemodel.instantiate_base`
        #     builds it as `Instantiator._InstantiateBase(kripke)` and returns
        #     it; it is not cached, not module state, and not shared with
        #     `kripke` (which is the dict-based structure.py object, holding no
        #     reference back into the lxml tree).
        #  2. NOTHING else holds a reference. The `del encoding` below used to
        #     drop the second name on a copy; now it drops the only other name
        #     on the original, which is the same intent -- single owner from
        #     here on -- and is why it is kept rather than removed.
        #  3. On the `--lite-acyclic` path `combined` is never mutated at all:
        #     `_CreateAcyclicConstraintsLite`'s clauses are deliberately kept
        #     separate (they are plain (name, negated) tuples that cannot be
        #     spliced into an lxml formula list) and are resolved to DIMACS
        #     ints further down, after the base encoding's own index exists.
        #     Only the general path does `combined[0].extend(...)`, and that
        #     mutation is safe for the same reason (1)+(2) give: the tree it
        #     mutates has exactly one owner.
        #
        # Why it went unnoticed: in PLAIN mode the base encoding is small
        # enough that the copy is lost in the noise (plain's peak is reached
        # later, at solver bootstrap). Faithful mode's
        # `_CreateMutationConstraints` -- 12 VLAN bits x 78,078 nodes of
        # per-node SSA copies plus frame axioms -- makes the encoding the
        # largest object in the process, and doubling it the largest single
        # allocation.
        #
        # The encoding itself is BYTE-IDENTICAL either way: this changes what
        # is copied, never what is solved. `acyclic_extra_clauses`,
        # `variable_count` and `clause_count` are the invariants to check
        # against the recorded plain artifacts, and they must not move.
        combined = encoding
        del encoding
        gc.collect()
        # Quantifies the line above: with the deepcopy this read ~18.1 GB on
        # the faithful encoding, and the DIMACS/bootstrap phases still to come
        # cost plain mode +5.2 GB.
        result["current_rss_after_encoding_handoff_mb"] = _current_rss_mb()
        lite_clauses = None
        if skip_acyclic:
            # AD6_PLAN.md §5.5 C1/C2 finding: i2's Kripke graph has one giant
            # non-trivial SCC (99.3% of nodes), so _CreateAcyclicConstraints
            # doesn't get Stanford's "orders of magnitude" cut and did not
            # complete within 7-14 min in this environment. This path is a
            # cheap, ORIENTATION-ONLY check (does plain reachability match the
            # oracle at all, ignoring the floating-cycle soundness fix) -- NOT
            # a soundness-complete C1 result on its own.
            result["acyclic_constraint_s"] = None
            result["acyclic_extra_clauses"] = 0
        else:
            t0 = time.time()
            progress = {"last_wall": t0}

            def _progress(edge_index):
                now = time.time()
                if now - progress["last_wall"] >= 5.0:
                    progress["last_wall"] = now
                    result["acyclic_edge_index"] = edge_index
                    _checkpoint(result, out_path, "acyclic_constraints_running")

            if lite_acyclic:
                print("[experimental] --lite-acyclic: _CreateAcyclicConstraintsLite fixes "
                      "C2's memory blowup but NOT C2 overall (solving still hangs "
                      "regardless of backend) -- see AD6_PLAN.md Sec 5.5", file=sys.stderr)
                # AD6_PLAN.md §5.5 C2 NO-GO fix attempt: the general encoding's
                # per-edge lxml/Tseitin machinery retains ~0.14-0.18 MB/edge
                # (confirmed genuine, not reclaimable garbage -- memory
                # 'ad6-wl-i2-c2-nogo-oom'). _CreateAcyclicConstraintsLite emits
                # the IDENTICAL clause set (see
                # testAcyclicRankConstraintLiteMatchesGeneralEncoding) as plain
                # (name, negated) literal tuples instead, which can't be spliced
                # into `combined[0]` (an lxml-Element formula list) directly --
                # they're kept separate and resolved to DIMACS ints below,
                # after the base encoding's own name_to_index/index_for exist.
                lite_clauses = Instantiator._CreateAcyclicConstraintsLite(kripke, ProgressCallback=_progress)
                result["acyclic_extra_clauses"] = len(lite_clauses)
            else:
                acyclic_constraints = Instantiator._CreateAcyclicConstraints(kripke, ProgressCallback=_progress)
                result["acyclic_extra_clauses"] = len(acyclic_constraints)
                combined[0].extend(deepcopy(acyclic_constraints))
                del acyclic_constraints
            result["acyclic_constraint_s"] = round(time.time() - t0, 3)
            gc.collect()
            _checkpoint(result, out_path, "acyclic_constraints_built")

        t0 = time.time()
        adapter = MiniSATAdapter()
        result["current_rss_before_dimacs_mb"] = _current_rss_mb()
        variables, dimacs_clauses = adapter._ConvertToDIMACS(combined)
        # `combined` (the base encoding +, for the non-lite path, the acyclic
        # constraints already spliced into it) is fully consumed by _ConvertToDIMACS --
        # nothing downstream reads it again.
        del combined
        gc.collect()
        result["dimacs_s"] = round(time.time() - t0, 3)
        result["variable_count"] = len(variables)
        result["clause_count"] = len(dimacs_clauses)
        result["current_rss_after_combined_free_mb"] = _current_rss_mb()
        _checkpoint(result, out_path, "dimacs_converted")

        name_to_index = {name: i + 1 for i, name in enumerate(variables)}
        next_index = [len(variables) + 1]
        # Only name_to_index/next_index are used from here on (index_for/literal
        # below close over them, not over `variables` itself).
        del variables
        gc.collect()
        result["current_rss_after_variables_free_mb"] = _current_rss_mb()

        def index_for(name):
            idx = name_to_index.get(name)
            if idx is None:
                idx = next_index[0]
                name_to_index[name] = idx
                next_index[0] += 1
            return idx

        if lite_clauses is not None:
            t0 = time.time()
            dimacs_clauses.extend(
                [-index_for(name) if negated else index_for(name) for name, negated in clause]
                for clause in lite_clauses)
            del lite_clauses
            gc.collect()
            result["lite_dimacs_s"] = round(time.time() - t0, 3)
            result["variable_count"] = next_index[0] - 1
            result["clause_count"] = len(dimacs_clauses)
            _checkpoint(result, out_path, "lite_acyclic_merged")

        def literal(xml_var):
            idx = index_for(xml_var.attrib[XMLUtils.ATTRNAME])
            return -idx if xml_var.attrib.get(XMLUtils.ATTRNEGATED) == 'true' else idx

        def or_gate(xml_vars):
            lits = [literal(v) for v in xml_vars]
            if not lits:
                aux = next_index[0]
                next_index[0] += 1
                return aux, [[-aux]]
            if len(lits) == 1:
                return lits[0], []
            aux = next_index[0]
            next_index[0] += 1
            return aux, [[-lit, aux] for lit in lits] + [[-aux] + lits]

        # AD6_PLAN.md §5.4 B1 / §5.5: which GROUNDING constraint produced this
        # result. `skip_acyclic`/`lite_acyclic` alone no longer say -- a run
        # can now be grounded by the rank encoding, by the per-query flow
        # encoding, or (orientation-only) by neither.
        result["flow_path"] = flow_path
        result["fresh_per_query"] = fresh_per_query
        if fresh_per_query:
            # AD6_PLAN.md §5.5 C2 follow-up: Kissat404 was disqualified from the
            # incremental architecture because PySAT's wrapper ignores its
            # `assumptions` (Kissat has no native incremental API at all --
            # `incr=True` raises NotImplementedError). But the *reload* cost of
            # re-bootstrapping a fresh solver from `dimacs_clauses` was already
            # measured at ~5-7s (`solver_load_s` above, single-shot) -- negligible
            # against the 100s-800s/query solve times Cadical195/Glucose4 showed.
            # So rather than reuse ONE persistent solver + assumptions, build a
            # FRESH solver per query, baking the source/dest OR-gate literals in
            # as unit clauses instead of assumptions -- lets a genuinely
            # non-incremental (but potentially much faster on this instance)
            # solver like Kissat404 be tried at all, at the cost of a small
            # per-query reload. `dimacs_clauses` must stay resident for this (not
            # deleted like the persistent-session path does) -- checkpoint data
            # above (current_rss_before/after_dimacs_clauses_free_mb) showed
            # freeing it only recovers ~160MB out of ~11GB resident, so retaining
            # it is not the memory risk the persistent path's comment implies.
            solver = None
            result["solver_load_s"] = None
        else:
            t0 = time.time()
            solver = solver_cls(bootstrap_with=dimacs_clauses)
            result["solver_load_s"] = round(time.time() - t0, 3)
            # Minisat22.new() just iterates bootstrap_with, calling self.add_clause() per
            # clause into the underlying C solver (pysat/solvers.py) -- it keeps no
            # reference to the list itself, so the ~14M-entry `dimacs_clauses` Python list
            # (confirmed via checkpoints to be most of this script's pre-solve memory,
            # not the solver's own footprint) is pure dead weight from here on.
            result["current_rss_before_dimacs_clauses_free_mb"] = _current_rss_mb()
            del dimacs_clauses
            gc.collect()
            result["current_rss_after_dimacs_clauses_free_mb"] = _current_rss_mb()
        _checkpoint(result, out_path, "solver_loaded")

        # AD6_PLAN.md §5.5 "ROOT-CAUSING PLAN": the witness index. Built ONCE
        # and restricted to TRANSITION variables on purpose -- inverting the
        # whole name_to_index would materialise a 7.2M-entry dict beside an
        # instance already holding ~17 GB, whereas the transitions are a small
        # fraction of it. One pass over the variable table costs seconds; the
        # alternative (a set of the model's positive indices) is the expensive
        # direction on an instance this size.
        result["witness"] = witness
        index_to_name = {}
        if witness:
            t0 = time.time()
            for name, index in name_to_index.items():
                if favemodel.parse_transition_name(name) is not None:
                    index_to_name[index] = name
            result["witness_index_s"] = round(time.time() - t0, 3)
            result["witness_transition_vars"] = len(index_to_name)
            _checkpoint(result, out_path, "witness_index_built")

        ad6_reach = {}
        result["query_log"] = []
        t0 = time.time()
        for qi, q in enumerate(queries):
            q0 = time.time()
            source = favemodel.gen_entry_key(q['source'])
            destination = favemodel.query_destination_key(q['probe'], ir)
            f_trans = [XMLUtils.CreateTransition(source, t, flag)
                       for t, flag in kripke.IterFTransitions(source)]
            b_trans = [XMLUtils.CreateTransition(p, destination, flag)
                       for p, flag in kripke.IterBTransitions(destination)]
            src_lit, src_clauses = or_gate(f_trans)
            dst_lit, dst_clauses = or_gate(b_trans)
            # AD6_PLAN.md §5.5 C4 part 2. This has to be wired HERE as well as in
            # `ad6/fave_bridge.py`: this script does not go through the bridge or
            # `IncrementalSession` at all -- it drives PySAT directly (that is
            # what lets it swap solvers and instrument the build/DIMACS/solve
            # split), so the bridge's own `extra_vars` plumbing never runs.
            untag_literals = []
            if probe_untag:
                untag_vars = favemodel.probe_vlan_literals(q['probe'], ir, destination)
                untag_literals = _forced_literals(
                    [(v.attrib[XMLUtils.ATTRNAME],
                      v.attrib.get(XMLUtils.ATTRNEGATED) == 'true') for v in untag_vars],
                    name_to_index, "probe untag for %s (destination %s)" % (
                        q['probe'], destination))
                if not untag_literals:
                    raise RuntimeError(
                        "probe_untag is on but probe %s produced NO forced literals -- "
                        "it declares no arrival VLAN, so this run would be identical to "
                        "the untagless one while stamping probe_untag: true" % q['probe'])
                result.setdefault("probe_untag_literals", len(untag_literals))
            last_solver_load_s = None
            if fresh_per_query:
                # No assumptions API to lean on (Kissat) -- bake src_lit/dst_lit
                # in as unit clauses on a fresh solver instead of reusing one
                # persistent instance across queries.
                lq0 = time.time()
                q_solver = solver_cls(bootstrap_with=dimacs_clauses)
                for clause in src_clauses + dst_clauses:
                    q_solver.add_clause(clause)
                q_solver.add_clause([src_lit])
                q_solver.add_clause([dst_lit])
                # AD6_PLAN.md §5.4 B1 / §5.5: the single-unit s-t flow
                # grounding constraint, the cheap alternative to the rank
                # encoding. PER-QUERY by nature (source and destination appear
                # in it), which is why `--flow-path` requires
                # `--fresh-per-query`: added to a REUSED solver, query 1's
                # flow constraints would still be asserted during query 2.
                if flow_path:
                    fp0 = time.time()
                    flow_clauses = Instantiator._CreateFlowPathConstraints(
                        kripke, source, destination)
                    for clause in flow_clauses:
                        q_solver.add_clause([
                            -index_for(n) if neg else index_for(n)
                            for n, neg in clause])
                    q_flow = {"clauses": len(flow_clauses),
                              "build_s": round(time.time() - fp0, 3)}
                    del flow_clauses
                else:
                    q_flow = None
                for untag_literal in untag_literals:
                    q_solver.add_clause([untag_literal])
                last_solver_load_s = round(time.time() - lq0, 3)
                sat = bool(q_solver.solve())
                witness_record = _extract_witness(
                    q_solver, sat, witness, index_to_name, source, destination, ir,
                    favemodel)
                q_solver.delete()
            else:
                for clause in src_clauses + dst_clauses:
                    solver.add_clause(clause)
                sat = bool(solver.solve(assumptions=[src_lit, dst_lit] + untag_literals))
                witness_record = _extract_witness(
                    solver, sat, witness, index_to_name, source, destination, ir,
                    favemodel)
            # Full per-query history (AD6_PLAN.md Sec 5.5 C2 follow-up: the prior
            # last_query_s/last_query fields get OVERWRITTEN every checkpoint, so
            # the archived Glucose4/Cadical195 full runs never actually recorded
            # whether the SAME pairs are slow across solvers -- only this
            # accumulating list can answer that for a future run). Appended every
            # query regardless of checkpoint_every; only the on-disk WRITE cadence
            # is gated by checkpoint_every, to avoid excess I/O on a long run.
            elapsed = round(time.time() - q0, 3)
            if flow_path and fresh_per_query and q_flow is not None:
                result.setdefault("flow_path_clauses", q_flow["clauses"])
                result.setdefault("flow_path_build_s", q_flow["build_s"])
            entry = {
                "index": qi, "source": q['source'], "probe": q['probe'],
                "elapsed_s": elapsed, "solver_load_s": last_solver_load_s, "sat": sat,
            }
            if witness_record is not None:
                entry.update(witness_record)
            result["query_log"].append(entry)
            # Checkpoint every checkpoint_every-th AND the final query of a (possibly
            # max_queries-truncated) run, so a short probe (e.g. max_queries=1) still
            # leaves a per-query timing behind instead of only the phase-level
            # checkpoints. checkpoint_every=1 (query-localization diagnostic,
            # AD6_PLAN.md Sec 5.5's solver-comparison follow-up) also records which
            # (source, probe) pair each query answers, to localize a stall exactly.
            if (qi + 1) % checkpoint_every == 0 or (qi + 1) == len(queries):
                result["last_query_s"] = elapsed
                result["last_query_solver_load_s"] = last_solver_load_s
                result["last_query"] = {"source": q['source'], "probe": q['probe']}
                result["queries_done"] = qi + 1
                _checkpoint(result, out_path, "querying")
            ad6_reach[(q['source'], q['probe'])] = sat
        result["query_s"] = round(time.time() - t0, 3)
        if not fresh_per_query:
            solver.delete()

        reach = {
            _base(p): sorted(
                _base(s) for s in sources
                if ad6_reach.get((s, p), False) and _base(s) != _base(p)
            )
            for p in probes
        }
        result["reachable_pairs"] = sum(len(v) for v in reach.values())
        result["reach_matrix"] = reach
        result["status"] = "completed"
    finally:
        os.chdir(cwd)
        result["wall_s"] = round(time.time() - wall0, 3)
        result["peak_rss_mb"] = _peak_rss_mb()

    # C1: differential vs the oracle (fave/bench/wl_i2/reachable.json)
    oracle_path = os.path.join(_FAVE, _ORACLE)
    if "reach_matrix" in result and os.path.isfile(oracle_path):
        oracle = json.load(open(oracle_path))
        # A run narrowed by --pairs/--pair-filter/--max-queries is compared
        # only over what it asked; see _oracle_diff for why that is a fix and
        # not a relaxation.
        answered = [(q["source"], q["probe"]) for q in result["query_log"]]
        result.update(_oracle_diff(
            result["reach_matrix"], oracle,
            None if _is_full_sweep(answered, sources, probes) else answered))

    result.pop("_wall0", None)
    printable = {k: v for k, v in result.items() if k != "reach_matrix"}
    print(json.dumps(printable, indent=2))
    if out_path:
        with open(out_path, "w") as fh:
            json.dump(result, fh, indent=2)
        print("wrote %s" % out_path, file=sys.stderr)
    return result


def main(argv=None):
    # RawDescriptionHelpFormatter so the module docstring's RECIPE survives
    # --help: the default formatter reflows it into one paragraph, which turns
    # the copy-pasteable commands into unusable prose. Option help strings are
    # still wrapped normally -- this formatter only spares the description.
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", help="write the result JSON here")
    p.add_argument("--skip-acyclic", action="store_true",
                    help="orientation-only: skip _CreateAcyclicConstraints (cheap, but NOT "
                         "a soundness-complete C1 result -- see AD6_PLAN.md Sec 5.5)")
    p.add_argument("--lite-acyclic", action="store_true",
                    help="EXPERIMENTAL, opt-in only: use _CreateAcyclicConstraintsLite "
                         "(plain-Python clauses, no per-edge lxml/Tseitin construction) "
                         "instead of the general _CreateAcyclicConstraints. Fixes C2's "
                         "memory blowup but C2 overall is still NO-GO -- solving still "
                         "hangs regardless (AD6_PLAN.md Sec 5.5) -- kept experimental "
                         "until that's resolved, not promoted to any default path")
    p.add_argument("--solver", choices=_SOLVERS, default="minisat22",
                    help="PySAT backend to load/solve with (default: minisat22, PySAT's "
                         "own default) -- solver-comparison plan, AD6_PLAN.md Sec 5.5")
    p.add_argument("--max-queries", type=int, default=None,
                    help="stop after this many queries (default: all) -- for a cheap "
                         "first-query-only probe before committing to a full run")
    p.add_argument("--checkpoint-every", type=int, default=10,
                    help="checkpoint every N queries (default: 10); use 1 to localize "
                         "exactly which query stalls, AD6_PLAN.md Sec 5.5")
    p.add_argument("--pair-filter", choices=("self-only", "exclude-self"), default=None,
                    help="self-only: run just the 9 same-router pairs (the ones that "
                         "turned out trivial, AD6_PLAN.md Sec 5.5). exclude-self: run "
                         "just the 72 real cross-router pairs. Default: all 81")
    p.add_argument("--faithful-vlan", action="store_true",
                    help="build the FAITHFUL i2 model: in-stage VLAN admission + the "
                         "77,451 out-stage `rw=vlan:M` egress rewrites (AD6_PLAN.md "
                         "Sec 5.5 C4 part 1). Default off -- every recorded i2 artifact "
                         "is faithful_vlan: false and the default has to keep "
                         "reproducing them")
    p.add_argument("--probe-untag", action="store_true",
                    help="additionally enforce each probe's own declared arrival VLAN "
                         "(i2's access-port untag, vlan=0) as a query-time constraint "
                         "(Sec 5.5 C4 part 2). Requires --faithful-vlan. Default off, "
                         "and NOT caution: neither NetPlumber nor APKeep enforces this "
                         "on i2, so this on makes ad6 the strictest of the three -- see "
                         "Sec 5.5's PROBE-UNTAG PARITY FINDING. Run it OFF first")
    p.add_argument("--pairs", default=None,
                    help="explicit, order-preserving query list, e.g. "
                         "hous>salt,chic>salt,chic>seat (Sec 5.5's three-query faithful "
                         "experiment). Bare router names or fully-qualified "
                         "source.X>probe.Y both work; an unknown name is an error, not "
                         "an empty selection. Mutually exclusive with --pair-filter")
    p.add_argument("--witness", action="store_true",
                    help="on each SAT query, extract the traversed FaVe devices from "
                         "the solver's model (AD6_PLAN.md Sec 5.5 ROOT-CAUSING PLAN -- "
                         "the shared primitive behind both the witness check and the "
                         "NetPlumber flow-tree-leaf comparison). Opt-in: costs one pass "
                         "over the instance's variable table to index transition names")
    p.add_argument("--dry-run", action="store_true",
                    help="build the IR, resolve and validate the query list, stamp the "
                         "model identity -- then stop, before instantiate/solve. ~5 s "
                         "validation of a run configuration that would otherwise take "
                         "hours to discover a typo")
    p.add_argument("--flow-path", action="store_true",
                   help="ground each query with a single-unit s-t FLOW constraint "
                        "(Instantiator._CreateFlowPathConstraints) instead of the "
                        "rank/acyclic encoding -- AD6_PLAN.md Sec 5.4 B1. Requires "
                        "--fresh-per-query (the constraint is per-query) and is "
                        "normally combined with --skip-acyclic, since it REPLACES "
                        "the rank block rather than adding to it.")
    p.add_argument("--fresh-per-query", action="store_true",
                    help="build a FRESH solver instance per query (unit clauses for "
                         "src/dst instead of assumptions) instead of one persistent "
                         "incremental session. Required for kissat404 (no native "
                         "assumptions support); also usable as a control for any "
                         "other solver. AD6_PLAN.md Sec 5.5 C2 follow-up")
    args = p.parse_args(argv)
    # Both of these are refused rather than resolved, because either resolution
    # would produce a plausible result file answering a different question than
    # the flags claim.
    if args.probe_untag and not args.faithful_vlan:
        p.error("--probe-untag requires --faithful-vlan: probe_vlan_literals() returns "
                "nothing on a plain IR, so the run would stamp probe_untag: true while "
                "measuring the untagless model (AD6_PLAN.md Sec 5.5 C4 part 2)")
    if args.flow_path and not args.fresh_per_query:
        p.error("--flow-path requires --fresh-per-query: the flow constraint names "
                "the query's own source and destination, so adding it to a REUSED "
                "solver would leave query 1's constraints asserted during query 2 -- "
                "every later query would be answered against the wrong endpoints "
                "(AD6_PLAN.md Sec 5.4 B1)")
    if args.pairs is not None and args.pair_filter is not None:
        p.error("--pairs and --pair-filter are mutually exclusive -- they select "
                "queries in contradictory ways and one would silently win")
    measure(args.out, skip_acyclic=args.skip_acyclic, lite_acyclic=args.lite_acyclic,
            solver_name=args.solver, max_queries=args.max_queries,
            checkpoint_every=args.checkpoint_every, pair_filter=args.pair_filter,
            fresh_per_query=args.fresh_per_query, flow_path=args.flow_path,
            faithful_vlan=args.faithful_vlan,
            probe_untag=args.probe_untag, pairs=args.pairs, dry_run=args.dry_run,
            witness=args.witness)
    return 0


if __name__ == "__main__":
    sys.exit(main())
