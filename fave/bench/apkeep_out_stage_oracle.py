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

""" Header-level APKeep-vs-NetPlumber differential for the wl_stanford out stage
(OUT_STAGE_PLAN.md step 0), and the evidence for its NEGATIVE RESULT.

**What this was built to do.** The out-stage collapse discards that stage's match
conditions. A plain reachability matrix cannot see it (OUT_STAGE_PLAN.md sec.
2.3), so step 0 asked for a header-level differential that FAILS on the pre-fix
tree -- otherwise the gate would pass against any implementation.

**What it established instead, and this is the headline: NO source->probe
reachability question can observe the gap, in the REFERENCE model.** Deleting all
16 out-stage deny rules from wl_stanford changes NetPlumber's own answer by
nothing -- 165/165 unconditioned, 30/30 under a TCP seed, 39/39 under the
anti-spoofing seed (`--drop-out-denies`, sec. 3 of the plan). The structural
reason is in the data:

  * every one of the 68 conditional arrival ports has a SINGLE-egress catch-all
    and no narrower permit routes anywhere else, so the 2,118 discarded permits
    are redundant with the catch-all and only the 16 denies remove anything; and
  * the denies are written against VLANs 68, 78, 730 and 570, and no out-stage
    rule ON THE DEVICES CARRYING THEM ever resets those to 0. All 16 probes
    filter `vlan=0`. So denied traffic can never satisfy a probe.

Both are reproducible from `routes.json` alone; this tool supplies the empirical
half.

**A second, unrelated defect fell out of it** (TODO item 26): for NetPlumber a
dst-CONDITIONED check and a dst-SEEDED check give different answers -- 35 vs 30
on the full model, 2 vs 1 on the yoza+bbra subnetwork -- although nothing in
wl_stanford rewrites anything but `vlan`, which makes the two formulations the
same question. APKeep's two answers agree with each other and with NetPlumber's
seeded one. Hence `--seed` is the trustworthy instrument here and `--cond` is
kept to reproduce the divergence.

Usage:
  # the negative result: the reference model cannot see its own denies
  python bench/apkeep_out_stage_oracle.py --drop-out-denies \
      --seed none --seed 'ipv4_dst=172.24.68.0/23+ip_proto=6'
  # backend differential, asked by SEEDING the generators (trustworthy)
  python bench/apkeep_out_stage_oracle.py --seed 'ipv4_dst=172.24.68.0/23+ip_proto=6'
  # backend differential, asked by CONDITIONING the check (reproduces item 26)
  python bench/apkeep_out_stage_oracle.py --cond dst:172.24.68.0/23
  # restrict to an induced subnetwork (see apkeep_convergence on its semantics)
  python bench/apkeep_out_stage_oracle.py --routers yoza_rtr,bbra_rtr --cond dst:172.24.68.0/23

Exit code: 0 iff every question agrees between the two backends (or, under
--drop-out-denies, iff dropping the denies changed nothing).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile

from typing import Any, Dict, List, Optional, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
FAVE = os.path.dirname(HERE)
sys.path.insert(0, FAVE)

from bench.apkeep_convergence import (      # noqa: E402  (path set above)
    FAVE as _FAVE, _FILES, _base, _filter_model, _load_model, _names,
    _not_reached, _write_model,
)

Pair = Tuple[str, str]

#: Short condition names -> the FaVe match field, for `--cond`. Only the fields
#: BOTH backends can force: APKeep's `_COND_SLOTS` is the binding constraint.
#: `vlan` is NOT among them, and every out-stage deny is VLAN-qualified -- which
#: is why a condition can only ever ask a BROADER question than a deny does, and
#: why pinning the DESTINATION (which pins the VLAN, since the mid stage assigns
#: the egress VLAN per dst route) was the only way to aim one at a deny at all.
_FIELDS = {
    'proto': 'packet.ipv6.proto',        # shared IPv4/IPv6 protocol field
    'src':   'packet.ipv4.source',
    'dst':   'packet.ipv4.destination',
    'sport': 'packet.upper.sport',
    'dport': 'packet.upper.dport',
}


def _parse_cond(spec: str) -> List[Dict[str, Any]]:
    """ "dst:172.24.68.0/23+proto:6" -> the condition list `check_compliance`
    takes. Fields are `+`-separated and CONJUNCTIVE: NetPlumber builds one header
    vector from all of them and APKeep intersects one arrival constraint per
    field, so both read the list the same way. """
    if spec in ('', 'none'):
        return []
    cond = []
    for part in spec.split('+'):
        short, _, value = part.partition(':')
        if short not in _FIELDS:
            raise SystemExit(
                "unknown condition field %r; both backends can force only %s "
                "(vlan is NOT among them -- see the module docstring)"
                % (short, '/'.join(sorted(_FIELDS))))
        cond.append({'name': _FIELDS[short], 'value': value, 'negated': False})
    return cond


def _make_engine(backend: str) -> Any:
    """ The PRODUCTION configuration, unlike `apkeep_convergence`'s plain/BDD.

    wl_stanford ships faithful (`faithful_vlan=True`, the aggregator default;
    `--no-vlan` opts out) on the NDD engine (owner, 2026-09-24). That is the
    configuration whose out stage contributes ZERO rules to the engine, so it is
    the one this differential has to interrogate. Plain mode cannot be asked a
    conditioned question at all: it is a pure dst-IP FIB, so `check_compliance`
    refuses the condition rather than answering the unconditioned one.
    """
    log = logging.getLogger("apkeep_out_stage_oracle")
    log.setLevel(logging.WARNING)
    if backend == "apkeep":
        from apkeep.adapter import APKeepAdapter
        # ORACLE_ENGINE=bdd switches the comparand. Production is NDD (owner,
        # 2026-09-24) and that is the default; the knob exists because the two
        # engines disagree about what a probe's VLAN filter means (TODO item 27)
        # and that question can only be asked of the BDD path -- which, on
        # faithful wl_stanford, may not finish.
        return APKeepAdapter(log, faithful_vlan=True,
                             engine=os.environ.get('ORACLE_ENGINE', 'ndd'))
    if backend == "netplumber":
        from netplumber.lib_adapter import NetPlumberLibAdapter
        return NetPlumberLibAdapter(log)
    raise ValueError("unknown backend %r" % backend)


def compute_matrix(backend: str, cond: List[Dict[str, Any]], seed: str,
                   routers: Optional[Set[str]],
                   drop_denies: bool) -> Dict[str, List[str]]:
    """ Drive wl_stanford through `backend` and return the reachability matrix.

    `seed` constrains what the GENERATORS emit; `cond` constrains what may arrive
    at the probe. For a field nothing rewrites the two are the same question --
    see the module docstring on why, for NetPlumber, they are not.

    One process per backend (APKeep's resident JVM and NetPlumber's native lib
    cross-contaminate; see apkeep_convergence's docstring). """
    from util.in_process_driver import InProcessFaVe

    model = _load_model()
    if routers is not None:
        model = _filter_model(model, routers)
    if drop_denies:
        model['routes'] = [r for r in model['routes']
                           if not (r[0].split('.', 1)[0] == 'out' and not r[4])]
    if seed not in ('', 'none'):
        for device in model['sources']['devices']:
            device[2] = seed.split('+')

    engine = _make_engine(backend)
    with tempfile.TemporaryDirectory(prefix="out_stage_oracle_") as tmp:
        _write_model(model, tmp)
        with InProcessFaVe(engine) as fave:
            fave.replay(tmp, files=_FILES)
            sources, probes = _names(engine)
            rules = {p: [[s, False, cond] for s in sources] for p in probes}
            fave.check_compliance(rules)
        not_reached = _not_reached(engine)
        return {
            _base(p): sorted(
                _base(s) for s in sources
                if (s, p) not in not_reached and _base(s) != _base(p)
            )
            for p in probes
        }


def _pairs(matrix: Dict[str, List[str]]) -> Set[Pair]:
    return {(s, p) for p, srcs in matrix.items() for s in srcs}


def _emit_worker(backend: str, spec: str, seed: str, routers: Optional[Set[str]],
                 drop_denies: bool, out: str) -> Dict[str, List[str]]:
    argv = [sys.executable, os.path.abspath(__file__), "--emit", backend,
            "--cond", spec, "--seed", seed, "--out", out]
    if routers is not None:
        argv += ["--routers", ",".join(sorted(routers))]
    if drop_denies:
        argv += ["--drop-out-denies"]
    env = dict(os.environ, PYTHONPATH=_FAVE)
    proc = subprocess.run(argv, cwd=_FAVE, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-3000:])
        raise RuntimeError("%s worker failed on cond=%r seed=%r (rc=%d)"
                           % (backend, spec, seed, proc.returncode))
    with open(out) as raw:
        return json.load(raw)


def _run_backend_diff(questions: List[Tuple[str, str]],
                      routers: Optional[Set[str]]) -> int:
    disagreeing = 0
    for spec, seed in questions:
        with tempfile.TemporaryDirectory(prefix="out_stage_oracle_out_") as tmp:
            ap = _emit_worker("apkeep", spec, seed, routers, False,
                              os.path.join(tmp, "ap.json"))
            np = _emit_worker("netplumber", spec, seed, routers, False,
                              os.path.join(tmp, "np.json"))
        ap_p, np_p = _pairs(ap), _pairs(np)
        over, under = ap_p - np_p, np_p - ap_p
        status = "AGREE" if not over and not under else "DISAGREE"
        disagreeing += status == "DISAGREE"
        print("\ncond=%-24s seed=%-38s apkeep=%-4d np=%-4d over=%-3d under=%-3d %s"
              % (spec, seed, len(ap_p), len(np_p), len(over), len(under), status))
        for label, pairs in (("APKeep-only (over)", over), ("NP-only (under)", under)):
            for s, p in sorted(pairs):
                print("    %-20s %s -> %s" % (label, s, p))
    print("\nRESULT: %d of %d question(s) disagree between the backends"
          % (disagreeing, len(questions)))
    return 1 if disagreeing else 0


def _run_deny_drop(questions: List[Tuple[str, str]],
                   routers: Optional[Set[str]]) -> int:
    """ Does the REFERENCE model's answer depend on the 16 out-stage denies? """
    moved = 0
    for spec, seed in questions:
        with tempfile.TemporaryDirectory(prefix="out_stage_deny_") as tmp:
            intact = _emit_worker("netplumber", spec, seed, routers, False,
                                  os.path.join(tmp, "intact.json"))
            without = _emit_worker("netplumber", spec, seed, routers, True,
                                   os.path.join(tmp, "without.json"))
        a, b = _pairs(intact), _pairs(without)
        moved += a != b
        print("\ncond=%-24s seed=%-38s intact=%-4d without-denies=%-4d  %s"
              % (spec, seed, len(a), len(b),
                 "DENIES MATTER" if a != b else "denies are INERT"))
        for s, p in sorted(b - a):
            print("    only-without-denies  %s -> %s" % (s, p))
    print("\nRESULT: the 16 out-stage denies change NetPlumber's answer on "
          "%d of %d question(s)" % (moved, len(questions)))
    return 1 if moved else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--emit", choices=("apkeep", "netplumber"))
    parser.add_argument("--out")
    parser.add_argument("--cond", action="append", default=None,
                        help="arrival condition as <field>:<value>[+...] "
                             "(repeatable); see the docstring on why --seed is "
                             "the trustworthy instrument")
    parser.add_argument("--seed", action="append", default=None,
                        help="generator seed as <field>=<value>[+...] "
                             "(repeatable), e.g. ipv4_dst=172.24.68.0/23+ip_proto=6")
    parser.add_argument("--routers")
    parser.add_argument("--drop-out-denies", action="store_true",
                        help="delete the 16 out-stage deny rules and ask "
                             "NetPlumber whether its answer moves")
    args = parser.parse_args(argv)

    routers = set(args.routers.split(",")) if args.routers else None
    conds = args.cond or ["none"]
    seeds = args.seed or ["none"]
    # One question per cond x seed entry, zipped to the longer list so a battery
    # can vary either axis without repeating the other.
    width = max(len(conds), len(seeds))
    questions = [(conds[i % len(conds)], seeds[i % len(seeds)])
                 for i in range(width)]

    if args.emit:
        if not args.out:
            parser.error("--emit requires --out")
        if len(questions) != 1:
            parser.error("--emit takes exactly one question")
        matrix = compute_matrix(args.emit, _parse_cond(conds[0]), seeds[0],
                                routers, args.drop_out_denies)
        with open(args.out, "w") as out:
            json.dump(matrix, out)
        return 0

    print("== wl_stanford out-stage oracle (%s) =="
          % ("routers=%s" % ",".join(sorted(routers)) if routers
             else "full 16-router"))
    if args.drop_out_denies:
        return _run_deny_drop(questions, routers)
    return _run_backend_diff(questions, routers)


if __name__ == "__main__":
    sys.exit(main())
