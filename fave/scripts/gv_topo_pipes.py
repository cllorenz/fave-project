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
    def __init__(self, use_pipes, use_topology, use_policy,
                 json_tables, json_policy, json_topology, json_pipes, **kwargs):
        """
        Class to build a graph of a netplumber topology and pipes
        
        use_pipes: pipes are printed in a subgraph
        use_slice: slices are printed in a subgraph, implies use pipes
        use_topology: topology information is printed in a subgraph separate from pipes
        json_*: required netplumber dump information to build the graphs
        """
        self.use_pipes = use_pipes
        self.use_topology = use_topology
        self.use_policy = use_policy
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
        self.colors = kwargs.get('colors', 'set19')
        self.format = kwargs.get('type', 'pdf')
        self.use_masks = kwargs.get('use_masks', False)
        self.graph = Digraph(
            format=self.format,
            edge_attr= { 'arrowhead': 'open'}
        )
        self.tgraph = Digraph(name='cluster1')
        self.pgraph = Digraph(name='cluster2')
        self.sgraph = Digraph(name='cluster3')
        self.fgraph = Digraph(name='cluster4')
        self.graph.attr(rankdir='LR')

    def build(self):
        """ render subgraph with pipes and slices """
        self.__build_policy()
        self.__build_tables()
        self.__build_topology()
        self.__build_pipes()
        self.__build_slices()
        self.__build_flows()

        self.graph.subgraph(self.fgraph)
        self.graph.subgraph(self.sgraph)
        self.graph.subgraph(self.pgraph)            
        self.graph.subgraph(self.tgraph)

    def __build_policy(self):
        if not (self.use_policy):
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
        if not (self.json_tables):
            raise MissingData('Missing Tables')

        i=0
        for table in self.json_tables:
            tgraph = Digraph(name = 'cluster1_' + str(i))
            tgraph.attr(rankdir='TD', label='Table '+str(table['id']),
                        labelloc = 't', labeljust='l')
            for port in table['ports']:
                tgraph.node('port'+str(port), label=str(port), shape='circle')

            j=0
            """ TODO(jan): check whether to include rewrite as table row """ 
            for rule in table['rules']:
                rewrite = ''
                if 'rewrite' in rule:
                    rewrite = '<TR><TD align="right">rewrite:</TD><TD>'+rule['rewrite']+'</TD></TR>'
                mask = ''
                if self.use_masks: 
                    mask = '<TR><TD align="right">mask:</TD><TD>' + rule['mask'] + '</TD></TR>'
                tgraph.node('rule'+str(i)+str(j), '''<
                <TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">
                <TR><TD align="right">match:</TD><TD>''' + rule['match'] + '''</TD></TR>'''+
                mask+rewrite+'''
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
        if not (self.use_topology):
            return
        if not json_topology:
            raise MissingData('Missing Topology')

        for link in json_topology['topology']:
            self.tgraph.edge('port'+str(link['src']), 'port'+str(link['dst']))
        

    def __build_pipes(self):
        if not(self.use_pipes):
            return
        if not(self.json_pipes):
            raise MissingData('Missing Pipes')

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

    def __build_slices(self):
        if not(self.use_slices):
            return
        if not(self.json_slices):
            raise MissingData('Missing Slices')

        nodes = set([])
        for slice in self.json_slices['pipes']:
            start  = slice[0]
            sid = 'slice' + str(start)
            if sid not in nodes:
                self.sgraph.node(sid, label=str(start), shape='rectangle')
                nodes.add(sid)
            for target in slice[1:]:
                tid = 'slice' + str(target['node_id'])
                if tid not in nodes:
                    self.sgraph.node(tid, label=str(target['node_id']), shape='rectangle')
                    nodes.add(tid)
                """ TODO(jan): treat overflow condition """
                c = '/'+self.colors+'/'+str(target['slice_id']+1)
                self.sgraph.edge(
                    sid,tid,
                    color=c+':invis:'+c,style='dashed', penwidth='1')

    def __build_flows(self):
        if not(self.use_flows):
            return
        if not(self.json_flows):
            raise MissingData('Missing Flows')

        nodes = set([])
        for flow in self.json_flows['flows']:
            start = flow[0]
            color = '#%06x' % (hash(str(start)) & 0xffffff)

            if 'flow'+str(start) not in nodes:
                self.fgraph.node('flow'+str(start), label=str(start), shape='rectangle')
                nodes.add('flow'+str(start))
            for target in flow[1:]:
                if 'flow'+str(target) not in nodes:
                    self.fgraph.node('flow'+str(target), label=str(target), shape='rectangle')
                    nodes.add('flow'+str(target))
                self.fgraph.edge('flow'+str(start), 'flow'+str(target), color=color, style='bold')
                start = target

    def render(self, filename):
        """ outputs the rendered graph """
        self.graph.render(filename, view=False)

def _print_help():
    print 'usage: python2 ' + os.path.basename(__file__) + ' [-hpst] [-d <dir]'
    print
    print '\t-h this help message'
    print '\t-m includes masks'
    print '\t-f include flows'
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
        opts = getopt.getopt(sys.argv[1:], 'hd:fprst')[0]
    except getopt.GetoptError:
        print 'Unable to parse options.'
        sys.exit(1)

    use_dir = 'np_dump'
    use_masks = False
    use_pipes = False
    use_slice = False
    use_policy = False
    use_topology = False
    use_flows = False

    for opt, arg in opts:
        if opt == '-h':
            _print_help()
            sys.exit(0)
        elif opt == '-m':
            use_masks = True
        elif opt == '-f':
            use_flows = True
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
    json_slices   = _read_files(use_dir, 'slice')
    json_flows    = _read_files(use_dir, 'flows')

    gb = topologyRenderer(
        use_pipes, use_topology, use_policy,
        json_tables, json_policy, json_topology, json_pipes,
        use_slices=use_slice, json_slices=json_slices,
        use_flows=use_flows, json_flows=json_flows, use_masks=use_masks)
    gb.build()
    gb.render('out')
