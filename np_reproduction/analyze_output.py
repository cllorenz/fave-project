#!/usr/bin/env python2


import sys
import pprint
import json


def _analyze_loop(tokens, tables):
    loop = []
    tokens.reverse()
    for token in tokens:
        try:
            rule_id = int(token, 16)
            loop.append(tables[rule_id >> 32])
        except ValueError:
            continue

    return loop

all_loops = {}
all_probes = {}

benchmark = sys.argv[1]
output_files = sys.argv[2:]
for output_file in output_files:
    with open(output_file, 'r') as f:
        loop = False
        loops = []
        probes = {}

        prefix = output_file.split('.')[0].split('_')[1] # XXX :-(
        config_json = json.load(open("%s_json_%s/config.json" % (benchmark, prefix)))
        tables = {
            tid*10 + ttid : "%s.%s" % (table, ttype) for ttid, ttype in \
                enumerate(config_json["table_types"]) for tid, table in \
                enumerate(config_json["tables"], start=1)
        }

        for line in f.readlines():
            if loop:
                loops.append(_analyze_loop(line.split(), tables))
                loop = False
                continue

            tokens = line.split()
            if len(tokens) < 9:
                continue

            elif tokens[7] == 'Probe':
                probe_id = int(tokens[8])
                probes.setdefault(probe_id, 0)
                probes[probe_id] += 1

            elif tokens[6] == 'Loop':
                loop = True

        all_loops[output_file] = loops
        all_probes[output_file] = probes


for output_file in output_files:
    print "%s found %s active probes" % (output_file, len(all_probes[output_file])),
    print " with a total of %d incoming flows" % sum([all_probes[output_file][probe_id] for probe_id in all_probes[output_file]])
    print "%s found %s loops" % (output_file, len(all_loops[output_file]))

def _check_no_differences(output_files, all_probes, all_loops):
    sums = [sum([all_probes[output_file][probe_id] for probe_id in all_probes[output_file]]) for output_file in output_files]
    loops = [len(app_loops[output_file]) for output_file in output_files]
    return min(sums) == max(sums) and min(loops) == max(loops)

if not _check_no_differences:
    for k1, k2 in zip(sorted(all_probes[output_files[0]].keys()), sorted(all_probes[output_files[1]].keys())):
        print k1, k2, all_probes[output_files[0]][k1], all_probes[output_files[1]][k2]
