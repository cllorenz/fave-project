#!/usr/bin/env python2

""" This module provides functionality to visualize FaVe and NetPlumber dumps in
    several degrees of granularity.
"""

import json
import os
import sys
import getopt

from graphviz import Digraph

_POSITION = lambda g: len(g.body) - 1

# read tables
def _read_tables(graph, n_map, table_files, fave_tables, fave_ports, use_topology):
    for table_file in table_files:
        with open(table_file, 'r') as ifile:
            table = json.loads(ifile.read())

            # add table and ports to graph
            t_id = table['id'] << 32

            t_name = fave_tables[str(table['id'])]
            g_t = Digraph(name=t_name)

            if use_topology:
                for p_id in table['ports']:
                    graph.node(str(p_id), label=fave_ports[str(p_id)], shape='circle')
                    n_map[p_id] = _POSITION(graph)

                    g_t.edge(
                        str(p_id),
                        fave_tables[str(table['id'])],
                        dir='none',
                        color='black'
                    )

            if table['rules']:
                l_id = table['rules'][0]['id']
                g_t.node(
                    str(l_id),
                    label="%s_%s\n(%s)" % (t_name, 1, l_id),
                    shape='rectangle'
                )
                n_map[l_id] = _POSITION(graph)

                g_t.edge(str(l_id), fave_tables[str(table['id'])], style='invis')


            for idx, rule in enumerate(table['rules'][1:]):
                r_id = rule['id']
                g_t.node(
                    str(r_id),
                    label="%s_%s\n(%s)" % (t_name, idx+2, r_id),
                    shape='rectangle'
                )
                n_map[r_id] = _POSITION(graph)

                g_t.edge(str(r_id), str(l_id), style='invis')
                l_id = r_id

            graph.subgraph(g_t)


def _read_policy(graph, n_map, fdir, fave_ports, use_topology):
    with open(fdir + '/policy.json') as ifile:
        policy = json.loads(ifile.read())

        # add sources and probes to graph
        for idx, node in enumerate(policy['commands']):
            is_source = node['method'] == 'add_source'

            shape = 'triangle' if is_source else 'invtriangle'

            ports = node['params']['ports']
            port_label = fave_ports[str(ports[0])].split('_')
            label = '_'.join(port_label[:len(port_label)-1])

            graph.node(str(idx+1), label=label, shape=shape)
            n_map[idx+1] = _POSITION(graph)

            if not use_topology:
                continue

            for port in ports:
                graph.node(str(port), label=fave_ports[str(port)], shape='circle')
                n_map[port] = _POSITION(graph)

                graph.edge(str(port), str(idx+1), dir='none', color='black')


def _read_topology(graph, fdir, use_topology):
    if not use_topology:
        return

    with open(fdir + '/topology.json') as ifile:
        topo = json.loads(ifile.read())

        # add links between ports
        for link in topo['topology']:
            graph.edge(str(link['src']), str(link['dst']), color='green', style='dashed')


def _read_pipes(graph, n_map, fdir, use_pipes):
    if not use_pipes:
        return

    with open(fdir + '/pipes.json') as ifile:
        pipes = json.loads(ifile.read())

        for pipe in pipes['pipes']:
            start = pipe[0]
            if start not in n_map:
                print 'pipes: unknown node: %s' % start
                graph.node(str(start), label=str(start), shape='rectangle')
                n_map[str(start)] = _POSITION(graph)

            for target in pipe[1:]:
                if target not in n_map:
                    print 'pipes: unknown node: %s'  % target
                    graph.node(str(target), label=str(target), shape='rectangle')
                    n_map[str(target)] = _POSITION(graph)

                graph.edge(
                    str(start),
                    str(target),
                    color='red:invis:red',
                    style='dashed',
                    penwidth='1'
                )


def _traverse_flow(graph, n_map, flow, color):
    if not flow:
        return

    start = flow['node']
    if start not in n_map:
        print 'flows: unknown node: %s' % start
        graph.node(str(start), label=str(start), shape='rectangle')
        n_map[start] = _POSITION(graph)

    if 'children' not in flow:
        return

    for child in flow['children']:
        target = child['node']

        if target not in n_map:
            print 'flows: unknown node: %s' % target

            graph.node(str(target), label=str(target), shape='rectangle')
            n_map[target] = _POSITION(graph)

        graph.edge(str(start), str(target), color=color, style='bold')

        _traverse_flow(graph, n_map, child, color)


def _read_flows(graph, n_map, fdir, use_flows):
    if not use_flows:
        return


    with open(fdir + '/flow_trees.json') as ifile:
        flows = json.loads(ifile.read())

        for flow in flows['flows']:
            color = '#%06x' % (hash(str(flow['node'])) & 0xffffff)
            _traverse_flow(graph, n_map, flow, color)


def _print_help():
    print "usage: python2 gv_np.py [-hfpt] [-d <dir>]"
    print "\t-h this help message"
    print "\t-f include flows"
    print "\t-p include pipes"
    print "\t-t include topology"
    print "\t-d <dir> directory of a fave dump"


if __name__ == '__main__':
    try:
        ONLY_OPTS = lambda x: x[0]
        OPTS = ONLY_OPTS(getopt.getopt(sys.argv[1:], "hd:fpt"))
    except getopt.GetoptError:
        _print_help()
        sys.exit(1)

    FDIR = "np_dump"
    USE_FLOWS = False
    USE_PIPES = False
    USE_TOPOLOGY = False

    for OPT, ARG in OPTS:
        if OPT == '-h':
            _print_help()
            sys.exit(0)

        elif OPT == '-d':
            FDIR = ARG.rstrip('/')

        elif OPT == '-f':
            USE_FLOWS = True

        elif OPT == '-p':
            USE_PIPES = True

        elif OPT == '-t':
            USE_TOPOLOGY = True

        else:
            print "no such option: %s" % OPT
            _print_help()
            sys.exit(2)

    GRAPH = Digraph(
        format='svg',
        edge_attr={
            'arrowhead':'open'
        }
    )

    TABLE_FILES = os.popen('ls -1 %s/*.tf.json' % FDIR).read().rstrip().split("\n")

    N_MAP = {}

    #fave_generators = {}
    #fave_probes = {}
    #fave_rules = {}
    FAVE_TABLES = {}
    #fave_mapping = {}
    FAVE_PORTS = {}

    # read fave infos
    with open(FDIR + '/fave.json', 'r') as f:
        FAVE = json.loads(f.read())

        #fave_generators = FAVE['id_to_generator']
        #fave_probes = FAVE['id_to_probe']
        #fave_rules = FAVE['id_to_rule']
        FAVE_TABLES = FAVE['id_to_table']
        #fave_mapping = FAVE['mapping']
        FAVE_PORTS = FAVE['id_to_port']

    _read_tables(GRAPH, N_MAP, TABLE_FILES, FAVE_TABLES, FAVE_PORTS, USE_TOPOLOGY)
    _read_policy(GRAPH, N_MAP, FDIR, FAVE_PORTS, USE_TOPOLOGY)
    _read_topology(GRAPH, FDIR, USE_TOPOLOGY)
    _read_pipes(GRAPH, N_MAP, FDIR, USE_PIPES)
    _read_flows(GRAPH, N_MAP, FDIR, USE_FLOWS)

    GRAPH.render('np', cleanup=True)

    os.popen('inkscape --export-pdf=np.pdf np.svg')
