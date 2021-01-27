#!/usr/bin/env python2

import json

tables = [
  "atla",
  "chic",
  "hous",
  "kans",
  "losa",
  "newy32aoa",
  "salt",
  "seat",
  "wash"
]

policy = []
for idx, table_name in enumerate(tables, start=1):
    table = json.load(open("i2-hassel/" + table_name + ".tf.json" , "r"))

    policy.append({
        "method" : "add_source",
        "params" : {
            "hs" : {
                "list" : ["xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx"],
                "diff" : []
            },
            "ports" : [idx]
        }
    })

    for port in [p for p in table["ports"] if str(p)[1] != "2"]:
        policy.append({
            "method" : "add_link",
            "params" : {
                "from_port" : idx,
                "to_port" : port
            }
        })

json.dump(
  {
    "commands" : policy
  },
  open("i2-hassel/policy.json", "w"),
  indent=2
)
