#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>
# This file is part of FaVe. GPLv3+ (see project root).
""" Faithful-i2 (dst x VLAN) partition sizing: NDD per-field Sigma vs BDD joint Pi.

wl_i2 is two-field: out.* routes match ipv4_dst and rewrite the VLAN
(rw=vlan:M(dst)); in.* rules admit a VLAN set. NDD keeps dst and VLAN as SEPARATE
fields (Sigma = |dst-atoms| + |VLAN-classes|); BDD-APKeep atoms are single BDDs
over the joint (dst,VLAN) space, so the INDEPENDENT in.* VLAN admission multiplies
against the dst partition (Pi ~ |dst-atoms| x |VLAN-classes|) -- a cross-product
blow-up NDD avoids. (The rw=vlan is dst-slaved, so it alone does not blow up; the
independent admission does.) Estimate from routes.json; the exact BDD ap_num is
measured by building the faithful-i2 model in BDD-APKeep. Run from fave/. """
import collections
import json
import sys

R = "bench/wl_i2/i2-json/routes.json"


def main():
    r = json.load(open(R))
    dst_rules = collections.defaultdict(list)   # out.dev -> [(lo,hi,plen,port)]
    in_admit = collections.defaultdict(set)     # in.dev -> {admitted vlan}
    for x in r:
        dev, match, action = x[0], x[3], x[4]
        dst = None
        for m in match:
            if m.startswith("ipv4_dst="):
                dst = m.split("=")[1]
            elif m.startswith("vlan=") and dev.startswith("in."):
                in_admit[dev].add(m.split("=")[1])
        port = next((a.split("=")[1] for a in action if a.startswith("fd=")), None)
        if dst is not None and port is not None:
            addr, _, pl = dst.partition("/")
            plen = int(pl) if pl else 32
            o = [int(b) for b in addr.split(".")]
            pref = (o[0] << 24) | (o[1] << 16) | (o[2] << 8) | o[3]
            lo = pref & ((((1 << plen) - 1) << (32 - plen)) if plen else 0)
            dst_rules[dev].append((lo, lo + (1 << (32 - plen)) - 1, plen, port))

    # dst-atoms: elementary intervals merged by per-device LPM forwarding signature
    bounds = {0, 1 << 32}
    for rs in dst_rules.values():
        for lo, hi, _pl, _pt in rs:
            bounds.add(lo); bounds.add(hi + 1)
    bs = sorted(bounds)
    devs = sorted(dst_rules)

    def lpm(rules, a):
        best, port = -1, None
        for lo, hi, pl, pt in rules:
            if lo <= a <= hi and pl > best:
                best, port = pl, pt
        return port
    dst_sigs = set()
    for i in range(len(bs) - 1):
        dst_sigs.add(tuple(lpm(dst_rules[d], bs[i]) for d in devs))
    dst_atoms = len(dst_sigs)

    # VLAN-admission classes: VLANs with the same in.* admission signature merge
    indev = sorted(in_admit)
    allv = set().union(*in_admit.values()) if in_admit else set()
    vlan_sigs = {tuple(1 if v in in_admit[d] else 0 for d in indev) for v in allv}
    vlan_classes = len(vlan_sigs)

    sigma = dst_atoms + vlan_classes
    pi = dst_atoms * vlan_classes
    print("dst-atoms                = %d" % dst_atoms)
    print("distinct admitted VLANs  = %d" % len(allv))
    print("VLAN-admission classes   = %d" % vlan_classes)
    print("NDD Sigma (per-field)    = %d + %d = %d" % (dst_atoms, vlan_classes, sigma))
    print("BDD Pi  (joint estimate) = %d x %d = %d" % (dst_atoms, vlan_classes, pi))
    print("Sigma-vs-Pi              ~= %.0fx" % (pi / sigma))
    return 0


if __name__ == "__main__":
    sys.exit(main())
