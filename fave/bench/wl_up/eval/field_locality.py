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

""" wl_up field-locality measurement -- the NDD GO/NO-GO gate (APKEEP_NDD_PLAN.md
2.0).

NDD computes atomic predicates PER FIELD, so its total atom count is a *sum*
over fields instead of the *product* (cross-product) a single global BDD/AP
partition pays. That win is strong when rules mostly constrain 1-2 orthogonal
fields, and degrades (NDD paper, NSDI'25, 6.6) when rules constrain many fields
at once. This tool quantifies where wl_up sits by building the model through the
APKeepAdapter and histogramming the number of *constrained BDD header fields*
per emitted rule.

It intercepts the assembled APKeep rule batch just before the (multi-minute)
Java build (patches LibAPKeep.init_in_memory/run/element_metrics to capture and
short-circuit), so it is cheap -- no verification runs.

IMPORTANT scoping note: in_port/out_port anti-spoofing is modelled STRUCTURALLY
in this backend (per-port FilterElements + the Port Predicate Map), NOT as a BDD
header field, so it does not appear in this count and does not enter the
atomic-predicate cross-product -- which is precisely the term NDD attacks. The
fields counted here are the actual BDD header fields: proto, src, sport, dst,
dport, vlan, related.

Run from fave/ with PYTHONPATH=.:
    PYTHONPATH=. python3 bench/wl_up/eval/field_locality.py
    FIELD_LOCALITY_OUT=out.json PYTHONPATH=. python3 bench/wl_up/eval/field_locality.py
"""

import collections
import json
import logging
import os
import sys

import apkeep.lib_apkeep as libmod

CAPTURED = {"rules": None, "edges": None, "fwd": None, "acls": None,
            "nats": None, "filters": None}


def _fake_init_in_memory(self, name, l1_links, fwd_devices=None,
                         device_acls=None, device_nats=None,
                         device_filters=None, bdd_table_size=1_000_000):
    CAPTURED["edges"] = list(l1_links)
    CAPTURED["fwd"] = list(fwd_devices or [])
    CAPTURED["acls"] = dict(device_acls or {})
    CAPTURED["nats"] = dict(device_nats or {})
    CAPTURED["filters"] = list(device_filters or [])
    return None


def _fake_run(self, rules):
    # Capture the assembled rule batch; do NOT run the (multi-minute) Java build.
    CAPTURED["rules"] = list(rules)
    return None


def _fake_element_metrics(self):
    # _build() reads this right after run(); the net was never built, so return
    # the single-universe shape (no ACL/NAT elements). Irrelevant to the capture.
    return {"ACLElement": 0, "NATElement": 0}


libmod.LibAPKeep.init_in_memory = _fake_init_in_memory
libmod.LibAPKeep.run = _fake_run
libmod.LibAPKeep.element_metrics = _fake_element_metrics


# --- field parsing -----------------------------------------------------------

IPV4_ANY = ("0.0.0.0", "255.255.255.255")


def _addr_constrained(ip, wild):
    """ True unless (ip, wild) is the all-space wildcard. A constrained IPv6
    address is "addr/len" with wild "null"; a constrained IPv4 is a specific
    address + inverse mask; both differ from IPV4_ANY. """
    return not (ip == IPV4_ANY[0] and wild == IPV4_ANY[1])


def classify(rule):
    """ (role, set_of_constrained_fields) for one "+ ..." APKeep rule string.
    Token layouts are those emitted by apkeep/adapter.py's _fib_rule_string,
    _filter_rule_string and _acl_rule_string. """
    t = rule.split()
    kind = t[1]
    fields = set()
    if kind == "fwd":
        # + fwd <dev> <prefix> <plen> <port> <plen>   (dst-LPM only)
        return ("fwd(dst-LPM)", {"dst"})
    if kind == "acl":
        # + acl <elem> acl 0 <permit/deny> 0 255 <sip> <swild> null null
        #       <dip> <dwild> null null <prio> [vlan]
        sip, swild, dip, dwild = t[8], t[9], t[12], t[13]
        if _addr_constrained(sip, swild):
            fields.add("src")
        if _addr_constrained(dip, dwild):
            fields.add("dst")
        if len(t) >= 18:            # trailing vlan token present
            fields.add("vlan")
        return ("acl", fields)
    if kind == "filter":
        # + filter <dev> filter 0 <out> <plo> <phi> <sip> <swild> <slo> <shi>
        #          <dip> <dwild> <dlo> <dhi> <prio> [vlan] [rel]
        plo, phi = t[6], t[7]
        sip, swild, slo, shi = t[8], t[9], t[10], t[11]
        dip, dwild, dlo, dhi = t[12], t[13], t[14], t[15]
        vlan = t[17] if len(t) > 17 else "null"
        rel = t[18] if len(t) > 18 else "null"
        if not (plo == "0" and phi == "255"):
            fields.add("proto")
        if _addr_constrained(sip, swild):
            fields.add("src")
        if not (slo == "null" and shi == "null"):
            fields.add("sport")
        if _addr_constrained(dip, dwild):
            fields.add("dst")
        if not (dlo == "null" and dhi == "null"):
            fields.add("dport")
        if vlan != "null":
            fields.add("vlan")
        if rel != "null":
            fields.add("related")
        dev = t[2]
        role = "filter(fib)" if (dev.endswith(".fib") and fields == {"dst"}) else "filter"
        return (role, fields)
    if kind == "nat":
        return ("nat(rewrite)", set())      # a rewrite, not a match
    return ("other:%s" % kind, set())


def main():
    log = logging.getLogger("field_locality")
    log.setLevel(logging.ERROR)
    from apkeep.adapter import APKeepAdapter, available
    if not available():
        print("APKeep unavailable (JPype/jar missing)")
        return 1
    from util.in_process_driver import InProcessFaVe

    # bench/wl_up (this file lives in bench/wl_up/eval/); replay wants the dir
    # relative to the fave/ cwd.
    model_rel = os.path.join("bench", "wl_up")

    engine = APKeepAdapter(log)
    # replay populates the adapter's model buffers; call _build() DIRECTLY (not
    # via check_compliance, whose threaded aggregator path deadlocks when the JVM
    # build is stubbed). _build assembles the rule batch -> our stubbed run().
    with InProcessFaVe(engine) as fave:
        fave.replay(model_rel)
        sources = sorted(engine._generators)
        probes = sorted(engine._probes)
        engine._build()

    rules = CAPTURED["rules"]
    if rules is None:
        print("!! capture failed: run() was never reached")
        return 2

    print("== wl_up field-locality (APKEEP_NDD_PLAN.md 2.0) ==")
    print("sources=%d probes=%d" % (len(sources), len(probes)))
    print("model elements: edges=%d fwd_devs=%d filter_devs=%d acls=%d nats=%d"
          % (len(CAPTURED["edges"]), len(CAPTURED["fwd"]),
             len(CAPTURED["filters"]), len(CAPTURED["acls"]),
             len(CAPTURED["nats"])))
    print("total rules emitted: %d\n" % len(rules))

    nfields_hist = collections.Counter()
    role_hist = collections.Counter()
    role_nfields = collections.defaultdict(collections.Counter)
    field_use = collections.Counter()
    combo = collections.Counter()

    for r in rules:
        role, fields = classify(r)
        role_hist[role] += 1
        if role == "nat(rewrite)":
            continue
        n = len(fields)
        nfields_hist[n] += 1
        role_nfields[role][n] += 1
        for f in fields:
            field_use[f] += 1
        combo[(role, tuple(sorted(fields)))] += 1

    match_rules = sum(nfields_hist.values())
    print("--- #constrained-fields distribution (match rules only) ---")
    for n in sorted(nfields_hist):
        c = nfields_hist[n]
        print("  %d field(s): %6d rules  (%.1f%%)" % (n, c, 100.0 * c / match_rules))
    many = sum(c for n, c in nfields_hist.items() if n >= 4)
    lite = sum(c for n, c in nfields_hist.items() if n <= 2)
    both = sum(c for (role, fs), c in combo.items() if "src" in fs and "dst" in fs)
    print("  --> <=2 fields: %.1f%%   >=4 fields: %.1f%%   src&dst(both 128-bit): %.1f%%"
          % (100.0 * lite / match_rules, 100.0 * many / match_rules,
             100.0 * both / match_rules))

    print("\n--- by role ---")
    for role in sorted(role_hist):
        detail = " ".join("%df:%d" % (n, role_nfields[role][n])
                          for n in sorted(role_nfields[role]))
        print("  %-16s %6d   [%s]" % (role, role_hist[role], detail))

    print("\n--- field usage (rules constraining each BDD header field) ---")
    for f, c in field_use.most_common():
        print("  %-8s %6d  (%.1f%%)" % (f, c, 100.0 * c / match_rules))

    print("\n--- top field-combinations ---")
    for (role, fs), c in combo.most_common(12):
        print("  %-16s {%s}: %d" % (role, ",".join(fs) or "-", c))

    out = {
        "sources": len(sources), "probes": len(probes),
        "total_rules": len(rules), "match_rules": match_rules,
        "nfields_hist": {str(k): v for k, v in nfields_hist.items()},
        "role_hist": dict(role_hist),
        "field_use": dict(field_use),
        "pct_le2": 100.0 * lite / match_rules,
        "pct_ge4": 100.0 * many / match_rules,
        "pct_src_and_dst": 100.0 * both / match_rules,
        "elements": {"edges": len(CAPTURED["edges"]),
                     "fwd_devs": len(CAPTURED["fwd"]),
                     "filter_devs": len(CAPTURED["filters"]),
                     "acls": len(CAPTURED["acls"]),
                     "nats": len(CAPTURED["nats"])},
    }
    dest = os.environ.get("FIELD_LOCALITY_OUT")
    if dest:
        with open(dest, "w") as fh:
            json.dump(out, fh, indent=2, sort_keys=True)
        print("\nwrote %s" % dest)
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # Hard-exit: skip JVM/jpype shutdown hooks (they can stall on a network that
    # was never fully built). We are done and all output is flushed.
    os._exit(rc)
