#!/usr/bin/env python2

import os
import sys
import json
import glob
import getopt
import subprocess

from graphviz import Digraph

class MissingData(Exception):
    """ Placeholder class to specifically name failure conditions """
    def __init__(self, message):
        super(MissingData, self).__init__(message)

class topologyRenderer(object):
    def __init__(self, use_pipes, use_slice, use_topology, use_policy,
                 json_tables, json_policy, json_topology, json_pipes, **kwargs):
        """
        Class to build a graph of a netplumber topology and pipes
        
        use_pipes: pipes are printed in a subgraph
        use_slice: slices are printed in a subgraph, implies use pipes
        use_topology: topology information is printed in a subgraph separate from pipes
        json_*: required netplumber dump information to build the graphs
        """
        self.use_pipes = use_pipes
        self.use_slice = use_slice
        self.use_topology = use_topology
        self.use_policy = use_policy
        self.json_tables = json_tables
        self.json_policy = json_policy
        self.json_topology = json_topology
        self.json_pipes = json_pipes
        self.format = kwargs.get('type', 'pdf') 
        self.graph = Digraph(
            format=self.format,
            edge_attr= { 'arrowhead': 'open'}
        )
        self.tgraph = Digraph(name='cluster1')
        self.pgraph = Digraph(name='cluster2')
        self.graph.attr(rankdir='LR')

    def build(self):
        """ render subgraph with pipes and slices """
        self.__build_policy()
        self.__build_tables()
        self.__build_topology()
        self.__build_pipes()

        self.graph.subgraph(self.pgraph)            
        self.graph.subgraph(self.tgraph)


    def __build_policy(self):
        if not use_policy:
            return
        if not json_policy:
            raise MissingData('Missing Policies')

        i = 0
        for probe in json_policy['commands']:
            source = probe['method'] == 'add_source'
            shape = 'triangle' if source else 'invtriangle'

            ports = probe['params']['ports']
            self.tgraph.node('s'+str(i), label='S'+str(i), shape=shape)
            for port in ports:
                self.tgraph.node('port'+str(port), label=str(port))
                if source:
                    self.tgraph.edge('s'+str(i), 'port'+str(port))
                else:
                    self.tgraph.edge('port'+str(port), 's'+str(i))

            i = i+1
        
    def __build_tables(self):
        if not json_tables:
            raise MissingData('Missing Tables')

        i=0
        for table in self.json_tables:
            tgraph = Digraph(name = 'cluster1_' + str(i))
            tgraph.attr(rankdir='TD', label='Table '+str(table['id']),
                        labelloc = 't', labeljust='l')
            for port in table['ports']:
                tgraph.node('port'+str(port), label=str(port), shape='circle')

            j=0
            """ TODO: check whether to include rewrite as table row """ 
            for rule in table['rules']:
                tgraph.node('rule'+str(i)+str(j), '''<
                <TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">
                <TR><TD>match:</TD><TD>''' + rule['match'] + '''</TD></TR>
                <TR><TD>mask:</TD><TD>''' + rule['mask'] + '''</TD></TR>
                </TABLE>>''', shape = 'rectangle')
                for ip in rule['in_ports']:
                    tgraph.edge('port'+str(ip), 'rule'+str(i)+str(j))
                for op in rule['out_ports']:
                    tgraph.edge('rule'+str(i)+str(j), 'port'+str(op))
                j=j+1


            self.tgraph.subgraph(tgraph)
            i = i+1

            """ action may be:
                fwd - forward
                rw  - rewrite
                encap - encapsulate
            """
    
    def __build_topology(self):
        if not use_topology:
            return
        if not json_topology:
            raise MissingData('Missing Topology')

        for link in json_topology['topology']:
            self.tgraph.edge('port'+str(link['src']), 'port'+str(link['dst']))
        

    def __build_pipes(self):
        if not(use_pipes or use_slice):
            return

        nodes = set([])
        for pipe in self.json_pipes['pipes']:
            start = pipe[0]
            sid = 'pipe' + str(start)
            if sid not in nodes:
                self.pgraph.node(sid, label=str(start), shape='rectangle')
                nodes.add(sid)
            for target in pipe[1:]:
                tid = 'pipe' + str(target)
                if tid not in nodes:
                    self.pgraph.node(tid, label=str(target), shape='rectangle')
                    nodes.add(tid)
                self.pgraph.edge(
                    sid,tid,
                    color='red:invis:red',style='dashed', penwidth='1')

    def render(self, filename):
        """ outputs the rendered graph """
        self.graph.render(filename, view=False)

def _print_help():
    print 'usage: python2 ' + os.path.basename(__file__) + ' [-hpst] [-d <dir]'
    print
    print '\t-h this help message'
    print '\t-p include policy'
    print '\t-r include pipes'
    print '\t-s include slices'
    print '\t-t include topology'
    print '\t-d <dir> directory of a netplumber dump'
    print

def _read_tables(ddir):
    """ reads a collection of json files and provides their contents
        as a list
    """
    tables = []
    table_files = glob.glob('%s/*.tf.json' % ddir)
    for f in table_files:
        with open(f) as ifile:
            tables = tables + [json.loads(ifile.read())]
    return tables

def _read_files(ddir, name):
    """ reads single json files and makes their contents available """
    with open(ddir + '/' + name + '.json') as ifile:
        contents = json.loads(ifile.read())
    return contents

if __name__ == '__main__':
    try:
        opts = getopt.getopt(sys.argv[1:], 'hd:prst')[0]
    except getopt.GetoptError:
        print 'Unable to parse options.'
        sys.exit(1)

    use_dir = 'np_dump'
    use_pipes = False
    use_slice = False
    use_policy = False
    use_topology = False

    for opt, arg in opts:
        if opt == '-h':
            _print_help()
            sys.exit(0)
        elif opt == '-p':
            use_policy = True
        elif opt == '-r':
            use_pipes = True
            """ r wie rohr """
        elif opt == '-s':
            use_slice = True
        elif opt == '-t':
            use_topology = True
        elif opt == '-d':
            use_dir = arg.rstrip('/')
        else:
            print 'No such option: %s.' % opt
            _print_help()
            sys.exit(2)

    """ read required data """
    json_tables   = _read_tables(use_dir)
    json_pipes    = _read_files(use_dir, 'pipes')
    json_policy   = _read_files(use_dir, 'policy')
    json_topology = _read_files(use_dir, 'topology')

    gb = topologyRenderer(
        use_pipes, use_slice, use_topology, use_policy,
        json_tables, json_policy, json_topology, json_pipes)
    gb.build()
    gb.render('out')
