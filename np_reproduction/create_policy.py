#!/usr/bin/env python2

import json
import sys

src_dir = sys.argv[1]
dst_dir = src_dir

config_json = json.load(open("%s/config.json" % src_dir))
with_paths = config_json.get("with_paths", False)
tables = config_json["tables"]
hdr_len = config_json["length"]

commands = []

table_out_json = {
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

first_in_port = {
    table : table_in_ports[table][0] for table in tables
}

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
        _sid, source_port = sources[table]
        source_port = first_in_port[table]
        pid, probe_port = table_probe
        source_commands.append({
            "method" : "add_source_probe",
            "params" : {
                "filter" : { "type" : "true" },
				"match" : ','.join(["xxxxxxxx"]*hdr_len),
				"ports" : [ probe_port ],
				"test" : # complex expression if paths should be checked
				{
					"type" : "path",
                    "pathlets" : [
                        {
                            "type" : "last_ports",
                            "ports" : [ source_port ]
                        }
                    ]
				} if with_paths else { "type" : "true" },
                "mode" : "existential",
                "id" : pid
            },
        })

        # connect all egress ports to probe
        for table_port in table_out_ports[table]:
            source_commands.append({
                "method" : "add_link",
                "params" : {
                    "from_port" : table_port,
                    "to_port" : probe_port
                }
            })

        # skip further probes if just the simple check is used
        if not with_paths: break


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

    # connect source to first ingress port
    table_port = first_in_port[table]
    commands.append({
        "method" : "add_link",
        "params" : {
            "from_port" : source_port,
            "to_port" : table_port
        }
    })

commands.extend(source_commands)

json.dump({ 'commands' : commands }, open("%s/policy.json" % src_dir, 'w'), indent=2)
