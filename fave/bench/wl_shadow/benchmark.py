#!/usr/bin/env python2

RULESET="bench/wl_shadow/rules.ipt"
INVENTORY="bench/wl_shadow/inventory.txt"
POLICY="bench/wl_shadow/policy.txt"
INTERFACES="bench/wl_shadow/interfaces.json"

if __name__ == '__main__':
    use_unix = True
    verbose = False

    os.system("python2 bench/wl_generic_fw/benchmark.py -6 -r %s -i %s -p %s -m %s %s" % (
        RULESET,
        INVENTORY,
        POLICY,
        INTERFACES,
        "-u" if use_unix else "",
        "-v" if verbose else ""
    ))
