import unittest
import lxml.etree as et
from lxml import objectify
from src.core.kripke import *
from src.xml.xmlutils import XMLUtils


class KripkeTest(unittest.TestCase):
    def testKripke(self):
        examinee = et.parse('./test/core/testKripke.xml').getroot()
        
        for elem in examinee.getiterator():
            i = elem.tag.find('}')
            if i >= 0:
                elem.tag = elem.tag[i+1:]
        objectify.deannotate(examinee,cleanup_namespaces=True)

        outiface = KripkeNode(Props=['net0_n0_eth0_out'],Gamma = XMLUtils.constant())
        n0_fw0_drop_r0 = KripkeNode(Props=['net0_n0_fw0_drop_r0','drop'], Gamma = XMLUtils.constant())
        n0_fw0_accept_r0 = KripkeNode(Props=['net0_n0_fw0_accept_r0','out'], Gamma = XMLUtils.constant())
        n0_fw0_fwdin_r2 = KripkeNode(Props=['net0_n0_fw0_fwdin_r2'], Gamma = XMLUtils.constant())
        n0_fw0_fwdin_r1 = KripkeNode(Props=['net0_n0_fw0_fwdin_r1'], Gamma = XMLUtils.variable('tcp'))
        n0_fw0_fwdin_r0 = KripkeNode(Props=['net0_n0_fw0_fwdin_r0'], Gamma = XMLUtils.constant())
        n0_fw0_forward_r0 = KripkeNode(Props=['net0_n0_fw0_output_r0','output','init'], Gamma = XMLUtils.constant())
        iniface = KripkeNode(Props=['net0_n0_eth0_in'],Gamma = XMLUtils.constant())

        expnodes = {
            'net0_n0_eth0_out' : outiface,
            'net0_n0_fw0_drop_r0' : n0_fw0_drop_r0,
            'net0_n0_fw0_accept_r0' : n0_fw0_accept_r0,
            'net0_n0_fw0_fwdin_r2' : n0_fw0_fwdin_r2,
            'net0_n0_fw0_fwdin_r1' : n0_fw0_fwdin_r1,
            'net0_n0_fw0_fwdin_r0' : n0_fw0_fwdin_r0,
            'net0_n0_fw0_output_r0' : n0_fw0_forward_r0,
            'net0_n0_eth0_in' : iniface,
        }

        expftrans = {
            'net0_n0_fw0_accept_r0': [('net0_n0_eth0_out', True)],
            'net0_n0_fw0_fwdin_r2' : [('net0_n0_fw0_drop_r0',True)],
            'net0_n0_fw0_fwdin_r1' : [('net0_n0_fw0_drop_r0',True),('net0_n0_fw0_fwdin_r2',False)],
            'net0_n0_fw0_fwdin_r0' : [('net0_n0_fw0_accept_r0',True),('net0_n0_fw0_fwdin_r1',False)],
            'net0_n0_fw0_output_r0' : [('net0_n0_fw0_fwdin_r0',True)],
        }

        expbtrans = {
            'net0_n0_eth0_out' : [('net0_n0_fw0_accept_r0',True)],
            'net0_n0_fw0_drop_r0' : [('net0_n0_fw0_fwdin_r1',True),('net0_n0_fw0_fwdin_r2',True)],
            'net0_n0_fw0_fwdin_r1' : [('net0_n0_fw0_fwdin_r0',False)],
            'net0_n0_fw0_fwdin_r2' : [('net0_n0_fw0_fwdin_r1',False)],
            'net0_n0_fw0_fwdin_r0' : [('net0_n0_fw0_output_r0',True)],
            'net0_n0_fw0_accept_r0' : [('net0_n0_fw0_fwdin_r0',True)],
        }

        expinits = {'net0_n0_fw0_output_r0' : n0_fw0_forward_r0 }

        kripke = KripkeUtils.ConvertToKripke(examinee)

        self.assertEqual(expnodes.keys(),kripke._Nodes.keys())
        self.assertEqual(expftrans,kripke._FTransitions)
        self.assertEqual(expbtrans,kripke._BTransitions)
        self.assertEqual(expinits,kripke._Inits)


def main():
    unittest.main()


if __name__ == '__main__':
    main()
