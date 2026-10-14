#!/usr/bin/env python3

""" wl_tum's inventory: each FPL role (fplgen.py) to its one endpoint, the
name of its source and probe (layout.py). """

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench.wl_tum import fplgen, layout  # pylint: disable=wrong-import-position

OFILE = "bench/wl_tum/inventory.json"

if __name__ == '__main__':
    inventory = {('Internet' if name == 'Internet' else fplgen.role_name(name)): [layout.endpoint_id(name)]
                 for name, _port, _ep in layout.endpoints()}
    with open(OFILE, 'w') as of:
        of.write(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
