#!/usr/bin/env python2

import csv
import json
import ast

if __name__ == '__main__':
    roles = {
        'Internet' : ['internet'],
        'WebServer' : ['dmz'],
        'Office' : ['office']
    }

    with open("bench/wl_example/roles_and_services.txt", 'r') as f:
        lines = f.read().split('\n')

        role = None
        for line in lines:
            token = line.lstrip().split(' ')
            if len(token) == 3 and token[0] == 'def':
                role = token[2]
            elif len(token) > 2 and token[0] == 'hosts':
                roles.setdefault(role, [])
                roles[role].extend(ast.literal_eval(' '.join(token[2:])))

    with open("bench/wl_example/reachability.csv", 'r') as f:
        reader = csv.reader(f, delimiter=',')

        header = reader.next()[1:]
        for role in header:
            if not role in roles: print role
            assert role in roles

    with open("bench/wl_example/inventory.json", 'w') as f:
        json.dump(roles, f, indent=2)
