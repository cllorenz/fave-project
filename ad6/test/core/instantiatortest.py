import unittest
import lxml.etree as et
from lxml import objectify
from src.core.instantiator import *
from src.solver.minisat import MiniSATAdapter
from src.solver.pycosat import PycoSATAdapter
from src.sat.satutils import SATUtils as sat

class InstantiatorTest(unittest.TestCase):
    def deannotate(config):
        for elem in config.getiterator():
            i = elem.tag.find('}')
            if i >= 0:
                elem.tag = elem.tag[i+1:]
        objectify.deannotate(config,cleanup_namespaces=True)


    def testReach(self):
        examinee = et.parse('./test/core/testReach.xml').getroot()
        InstantiatorTest.deannotate(examinee)
        expectation = [{
            'net0_n0_fw0_accept_r0_true_net0_n0_eth0_out': False,
            'net0_n0_fw0_output_r0_true_net0_n0_fw0_fwdin_r0': True,
            'net0_n0_fw0_fwdin_r0_false_net0_n0_fw0_fwdin_r1': False,
            'net0_n0_fw0_fwdin_r0_true_net0_n0_fw0_drop_r0': True,
            'net0_n0_fw0_fwdin_r1_false_net0_n0_fw0_fwdin_r2': False,
            'net0_n0_fw0_fwdin_r1_true_net0_n0_fw0_accept_r0': False,
            'net0_n0_fw0_fwdin_r2_true_net0_n0_fw0_drop_r0': False,
            'proto_0=0' : False,
            'proto_0=1' : False,
            'proto_1=0' : False,
            'proto_1=1' : False,
            'proto_2=0' : False,
            'proto_2=1' : False,
            'proto_3=0' : False,
            'proto_3=1' : False,
            'proto_4=0' : False,
            'proto_4=1' : False,
            'proto_5=0' : False,
            'proto_5=1' : False,
            'proto_6=0' : False,
            'proto_6=1' : False,
            'proto_7=0' : False,
            'proto_7=1' : False,
            'proto_tcp' : False,
        }]

        solver = PycoSATAdapter()
        instances = Instantiator.Instantiate(examinee)
        self.assertEqual(solver.Solve(instances['net0_n0_fw0_drop_r0_reach']),expectation)

        expectation = []
        self.assertEqual(solver.Solve(instances['net0_n0_fw0_accept_r0_reach']),expectation)


    def testCycle(self):
        examinee = et.parse('./test/core/testCycle.xml').getroot()
        InstantiatorTest.deannotate(examinee)
        expectation = [{
            'net0_n0_fw0_accept_r0_true_net0_n0_eth0_out': False,
            'net0_n0_fw0_output_r0_true_net0_n0_fw0_fwdin_r0': True,
            'net0_n0_fw0_fwdin_r0_false_net0_n0_fw0_fwdin_r1': True,
            'net0_n0_fw0_fwdin_r0_true_net0_n0_fw0_accept_r0': False,
            'net0_n0_fw0_fwdin_r1_false_net0_n0_fw0_fwdin_r2': False,
            'net0_n0_fw0_fwdin_r1_true_net0_n0_fw0_fwdin_r0': True,
            'net0_n0_fw0_fwdin_r2_true_net0_n0_fw0_drop_r0': False,
            'proto_0=0' : True,
            'proto_0=1' : False,
            'proto_1=0' : True,
            'proto_1=1' : False,
            'proto_2=0' : True,
            'proto_2=1' : False,
            'proto_3=0' : True,
            'proto_3=1' : False,
            'proto_4=0' : True,
            'proto_4=1' : False,
            'proto_5=0' : False,
            'proto_5=1' : True,
            'proto_6=0' : False,
            'proto_6=1' : True,
            'proto_7=0' : True,
            'proto_7=1' : False,
            'proto_tcp' : True,
            'proto_udp' : False,
        }]
        solver = MiniSATAdapter()
        instances = Instantiator.Instantiate(examinee, Reach=False, Cycle=True)
        self.assertEqual(solver.Solve(instances['cycle']),expectation)


    def testShadow(self):
        examinee = et.parse('./test/core/testShadow.xml').getroot()
        InstantiatorTest.deannotate(examinee)
        expectation = [{
            'net0_n0_fw0_accept_r0_true_net0_n0_eth0_out': False,
            'net0_n0_fw0_output_r0_true_net0_n0_fw0_fwdin_r0': True,
            'net0_n0_fw0_fwdin_r0_false_net0_n0_fw0_fwdin_r1': False,
            'net0_n0_fw0_fwdin_r0_true_net0_n0_fw0_accept_r0': True,
            'net0_n0_fw0_fwdin_r1_false_net0_n0_fw0_fwdin_r2': False,
            'net0_n0_fw0_fwdin_r1_true_net0_n0_fw0_drop_r0': False,
            'net0_n0_fw0_fwdin_r2_true_net0_n0_fw0_drop_r0': False,
            'proto_0=0' : True,
            'proto_0=1' : False,
            'proto_1=0' : True,
            'proto_1=1' : False,
            'proto_2=0' : True,
            'proto_2=1' : False,
            'proto_3=0' : True,
            'proto_3=1' : False,
            'proto_4=0' : True,
            'proto_4=1' : False,
            'proto_5=0' : False,
            'proto_5=1' : True,
            'proto_6=0' : False,
            'proto_6=1' : True,
            'proto_7=0' : True,
            'proto_7=1' : False,
            'proto_tcp' : True,
        }]

        solver = MiniSATAdapter()
        instances = Instantiator.Instantiate(examinee, Reach=False, Shadow=True)

        self.assertEqual(solver.Solve(instances['net0_n0_fw0_accept_r0_shadow']),expectation)


        expectation = []
        self.assertEqual(solver.Solve(instances['net0_n0_fw0_fwdin_r1_shadow']),expectation)


    def testCross(self):
        examinee = et.parse('./test/core/testCross.xml').getroot()
        InstantiatorTest.deannotate(examinee)
        expectation = [{
            'net0_n0_eth0_out_true_net0_n1_eth0_in': True,
            'net0_n0_eth0_out_true_net0_n2_eth0_in': True,
            'net0_n0_fw0_accept_r0_true_net0_n0_eth0_out': True,
            'net0_n0_fw0_output_r0_true_net0_n0_fw0_accept_r0': True,
            'net0_n1_eth0_in_true_net0_n1_fw0_input_r0': True,
            'net0_n1_eth0_out_true_net0_n0_eth0_in': False,
            'net0_n1_fw0_input_r0_false_net0_n1_fw0_input_r1': False,
            'net0_n1_fw0_input_r0_true_net0_n1_fw0_input_r0_accept': True,
            'net0_n1_fw0_input_r1_true_net0_n1_fw0_drop_r0': False,
            'net0_n2_eth0_in_true_net0_n2_fw0_input_r0': True,
            'net0_n2_eth0_out_true_net0_n0_eth0_in': False,
            'net0_n2_fw0_input_r0_false_net0_n2_fw0_input_r1': False,
            'net0_n2_fw0_input_r0_true_net0_n2_fw0_drop_r0': True,
            'net0_n2_fw0_input_r1_true_net0_n2_fw0_drop_r0': False,
            'proto_0=0' : True,
            'proto_0=1' : False,
            'proto_1=0' : True,
            'proto_1=1' : False,
            'proto_2=0' : True,
            'proto_2=1' : False,
            'proto_3=0' : True,
            'proto_3=1' : False,
            'proto_4=0' : True,
            'proto_4=1' : False,
            'proto_5=0' : False,
            'proto_5=1' : True,
            'proto_6=0' : False,
            'proto_6=1' : True,
            'proto_7=0' : True,
            'proto_7=1' : False,
            'proto_tcp' : True,
        }]
        solver = MiniSATAdapter()
        instances = Instantiator.Instantiate(examinee, Reach=False, Cross=True)
        self.assertEqual(solver.Solve(instances['cross']),expectation)


def main():
    unittest.main()


if __name__ == '__main__':
    main()
