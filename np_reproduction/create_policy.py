#!/usr/bin/env python2

import json
import random
random.seed(1)
import sys

src_dir = sys.argv[1]
dst_dir = src_dir

config_json = json.load(open("%s/config.json" % src_dir))
tables = config_json["tables"]
hdr_len = config_json["length"]

commands = []

table_out_json = {
#    table : json.load(open("%s/%s.tf.json" % (src_dir, table))) for table in tables
    table : json.load(open("%s/%s.out.rules.json" % (src_dir, table))) for table in tables
}

table_in_json = {
    table : json.load(open("%s/%s.in.rules.json" % (src_dir, table))) for table in tables
}

topology_json = json.load(open("%s/topology.json" % src_dir))

table_out_ports = {
    table : [p for p in table_out_json[table]['ports'] if p != tid*100000+20000 and p < tid*100000+30000] for tid, table in enumerate(tables, start=1)
}

table_in_ports = {
    table : [p for p in table_in_json[table]['ports'] if p != tid*100000] for tid, table in enumerate(tables, start=1)
}

table_used_in_ports = {}
for table, json_table in table_in_json.iteritems():
    used_in_ports = set()
    for rule in json_table['rules']:
        used_in_ports.update(set(rule['in_ports']))

    table_used_in_ports[table] = used_in_ports

topology_used_in_ports = set(
    [l['dst'] for l in topology_json['topology']]
)

random_in_port = {
#    table : random.choice(table_in_ports[table]) for table in tables
    table : random.choice(list(table_used_in_ports[table] - topology_used_in_ports)) for table in tables
}

first_in_port = {
    table : table_in_ports[table][0] for table in tables
}

table_used_out_ports = {}
for table, json_table in table_out_json.iteritems():
    used_out_ports = set()
    for rule in json_table['rules']:
        used_out_ports.update(set(rule['out_ports']))

    table_used_out_ports[table] = used_out_ports

topology_used_out_ports = set(
    [l['src'] for l in topology_json['topology']]
)

probes = {
    table : [
        (10000+tid*100+pid, 10000+tid*100+pid) for pid in range(1, len(tables)+1)
    ] for tid, table in enumerate(tables, start=1)
}
sources = {
    table : (20000+tid*100, 20000+tid*100) for tid, table in enumerate(tables, start=1)
}

# add and connect probes
source_commands = []
for tid, table in enumerate(tables, start=1):
    table_ports = table_out_ports[table]
    table_probes = probes[table]

    for table, table_probe in zip(tables, table_probes):
#        _sid, source_port = sources[table]
        source_port = first_in_port[table]
        pid, probe_port = table_probe
        source_commands.append({
            "method" : "add_source_probe",
            "params" : {
                "filter" : { "type" : "true" },
				"match" : ','.join(["xxxxxxxx"]*hdr_len),
				"ports" : [ probe_port ],
				"test" :
				{
                    "type" : "true"
#					"type" : "path",
#                    "pathlets" : [
#                        {
#                            "type" : "last_ports",
#                            "ports" : [ source_port ]
#                        }
#                    ]
				},
                "mode" : "existential",
                "id" : pid
            },
        })

        # connect all egress ports to probe
        for table_port in table_out_ports[table]: #(table_used_out_ports[table] - topology_used_out_ports):
            source_commands.append({
                "method" : "add_link",
                "params" : {
                    "from_port" : table_port,
                    "to_port" : probe_port
                }
            })


# add and connect sources
for tid, table in enumerate(tables, start=1):
    table_ports = table_in_ports[table]
    sid, source_port = sources[table]

    commands.append({
		"method" : "add_source",
		"params" :
		{
			"hs" : {
                "list" : [ ','.join(["xxxxxxxx"]*hdr_len) ],
                "diff" : []
            },
            "ports" : [ source_port ],
            "id" : sid
		},
	})

    # connect source to one random ingress port
    table_port = first_in_port[table] #random_in_port[table] #random.choice(table_ports)
#    for table_port in table_ports:
    commands.append({
        "method" : "add_link",
        "params" : {
            "from_port" : source_port,
            "to_port" : table_port
        }
    })

commands.extend(source_commands)

json.dump({ 'commands' : commands }, open("%s/policy.json" % src_dir, 'w'), indent=2)
