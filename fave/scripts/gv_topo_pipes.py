#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2019 Jan Sohre
# List of co-authors:
#    Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

""" This module provide functionality to draw a netplumber network.
"""

import os
import sys
import json
import glob
import argparse

from util.ip6np_util import bitvector_to_field_value
from netplumber.vector import get_field_from_vector
from netplumber.mapping import Mapping

from graphviz import Digraph

class MissingData(Exception):
    """ Placeholder class to specifically name failure conditions """
    def __init__(self, message):
        super(MissingData, self).__init__(message)


class TopologyRenderer(object):
    """ This class builds a graph from a netplumber topology and pipes.
    """

    def __init__(
            self,
            use_fave,
            use_pipes,
            use_policy,
            use_tables,
            use_topology,
            json_tables,
            json_policy,
            json_topology,
            json_pipes,
            **kwargs
        ):
        """
        Class to build a graph of a netplumber topology and pipes

        use_pipes: pipes are printed in a subgraph
        use_slice: slices are printed in a subgraph, implies use pipes
        use_topology: topology information is printed in a subgraph separate from pipes
        json_*: required netplumber dump information to build the graphs
        """
        self.use_fave = use_fave
        self.use_pipes = use_pipes
        self.use_policy = use_policy
        self.use_tables = use_tables
        self.use_topology = use_topology
        self.json_tables = json_tables
        self.json_policy = json_policy
        self.json_topology = json_topology
        self.json_pipes = json_pipes
        """
        optional parameters for slices
        """
        self.use_slices = kwargs.get('use_slices', False)
        self.json_slices = kwargs.get('json_slices', None)
        self.use_flows = kwargs.get('use_flows', False)
        self.json_flows = kwargs.get('json_flows', None)
        self.use_flow_trees = kwargs.get('use_flow_trees', False)
        self.json_flow_trees = kwargs.get('json_flow_trees', None)
        self.colors = kwargs.get('colors', 'set19')
        self.format = kwargs.get('type', 'pdf')
        self.use_verbose = kwargs.get('use_verbose', False)

        self.rule_labels = {}
        self.graph = Digraph(
            format=self.format,
            edge_attr={'arrowhead': 'open'}
        )
        self.tgraph = Digraph(name='cluster1')
        self.pgraph = Digraph(name='cluster2')
        self.sgraph = Digraph(name='cluster3')
        self.fgraph = Digraph(name='cluster4')
        self.ftgraph = Digraph(name='cluster5')
        self.graph.attr(rankdir='LR')

        if use_fave:
            self.fave = kwargs.get('json_fave', None)
            self.fave_mapping = Mapping.from_json(self.fave['mapping'])


    def build(self):
        """ render subgraph with pipes and slices """
        self.__build_policy()
        self.__build_rule_labels()
        self.__build_tables()
        self.__build_topology()
        self.__build_pipes()
        self.__build_slices()
        self.__build_flows()
        self.__build_flow_trees()

        self.graph.subgraph(self.fgraph)
        self.graph.subgraph(self.sgraph)
        self.graph.subgraph(self.pgraph)
        self.graph.subgraph(self.tgraph)
        self.graph.subgraph(self.ftgraph)

    def __build_policy(self):
        if not self.use_policy:
            return
        if not self.json_policy:
            raise MissingData('Missing Policies')

        for i, probe in enumerate(self.json_policy['commands'], 1):
            source = probe['method'] == 'add_source'
            shape = 'triangle' if source else 'invtriangle'
            label = ('S' if source else 'P')+str(i)

            ports = probe['params']['ports']
            self.tgraph.node('s'+str(i), label=label, shape=shape)
            for port in ports:
                self.tgraph.node('port'+str(port), label=str(port))
                if source:
                    self.tgraph.edge('s'+str(i), 'port'+str(port))
                else:
                    self.tgraph.edge('port'+str(port), 's'+str(i))


    def _build_rule_label(self, rule):
        TABLE_START = '<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">'
        TABLE_END = '</TABLE>'
        build_row = lambda x, y: \
            '<TR><TD ALIGN="RIGHT">%s</TD><TD ALIGN="LEFT">%s</TD></TR>' % (x, y)

        rule_id = rule['id']
        row_id = build_row('id:', hex(rule_id))

        row_position = build_row('position', rule['position'])

        row_match = build_row(
            'match:', self._readable_vector(rule['match'], printable=True)
        ) if self.use_verbose else ''

        row_mask = build_row(
            'mask:', self._readable_vector(rule['mask'], ignore_bit='0', printable=True)
        ) if 'mask' in rule and self.use_verbose else ''

        row_rewrite = build_row(
            'rewrite:', self._readable_vector(rule['rewrite'], printable=True)
        ) if 'rewrite' in rule and self.use_verbose else ''

        row_influences = build_row(
            'influences', _break_list_table(
                map(
                    lambda inf: self._readable_vector(inf, printable=True),
                    rule['influences'].split(' + ')
                )
            )
        ) if 'influences' in rule and self.use_verbose else ''

        row_label = "<%s%s%s%s%s%s%s%s>" % (
            TABLE_START,
            row_id,
            row_position,
            row_match,
            row_mask,
            row_rewrite,
            row_influences,
            TABLE_END
        )

        if rule_id not in self.rule_labels:
            self.rule_labels[rule_id] = row_label

        return row_label

    def _build_table_label(self, tid):
        if not self.use_fave:
            return 'Table ' + hex(tid)
        else:
            return 'Table %s (%s)' % (self.fave['id_to_table'][str(tid)], hex(tid))


    def _build_port_label(self, port):
        if not self.use_fave:
            return str(port)
        else:
            label = self.fave['id_to_port'][str(port)].split('_')
            return label[len(label)-1]


    def __build_rule_labels(self):
        for i, table in enumerate(self.json_tables):
            for j, rule in enumerate(table['rules']):
                rule_id = rule['id']
                if rule_id not in self.rule_labels:
                    label = self._build_rule_label(rule) if self.use_verbose else hex(rule_id)
                    self.rule_labels[rule_id] = label


    def __build_tables(self):
        if not self.use_tables:
            return
        if not self.json_tables:
            raise MissingData('Missing Tables')

        for i, table in enumerate(self.json_tables):
            tgraph = Digraph(name='cluster1_' + str(i))
            tlabel = self._build_table_label(table['id'])
            tgraph.attr(rankdir='TD', label=tlabel,
                        labelloc='t', labeljust='l')
            for port in table['ports']:
                tgraph.node('port'+str(port), label=str(port), shape='circle')

            for j, rule in enumerate(table['rules']):
                rule_id = rule['id']
                label = self.rule_labels[rule_id]

                tgraph.node(
                    "rule_%s_%s" % (i, j),
                    label=label,
                    shape='rectangle'
                )

                for in_port in rule['in_ports']:
                    tgraph.edge('port'+str(in_port), 'rule_%s_%s' % (i, j))

                for out_port in rule['out_ports']:
                    tgraph.edge('rule_%s_%s' % (i, j), 'port'+str(out_port))


            self.tgraph.subgraph(tgraph)

            # action may be:
            #    fwd - forward
            #    rw  - rewrite
            #    encap - encapsulate

    def __build_topology(self):
        if not self.use_topology:
            return
        if not self.json_topology:
            raise MissingData('Missing Topology')

        for link in self.json_topology['topology']:
            self.tgraph.edge('port'+str(link['src']), 'port'+str(link['dst']))


    def __build_pipes(self):
        if not self.use_pipes:
            return
        if not self.json_pipes:
            raise MissingData('Missing Pipes')

        nodes = set([])
        for pipe in self.json_pipes['pipes']:
            start = pipe[0]
            sid = 'pipe' + str(start)
            if sid not in nodes:
                slabel = self.rule_labels.get(start, hex(start))
                self.pgraph.node(sid, label=slabel, shape='rectangle')
                nodes.add(sid)
            for target in pipe[1:]:
                node = target['node']
                tid = 'pipe' + str(node)
                if tid not in nodes:
                    tlabel = self.rule_labels.get(node, hex(node))
                    self.pgraph.node(tid, label=tlabel, shape='rectangle')
                    nodes.add(tid)

                label = "<%s>" % _break_list_table(
                    map(
                        lambda fil: self._readable_vector(fil, printable=True),
                        target['filter'].split(' + ')
                    )
                ) if self.use_verbose else ''

                self.pgraph.edge(
                    sid,
                    tid,
                    label=label,
                    color='red:invis:red',
                    style='dashed',
                    penwidth='1'
                )

    def __build_slices(self):
        if not self.use_slices:
            return
        if not self.json_slices:
            raise MissingData('Missing Slices')

        nodes = set([])
        for np_slice in self.json_slices['pipes']:
            start = np_slice[0]
            sid = 'slice' + str(start)
            if sid not in nodes:
                slabel = self.rule_labels.get(start, hex(start))
                self.sgraph.node(sid, label=slabel, shape='rectangle')
                nodes.add(sid)
            for target in np_slice[1:]:
                tid = 'slice' + str(target['node_id'])
                if tid not in nodes:
                    tlabel = self.rule_labels.get(target['node_id'], hex(target['node_id']))
                    self.sgraph.node(tid, label=tlabel, shape='rectangle')
                    nodes.add(tid)
                # TODO(jan): treat overflow condition
                col = '/'+self.colors+'/'+str(target['slice_id']+1)
                self.sgraph.edge(
                    sid,
                    tid,
                    color=col+':invis:'+col,
                    style='dashed',
                    penwidth='1'
                )

    def __build_flows(self):
        if not self.use_flows:
            return
        if not self.json_flows:
            raise MissingData('Missing Flows')

        nodes = set([])
        for flow in self.json_flows['flows']:
            start = flow[0]
            color = '#%06x' % (hash(str(start)) & 0xffffff)

            if 'flow'+str(start) not in nodes:
                slabel = self.rule_labels.get(start, hex(start))
                self.fgraph.node('flow'+str(start), label=slabel, shape='rectangle')
                nodes.add('flow'+str(start))
            for target in flow[1:]:
                if 'flow'+str(target) not in nodes:
                    tlabel = self.rule_labels.get(target, hex(target))
                    self.fgraph.node('flow'+str(target), label=tlabel, shape='rectangle')
                    nodes.add('flow'+str(target))
                self.fgraph.edge('flow'+str(start), 'flow'+str(target), color=color, style='bold')
                start = target


    def _traverse_flow(self, n_map, flow, color):
        _POSITION = lambda g: len(g.body) - 1

        if not flow:
            return

        start = flow['node']
        if start not in n_map:
            slabel = self.rule_labels.get(start, hex(start))
            self.ftgraph.node(str(start), label=slabel, shape='rectangle')
            n_map[start] = _POSITION(self.ftgraph)

        if 'children' not in flow:
            return

        for child in flow['children']:
            target = child['node']

            if target not in n_map:
                tlabel = self.rule_labels[target] if target in self.rule_labels else hex(target)
                self.ftgraph.node(str(target), label=tlabel, shape='rectangle')
                n_map[target] = _POSITION(self.ftgraph)

            if self.use_verbose and 'flow' in child:
                hs_list, hs_diff = self._readable_vectors(child['flow'])

                label = _break_list_nl(hs_list)
                if hs_diff:
                    label += '\n - (%s)' % _break_list_nl(hs_diff)

            else:
                label = ''

            self.ftgraph.edge(
                str(start),
                str(target),
                label=label,
                color=color,
                style='bold'
            )

            self._traverse_flow(n_map, child, color)


    def __build_flow_trees(self):
        if not self.use_flow_trees:
            return
        if not self.json_flow_trees:
            raise MissingData('Missing Flow Trees')

        _POSITION = lambda g: len(g.body) - 1

        n_map = {}
        for flow in self.json_flow_trees['flows']:
            start = flow['node']
            if start not in n_map:
                slabel = self.rule_labels.get(start, hex(start))
                self.ftgraph.node(str(start), label=slabel, shape='rectangle')
                n_map[start] = _POSITION(self.ftgraph)


#            color = '#%06x' % (hash(str(flow['node'])) & 0xffffff)
#            self._traverse_flow({}, flow, color)
            for idx, child in enumerate(flow['children']):
                color = '#%06x' % (hash(str(child['node'] * child['node'] * (idx+1))) & 0xffffff)

                target = child['node']

                if target not in n_map:
                    tlabel = self.rule_labels[target] if target in self.rule_labels else hex(target)
                    self.ftgraph.node(str(target), label=tlabel, shape='rectangle')
                    n_map[target] = _POSITION(self.ftgraph)


                if self.use_verbose and 'flow' in child:
                    hs_list, hs_diff = self._readable_vectors(child['flow'])

                    label = _break_list_nl(hs_list)
                    if hs_diff:
                        label += '\n - (%s)' % _break_list_nl(hs_diff)

                else:
                    label = ''

                self.ftgraph.edge(
                    str(start),
                    str(target),
                    label=label,
                    color=color,
                    style='bold'
                )

                self._traverse_flow(n_map, child, color)


    def _readable_vectors(self, hs):
        hs_diff = None
        try:
            hs_list, hs_diff = hs.split(' - ')
            hs_list = hs_list.strip('()')
            hs_diff = hs_diff.strip('()')
        except:
            hs_list = hs

#        hs_list = hs['list']
#        hs_diff = hs['diff']

#        res_list = [self._readable_vector(vec, printable=True) for vec in hs_list]
        res_list = [self._readable_vector(vec, printable=True) for vec in hs_list.split(' + ')]

        res_diff = []
        if hs_diff:
#            res_diff = [self._readable_vector(vec, printable=True) for vec in hs_diff]
            res_diff = [self._readable_vector(vec, printable=True) for vec in hs_diff.split(' + ')]

        return res_list, res_diff


    def _readable_vector(self, vector, **kwargs):
        res = []
        vec = ''.join(vector.split(','))

        for field, offset in self.fave_mapping.iteritems():
            binary = get_field_from_vector(self.fave_mapping, vec, field)
            readable = bitvector_to_field_value(binary, field, **kwargs)
            if readable:
                res.append("%s=%s" % (field, readable))

        return ', '.join(res)


    def render(self, filename):
        """ outputs the rendered graph """
        self.graph.render(filename, view=False)


def _break_list_inline(rows, row_func, lrow_func):
    if len(rows) == 1:
        res = [lrow_func('', rows[0])]
    else:
        res = [row_func('', rows[0])]

    if len(rows) > 2:
        res += [row_func('+ ', row) for row in rows[1:-1]]

    if len(rows) > 1:
        res += [lrow_func('+ ', rows[-1])]

    return res


def _break_list_table(rows):
    TABLE_START = '<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">'
    TABLE_END = '</TABLE>'

    build_row = lambda prefix, x: \
        '<TR><TD align="right">%s%s</TD></TR>' % (prefix, x)

    return TABLE_START + ''.join(_break_list_inline(rows, build_row, build_row)) + TABLE_END


def _break_list_nl(rows):
    row_func = lambda prefix, x: prefix + x + '\n'
    lrow_func = lambda prefix, x: prefix + x

    return ''.join(_break_list_inline(rows, row_func, lrow_func))


def _read_tables(ddir):
    """ reads a collection of json files and provides their contents
        as a list
    """
    tables = []
    table_files = glob.glob('%s/*.tf.json' % ddir)
    for table_file in table_files:
        with open(table_file) as ifile:
            tables = tables + [json.loads(ifile.read())]
    return tables

def _read_files(ddir, name):
    """ reads single json files and makes their contents available """
    with open(ddir + '/' + name + '.json') as ifile:
        contents = json.loads(ifile.read())
    return contents

def _read_combine_files(ddir, name):
    """ reads json files and combines their contents """
    flow_trees = []
    flow_tree_files = glob.glob('%s/*.%s.json' % (ddir, name))
    for flow_tree_file in flow_tree_files:
        flow_trees.extend(json.load(open(flow_tree_file, "r"))['flows'])

    return { 'flows' : flow_trees }

if __name__ == '__main__':
    PARSER = argparse.ArgumentParser()

    PARSER.add_argument(
        '-b', '--baeume',
        dest='use_flow_trees',
        action='store_const',
        const=True,
        default=False
    )
    PARSER.add_argument(
        '-f', '--flows',
        dest='use_flows',
        action='store_const',
        const=True,
        default=False
    )
    PARSER.add_argument(
        '-n', '--no-tables',
        dest='use_tables',
        action='store_const',
        const=False,
        default=True
    )
    PARSER.add_argument(
        '-l', '--labels',
        dest='use_fave',
        action='store_const',
        const=True,
        default=False
    )
    PARSER.add_argument(
        '-p', '--policy',
        dest='use_policy',
        action='store_const',
        const=True,
        default=False
    )
    PARSER.add_argument(
        '-r', '--rohre',
        dest='use_pipes',
        action='store_const',
        const=True,
        default=False
    )
    PARSER.add_argument(
        '-s', '--slices',
        dest='use_slices',
        action='store_const',
        const=True,
        default=False
    )
    PARSER.add_argument(
        '-t', '--topology',
        dest='use_topology',
        action='store_const',
        const=True,
        default=False
    )
    PARSER.add_argument(
        '-v', '--verbose',
        dest='use_verbose',
        action='store_const',
        const=True,
        default=False
    )
    PARSER.add_argument(
        '-d', '--dir',
        dest='use_dir',
        default='np_dump'
    )

    ARGS = PARSER.parse_args(sys.argv[1:])

    if not ARGS.use_tables:
        ARGS.use_policy = False
        ARGS.use_topology = False

    # read required data
    JSON_TABLES = _read_tables(ARGS.use_dir)

    JSON_PIPES = _read_files(ARGS.use_dir, 'pipes') if ARGS.use_pipes else None
    JSON_POLICY = _read_files(ARGS.use_dir, 'policy') if ARGS.use_policy else None
    JSON_TOPOLOGY = _read_files(ARGS.use_dir, 'topology') if ARGS.use_topology else None
    JSON_SLICES = _read_files(ARGS.use_dir, 'slice') if ARGS.use_slices else None
    JSON_FLOWS = _read_files(ARGS.use_dir, 'flows') if ARGS.use_flows else None
    JSON_FLOW_TREES = _read_combine_files(ARGS.use_dir, 'flow_tree') if ARGS.use_flow_trees else None
    JSON_FAVE = _read_files(ARGS.use_dir, 'fave') if ARGS.use_fave else None

    GB = TopologyRenderer(
        ARGS.use_fave, ARGS.use_pipes, ARGS.use_policy, ARGS.use_tables, ARGS.use_topology,
        JSON_TABLES, JSON_POLICY, JSON_TOPOLOGY, JSON_PIPES,
        use_slices=ARGS.use_slices, json_slices=JSON_SLICES,
        use_flows=ARGS.use_flows, json_flows=JSON_FLOWS, json_fave=JSON_FAVE,
        use_flow_trees=ARGS.use_flow_trees, json_flow_trees=JSON_FLOW_TREES,
        use_verbose=ARGS.use_verbose
    )
    GB.build()
    GB.render('out')
