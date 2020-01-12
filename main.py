#!/usr/bin/env python
import math
from lxml import objectify
import lxml.etree as et
from copy import deepcopy
import os
import subprocess
import sys

from src.sat.satutils import SATUtils as sat
from src.core.instantiator import Instantiator
from src.solver.minisat import MiniSATAdapter
from src.solver.clasp import ClaspAdapter
from src.solver.pycosat import PycoSATAdapter
from pprint import pprint
from src.core.kripke import *
from src.xml.xmlutils import XMLUtils as xml
from src.xml.genutils import GenUtils
from src.xml.trans import Translator as trans

from src.service.service import Service

from src.database.redis import RedisAdapter

from src.generator.generator import Generator

import json

import time

import numpy

class Main:
    def clear(self,elem):
        for child in elem:
            self.clear(child)

        elem.clear()


    def main(self):
        db = RedisAdapter.Instance()

        reach = True
        cycle = True
        shadow = True
        cross = False
        lppreach = True
        lppshadow = True
        end_to_end = True

        firstrun = True

#        f = open('./time.log','w')
#        f.write('inst(total)\tinst(base)\tinst(mean)\tinst(median)\tinst(std)\n')
#        print(self._roots)
        for config in self._roots:
#            print(config)
            results = {}

            XMLUtils.deannotate(config)
            for mode in ['nodb']:#,'db']:
#                print(mode)
#                sys.stdout.flush()
                instantiation = []


                if mode == 'nodb':
                    db.reset()

                print('Instantiate...', end='', flush=True)
                t1 = time.time()
                kripke,encoding = Instantiator.InstantiateBase(config)
                t2 = time.time()
                print(' done', flush=True)
                base = t2-t1
                print('Base instantiation: ' + str(base), flush=True)
                instantiation.append(base)
                print('  nodes: ' + str(len(list(kripke.IterNodes()))), flush=True)
                transitions = []
                for transition in kripke.IterFTransitions():
                    transitions.extend(kripke.IterFTransitions(transition))
                print('  transitions: ' + str(len(transitions)), flush=True)

                """
                if cycle:
                    print('cycle', flush=True)
                    t1 = time.time()
                    instance = Instantiator.InstantiateCycle(kripke,encoding)
                    t2 = time.time()
                    td = t2-t1
                    print('  Instantiation: ' + str(td), flush=True)
                    instantiation.append(td)


                if cross:
                    print('cross', flush=True)
                    t1 = time.time()
                    instance = Instantiator.InstantiateCross(kripke,encoding)
                    t2 = time.time()
                    td = t2-t1
                    print('  Instantiation: ' + str(td), flush=True)
                    instantiation.append(td)


                if reach:
                    print('instantiate reach', flush=True)
                    reach_inst = []
                    for node in kripke.IterNodes():
                        #print(node+'_reach')
                        #sys.stdout.flush()
                        t1 = time.time()

                        instance = Instantiator.InstantiateReach(kripke,encoding,node)
                        t2 = time.time()
                        td = t2-t1
                        #print('Instantiation: ' + str(td))
                        #sys.stdout.flush()
                        instantiation.append(td)
                        reach_inst.append(td)
                    print('  Instantiation: ' + str(sum(reach_inst)), flush=True)


                if shadow:
                    print('instantiate shadow', flush=True)
                    shadow_inst = []
                    for node in kripke.IterNodes():
                        #print(node+'_shadow')
                        #sys.stdout.flush()
                        t1 = time.time()
                        instance = Instantiator.InstantiateShadow(kripke,encoding,{},node)
                        t2 = time.time()
                        td = t2-t1
                        #print('Instantiation: ' + str(td))
                        #sys.stdout.flush()
                        instantiation.append(td)
                        shadow_inst.append(td)
                    print('  Instatiation: ' + str(sum(shadow_inst)), flush=True)

                measstr = '\t'.join([
                    str(sum(instantiation)),
                    str(instantiation[0]),
                    str(numpy.mean(instantiation[1:])),
                    str(numpy.median(instantiation[1:])),
                    str(numpy.std(instantiation[1:])),
                ])
                #f.write(measstr+'\n')

                print('Total instantiation: ' + str(sum(instantiation[1:])))
                print('Avg instantiation: ' + str(numpy.mean(instantiation[1:])))
                print('Median instantiation: ' + str(numpy.median(instantiation[1:])))
                print('Std deviation: ' + str(numpy.std(instantiation[1:])))
                sys.stdout.flush()
                """

            FNULL = open(os.devnull,'w')

            if firstrun:
#                f.write('mini(total)\tmini(mean)\tmini(median)\tmini(std)\tclasp(total)\tclasp(mean)\tclasp(median)\tclasp(std)\n')
                firstrun = False

            solvingm = []
            solvingc = []

            if cycle:
                print('cycle', flush=True)
#                subprocess.call(["./mem.sh",str(os.getpid()),"pre"],stderr=FNULL)
                t1 = time.time()
                instance = Instantiator.InstantiateCross(kripke,encoding)
                t2 = time.time()
                td = t2 - t1
#                subprocess.call(["./mem.sh",str(os.getpid()),"in"],stderr=FNULL)
                print('  Cycle (Instantiation): ' + str(td), flush=True)

                self._solver = PycoSATAdapter()#'/dev/shm/solver.in','/dev/shm/solver.out')
                t1 = time.time()
                results['cycle'] = self._solver.Solve(instance)
                t2 = time.time()
                td = t2-t1
                print('  Cycle (Solving): ' + str(td), flush=True)
#                print('Solving (MiniSAT): ' + str(td))
#                sys.stdout.flush()
#                solvingm.append(td)

#                self._solver = ClaspAdapter('/dev/shm/solver.in')
#                t1 = time.time()
#                results['cycle'] = self._solver.Solve(instance)
#                t2 = time.time()
#                td = t2-t1
#                print('Solving (Clasp): ' + str(td))
#                sys.stdout.flush()
#                solvingc.append(td)

#                subprocess.call(["./mem.sh",str(os.getpid()),"post"],stderr=FNULL)


            if cross:
                print('cross', flush=True)
#                subprocess.call(["./mem.sh",str(os.getpid()),"pre"],stderr=FNULL)
                t1 = time.time()
                instance = Instantiator.InstantiateCross(kripke,encoding)
                t2 = time.time()
                td = t2 - t1
#                subprocess.call(["./mem.sh",str(os.getpid()),"in"],stderr=FNULL)
                print('  Cross (Instantiation): ' + str(td), flush=True)

#                self._solver = MiniSATAdapter('/dev/shm/solver.in','/dev/shm/solver.out')
                t1 = time.time()
                results['cross'] = self._solver.Solve(instance)
                t2 = time.time()
                td = t2 - t1
                print('  Cross (Solving): ' + str(td), flush=True)
#                print('Solving (MiniSAT): ' + str(td))
#                sys.stdout.flush()
#                solvingm.append(td)

#                self._solver = ClaspAdapter('/dev/shm/solver.in')
#                t1 = time.time()
#                results['cross'] = self._solver.Solve(instance)
#                t2 = time.time()
#                td = t2-t1
#                print('Solving (Clasp): ' + str(td))
#                sys.stdout.flush()
#                solvingc.append(td)

#                subprocess.call(["./mem.sh",str(os.getpid()),"post"],stderr=FNULL)


            unreach = []

            if reach:
                print('reach', flush=True)
                instm = []
                solvingm = []
                nodes = list(kripke.IterNodes())
                for node in nodes:
#                    print(node+'_reach')
#                    sys.stdout.flush()
#                    subprocess.call(["./mem.sh",str(os.getpid()),"pre"],stderr=FNULL)
                    t1 = time.time()
                    instance = Instantiator.InstantiateReach(kripke,encoding,node)
                    t2 = time.time()
                    td = t2 - t1
                    instm.append(td)
#                    subprocess.call(["./mem.sh",str(os.getpid()),"in"],stderr=FNULL)

                    self._solver = PycoSATAdapter()#'/dev/shm/solver.in','/dev/shm/solver.out')
                    t1 = time.time()
                    result = self._solver.Solve(instance)
                    results[node+'_reach'] = result
                    t2 = time.time()
                    td = t2 - t1
#                    print('Solving (MiniSAT): ' + str(td))
#                    sys.stdout.flush()
                    solvingm.append(td)

#                    self._solver = ClaspAdapter('/dev/shm/solver.in')
#                    t1 = time.time()
#                    results[node+'_reach'] = self._solver.Solve(instance)
#                    t2 = time.time()
#                    td = t2-t1
#                    print('Solving (Clasp): ' + str(td))
#                    sys.stdout.flush()
#                    solvingc.append(td)

                    if result == []:
                        unreach.append(node)

#                    subprocess.call(["./mem.sh",str(os.getpid()),"post"],stderr=FNULL)

                print('  Reach (Instantiation): ' + str(sum(instm)), flush=True)
                print('  Reach (Solving): ' + str(sum(solvingm)), flush=True)


            if lppreach:
                print('long path reach', flush=True)
                instm = []
                solvingm = []
                self._solver = PycoSATAdapter()#'/dev/shm/solver.in','/dev/shm/solver.out')
                nodes = list(kripke.IterNodes())
                no = 0
                while nodes != []:
                    no += 1
                    node = nodes.pop()
                    if 'init' in kripke.GetNode(node).Props:
                        continue

                    t1 = time.time()
                    instance = Instantiator.InstantiateReach(kripke,encoding,node)
                    t2 = time.time()
                    td = t2 - t1
                    instm.append(td)
#                    if node == 'api_client_fw_input_r0':
#                        XMLUtils.pprint(instance)

                    t1 = time.time()
                    result = self._solver.Solve(instance)
                    t2 = time.time()
                    td = t2 - t1
                    solvingm.append(td)

                    if result == []:
#                        print('\t' + node, file=sys.stderr)
#                        sys.stdout.flush()

                        if not reach:
                            unreach.append(node)
                        continue

                    result = result[0]

                    transitions = [transition for transition in result if result[transition] and ('_true_' in transition or '_false_' in transition)]
                    for transition in transitions:
                        labels = transition.split('_')
                        try:
                            nodes.remove('_'.join(labels[:5]))
                            print('_'.join(labels[:5]), file=sys.stderr)
                        except:
                            pass
                        try:
                            nodes.remove('_'.join(labels[6:]))
                            print('_'.join(labels[6:]), file=sys.stderr)
                        except:
                            pass

                print('  Long Path Reach (Instantiation): ' + str(sum(instm)), flush=True)
                print('  Long Path Reach (Solving): ' + str(sum(solvingm)), flush=True)
                print('    saved %s of %s calculations' % (len(list(kripke.IterNodes()))-no, len(list(kripke.IterNodes()))), flush=True)


            if lppshadow and (reach or lppreach):
                print('long path shadow', flush=True)
                instm = []
                solvingm = []
                self._solver = PycoSATAdapter()#'/dev/shm/solver.in','/dev/shm/solver.out')
                nodes = list(kripke.IterNodes())
                no = 0
                for node in nodes:
                    if 'init' in kripke.GetNode(node).Props or node in unreach:
                        continue

                    no += 1

                    t1 = time.time()
                    instance = Instantiator.InstantiateShadow(kripke,encoding,{},node)
                    t2 = time.time()
                    td = t2 - t1
                    instm.append(td)

                    t1 = time.time()
                    result = self._solver.Solve(instance)
                    t2 = time.time()
                    td = t2-t1
                    solvingm.append(td)

                print('  Long Path Shadow (Instantiation): ' + str(sum(instm)), flush=True)
                print('  Long Path Shadow (Solving): ' + str(sum(solvingm)), flush=True)
                print('    saved %s of %s calculations' % (len(nodes)-no, len(nodes)), flush=True)


            if shadow:
                print('shadow', flush=True)
                instm = []
                solvingm = []
                nodes = list(kripke.IterNodes())
                for node in nodes:
#                    print(node+'_shadow')
#                    sys.stdout.flush()
#                    subprocess.call(["./mem.sh",str(os.getpid()),"pre"],stderr=FNULL)
                    t1 = time.time()
                    instance = Instantiator.InstantiateShadow(kripke,encoding,{},node)
                    t2 = time.time()
                    td = t2 - t1
                    instm.append(td)
#                    subprocess.call(["./mem.sh",str(os.getpid()),"in"],stderr=FNULL)

#                    self._solver = MiniSATAdapter('/dev/shm/solver.in','/dev/shm/solver.out')
                    t1 = time.time()
                    results[node+'_shadow'] = self._solver.Solve(instance)
                    t2 = time.time()
                    td = t2 - t1
#                    print('Solving (MiniSAT): ' + str(td))
#                    sys.stdout.flush()
                    solvingm.append(td)

#                    self._solver = ClaspAdapter('/dev/shm/solver.in')
#                    t1 = time.time()
#                    results[node+'_shadow'] = self._solver.Solve(instance)
#                    t2 = time.time()
#                    td = t2-t1
#                    print('Solving (Clasp): ' + str(td))
#                    sys.stdout.flush()
#                    solvingc.append(td)

#                    subprocess.call(["./mem.sh",str(os.getpid()),"post"],stderr=FNULL)

                print('  Shadow (Instantiation): ' + str(sum(instm)), flush=True)
                print('  Shadow (Solving): ' + str(sum(solvingm)), flush=True)


        if end_to_end:
            print("end to end", flush=True)
            instm = []
            solvingm = []

            self._solver = PycoSATAdapter()

            reach = self._gen_reach()

            source = lambda src: "%s_output_r0" % src
            target = lambda dst: "%s_input_r0_accept" % dst

            for src, targets in reach.items():
                for dst in reach.keys():

                    t1 = time.time()
                    instance = Instantiator.InstantiateEndToEnd(kripke, encoding, source(src), target(dst))
                    t2 = time.time()
                    td = t2 - t1
                    instm.append(td)

                    t1 = time.time()
                    result = self._solver.Solve(instance)
                    t2 = time.time()
                    td = t2 - t1
                    solvingm.append(td)

                    results['%s_to_%s' % (src, dst)] = result

                    if dst in targets and result:
                        print('  correct for %s -> %s' % (src, dst), file=sys.stderr, flush=True)
                    elif dst in targets and not result:
                        print('  failed for %s -> %s' % (src, dst), file=sys.stderr, flush=True)
                    elif dst not in targets and result:
                        print('  failed for ! %s -> %s' % (src, dst), file=sys.stderr, flush=True)
                    elif dst not in targets and not result:
                        print('  correct for ! %s -> %s' % (src, dst), file=sys.stderr, flush=True)
                    else:
                        print('  should never occur but did for %s -> %s' % (src, dst), file=sys.stderr, flush=True)

            print('  End to End (Instantiation): ' + str(sum(instm)), flush=True)
            print('  End to End (Solving): ' + str(sum(solvingm)), flush=True)


            measstr = '\t'.join([
                str(sum(solvingm)),
                str(numpy.mean(solvingm)),
                str(numpy.median(solvingm)),
                str(numpy.std(solvingm)),
#                str(sum(solvingc)),
#                str(numpy.mean(solvingc)),
#                str(numpy.median(solvingc)),
#                str(numpy.std(solvingc))
            ])
#            f.write(measstr+'\n')

#            print('MiniSAT')
#            print('Total solving: ' + str(sum(solvingm)))
#            print('Avg solving: ' + str(numpy.mean(solvingm)))
#            print('Median instantiation: ' + str(numpy.median(solvingm)))
#            print('Std deviation: ' + str(numpy.std(solvingm)))

#            print('Clasp')
#            print('Total solving: ' + str(sum(solvingc)))
#            print('Avg solving: ' + str(numpy.mean(solvingc)))
#            print('Median instantiation: ' + str(numpy.median(solvingc)))
#            print('Std deviation: ' + str(numpy.std(solvingc)))
#            print('')
#            sys.stdout.flush()


#        f.close()



    def _gen_reach(self):
        internet = ["internet_provider_fw"]
        dns = ["ups_dns_fw"]
        dmz_servers = [
            "ups_admin_fw", "ups_data_fw", "ups_file_fw",
            "ups_ldap_fw", "ups_mail_fw", "ups_mail_fw", "ups_vpn_fw",
            "ups_web_fw"
        ]
        subnet_servers = [
            "api_server_fw", "asta_server_fw", "bgp_server_fw", "chem_server_fw",
            "cs_server_fw", "geog_server_fw", "geo_server_fw", "hgp_server_fw",
            "hpi_server_fw", "hssp_server_fw", "intern_server_fw",
            "intern_server_fw", "jura_server_fw", "ling_server_fw",
            "math_server_fw", "mmz_server_fw", "physik_server_fw",
            "pogs_server_fw", "psych_server_fw", "sq_server_fw",
            "stud_server_fw", "ub_server_fw", "welc_server_fw"
        ]
        res = {
            "api_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "api_server_fw" : dns,
            "asta_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "asta_server_fw" : dns,
            "bgp_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "bgp_server_fw" : dns,
            "chem_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "chem_server_fw" : dns,
            "cs_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "cs_server_fw" : dns,
            "geo_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "geog_server_fw" : dns,
            "geog_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "geo_server_fw" : dns,
            "hgp_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "hgp_server_fw" : dns,
            "hpi_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "hpi_server_fw" : dns,
            "hssp_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "hssp_server_fw" : dns,
            "intern_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "internet_provider_fw" : internet + dns + dmz_servers + subnet_servers,
            "intern_server_fw" : dns,
            "jura_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "jura_server_fw" : dns,
            "ling_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "ling_server_fw" : dns,
            "math_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "math_server_fw" : dns,
            "mmz_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "mmz_server_fw" : dns,
            "physik_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "physik_server_fw" : dns,
            "pogs_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "pogs_server_fw" : dns,
            "psych_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "sq_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "sq_server_fw" : dns,
            "stud_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "stud_server_fw" : dns,
            "ub_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "ub_server_fw" : dns,
            "upc_client0_fw" : internet + dns + dmz_servers + subnet_servers,
            "upc_client1_fw" : internet + dns + dmz_servers + subnet_servers,
            "up_gateway_fw" : dns,
            "ups_admin_fw" : internet + dns + dmz_servers + ["up_gateway_fw"],
            "ups_data_fw" : dns,
            "ups_dns_fw" : dns,
            "ups_file_fw" : dns,
            "ups_ldap_fw" : dns,
            "ups_mail_fw" : dns,
            "ups_vpn_fw" : dns,
            "ups_web_fw" : dns,
            "welc_client_fw" : internet + dns + dmz_servers + subnet_servers,
            "welc_server_fw" : dns
        }

        return res



    def __init__(self):
        trees = [et.parse('./large.xml')]#et.parse('./small.xml'),et.parse('./medium.xml'),et.parse('./large.xml')]
        self._roots = [tree.getroot() for tree in trees ]


if __name__ == "__main__":
    main = Main()
    main.main()
