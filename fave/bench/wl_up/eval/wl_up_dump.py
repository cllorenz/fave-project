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

""" Dump the wl_up model (APKeep rule strings + topology edges) to JSON, for the
NDD engine prototype (APKEEP_NDD_PLAN.md 2.5b). Captures the assembled rule batch
just before the Java build (patches LibAPKeep), so no verification runs.

Run from fave/ with PYTHONPATH=.:
    PYTHONPATH=. python3 wl_up_dump.py <out.json>
"""
import json
import logging
import os
import sys

import apkeep.lib_apkeep as libmod

CAP = {"rules": None, "edges": None, "fwd": None, "filters": None, "acls": None, "nats": None}


def _fake_init(self, name, l1_links, fwd_devices=None, device_acls=None,
               device_nats=None, device_filters=None, bdd_table_size=1_000_000):
    CAP["edges"] = list(l1_links)
    CAP["fwd"] = list(fwd_devices or [])
    CAP["filters"] = list(device_filters or [])
    CAP["acls"] = {k: list(v) for k, v in (device_acls or {}).items()}
    CAP["nats"] = {k: list(v) for k, v in (device_nats or {}).items()}
    return None


def _fake_run(self, rules):
    CAP["rules"] = list(rules)
    return None


def _fake_metrics(self):
    return {"ACLElement": 0, "NATElement": 0}


libmod.LibAPKeep.init_in_memory = _fake_init
libmod.LibAPKeep.run = _fake_run
libmod.LibAPKeep.element_metrics = _fake_metrics


def main(out_path):
    log = logging.getLogger("wl_up_dump")
    log.setLevel(logging.ERROR)
    from apkeep.adapter import APKeepAdapter, available
    if not available():
        print("APKeep unavailable")
        return 1
    from util.in_process_driver import InProcessFaVe

    engine = APKeepAdapter(log)
    with InProcessFaVe(engine) as fave:
        fave.replay("bench/wl_up")
        sources = sorted(engine._generators)
        probes = sorted(engine._probes)
        engine._build()

    dump = {
        "rules": CAP["rules"],
        "edges": CAP["edges"],
        "fwd_devices": CAP["fwd"],
        "filter_devices": CAP["filters"],
        "sources": sources,
        "probes": probes,
    }
    with open(out_path, "w") as fh:
        json.dump(dump, fh)
    print("rules=%d edges=%d fwd=%d filters=%d sources=%d probes=%d -> %s" % (
        len(CAP["rules"]), len(CAP["edges"]), len(CAP["fwd"]),
        len(CAP["filters"]), len(sources), len(probes), out_path))
    return 0


if __name__ == "__main__":
    rc = main(sys.argv[1] if len(sys.argv) > 1 else "wl_up_model.json")
    sys.stdout.flush()
    os._exit(rc)
