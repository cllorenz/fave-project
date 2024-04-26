#!/usr/bin/env python3

import json
from xml.dom import minidom

root = minidom.parse("bench/wl_i2/i2/show_interfaces.xml")

routers = {}
aenets = {}
xrouters = root.getElementsByTagName("router")

for xrouter in xrouters:
    router_name = xrouter.getAttribute("name")
    routers[router_name] = []
    xinterfaces = xrouter.getElementsByTagName("physical-interface")
    for xinterface in xinterfaces:
        xif_names = xinterface.getElementsByTagName("name")
        for xif_name in xif_names:
            if_name = xif_name.childNodes[0].data.split(".")[0]
            if if_name not in routers[router_name]:
                routers[router_name].append(if_name)

        xlogical_interfaces = xinterface.getElementsByTagName("logical-interface")
        for xlogical_interface in xlogical_interfaces:
            xlif_names = xlogical_interface.getElementsByTagName("name")
            for xlif_name in xlif_names:
                lif_name = xlif_name.childNodes[0].data
                xaddr_fams = xlogical_interface.getElementsByTagName("address-family")
                for xaddr_fam in xaddr_fams:
                    addr_fam_name = xaddr_fam.getElementsByTagName("address-family-name")[0].childNodes[0].data
                    if addr_fam_name == 'aenet':
                        bundle_name = xaddr_fam.getElementsByTagName("ae-bundle-name")[0].childNodes[0].data
                        aenets.setdefault(router_name, {})
                        aenets[router_name].setdefault(bundle_name, [])
                        aenets[router_name][bundle_name].append(lif_name)


with open("bench/wl_i2/i2_tfs/routers.json", "w") as pf:
    jrouters = [{'name' : n, 'ports' : p} for n, p in list(routers.items())]
    pf.write(json.dumps({'routers' : jrouters}, indent=2))

with open("bench/wl_i2/i2_tfs/bundles.json", "w") as bf:
    bf.write(json.dumps(aenets, indent=2))

rev_port_map = {}
with open("bench/wl_i2/i2/port_map.txt", "r") as pf:
    lines = pf.read().splitlines()
    router_name = ""
    for line in lines:
        if line.startswith("$"):
            router_name = line[1:]
        elif line == '':
            continue
        else:
            port, no = line.split(':')
            rev_port_map[no] = "%s:%s" % (router_name, port)

topology = []
with open("bench/wl_i2/i2/backbone_topology.tf", "r") as tf:
    lines = tf.read().splitlines()

    for line in lines:
        try:
            _, src, _, _, _, _, _, dst, _, _, _, _, _, _ = line.split('$')
        except:
            print(('not parseable:', line))
            continue

        src = src.strip('[]')
        src = rev_port_map[src[0] + "0" + src[2:]]
        dst = rev_port_map[dst.strip('[]')]

        topology.append({'src' : src, 'dst' : dst})


with open("bench/wl_i2/i2/topology_names.json", "w") as tf:
    tf.write(json.dumps({'topology' : topology}, indent=2))
