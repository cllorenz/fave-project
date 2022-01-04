import unittest
import lxml.etree as et
from src.sat.satutils import SATUtils as sat
from src.xml.xmlutils import XMLUtils

class SATUtilsTest(unittest.TestCase):
    def equal(et1,et2):
        if et1.tag != et2.tag:
            print("Failed tag with: " + et1.tag + " and " + et2.tag)
            #print(str(et.tostring(et1)) + "\n" + str(et.tostring(et2)))
            XMLUtils.pprint(et1)
            XMLUtils.pprint(et2)
            return False
        if et1.attrib != et2.attrib:
            print("Failed attrib with: " + str(et1.attrib) + " and " + str(et2.attrib))
            #print(str(et.tostring(et1)) + "\n" + str(et.tostring(et2)))
            XMLUtils.pprint(et1)
            XMLUtils.pprint(et2)
            return False
        #if et1.text != et2.text:
        #    print("Failed text with: " + str(et1.text) + " and " + str(et2.text))
        #    print(str(et.tostring(et1)) + "\n" + str(et.tostring(et2)))
        #    return False
        #if et1.tail != et2.tail:
        #    print("Failed tail with: " + str(et1.tail) + " and " + str(et2.tail))
        #    print(str(et.tostring(et1)) + "\n" + str(et.tostring(et2)))
        #    return False
        if len(et1) != len(et2):
            print("Failed len with: " + str(len(et1)) + " and " + str(len(et2)))
            #print(str(et.tostring(et1)) + "\n" + str(et.tostring(et2)))
            XMLUtils.pprint(et1)
            XMLUtils.pprint(et2)
            return False
        if any(not SATUtilsTest.equal(et1,et2) for et1,et2 in zip(et1,et2)):
            return False
        return True

    def removeClauseMarks(self,formula):
        try:
            del formula.attrib['clause']
        except:
            pass
        for subformula in formula:
            self.removeClauseMarks(subformula)

    def testReduceImplication(self):
        examinee = et.parse('./test/sat/testReduceImplication.xml').getroot()
        expectation = et.parse('./test/sat/resultReduceImplication.xml').getroot()

        sat._ReduceToDNC(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testReduceEquality(self):
        examinee = et.parse('./test/sat/testReduceEquality.xml').getroot()
        expectation = et.parse('./test/sat/resultReduceEquality.xml').getroot()

        sat._ReduceToDNC(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testReduceToDNC(self):
        examinee = et.parse('./test/sat/testNonDNC.xml').getroot()
        expectation = et.parse('./test/sat/resultReduceToDNC.xml').getroot()

        self.assertRaises(Exception,sat._ReduceToDNC,'blablabla')
        sat._ReduceToDNC(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testFlattenConjunction(self):
        examinee = et.parse('./test/sat/testFlattenConjunction.xml').getroot()
        expectation = et.parse('./test/sat/resultFlattenConjunction.xml').getroot()

        sat._Flatten(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testFlattenDisjunction(self):
        examinee = et.parse('./test/sat/testFlattenDisjunction.xml').getroot()
        expectation = et.parse('./test/sat/resultFlattenDisjunction.xml').getroot()

        sat._Flatten(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testFlattenAll(self):
        examinee = et.parse('./test/sat/testFlattenAll.xml').getroot()
        expectation = et.parse('./test/sat/resultFlattenAll.xml').getroot()

        sat._Flatten(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testConvertBinaryFormSimple(self):
        examinee = et.parse('./test/sat/testConvertBinaryFormSimple.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertBinaryFormSimple.xml').getroot()

        sat._ConvertBinaryForm(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testConvertBinaryFormComplex(self):
        examinee = et.parse('./test/sat/testConvertBinaryFormComplex.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertBinaryFormComplex.xml').getroot()

        sat._ConvertBinaryForm(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testNegationConstant(self):
        examinee = et.parse('./test/sat/testNegationConstant.xml').getroot()
        expectation = et.parse('./test/sat/resultNegationConstant.xml').getroot()

        examinee = sat._Negate(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testNegationVariable(self):
        examinee = et.parse('./test/sat/testNegationVariable.xml').getroot()
        expectation = et.parse('./test/sat/resultNegationVariable.xml').getroot()

        examinee = sat._Negate(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))



    def testNegationNegation(self):
        examinee = et.parse('./test/sat/testNegationNegation.xml').getroot()
        expectation = et.parse('./test/sat/resultNegationNegation.xml').getroot()

        examinee = sat._Negate(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))



    def testNegationConjunction(self):
        examinee = et.parse('./test/sat/testNegationConjunction.xml').getroot()
        expectation = et.parse('./test/sat/resultNegationConjunction.xml').getroot()

        examinee = sat._Negate(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testNegationDisjunction(self):
        examinee = et.parse('./test/sat/testNegationDisjunction.xml').getroot()
        expectation = et.parse('./test/sat/resultNegationDisjunction.xml').getroot()

        examinee = sat._Negate(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testNegationAll(self):
        examinee = et.parse('./test/sat/testNegationAll.xml').getroot()
        expectation = et.parse('./test/sat/resultNegationAll.xml').getroot()

        examinee = sat._Negate(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testConvertDNCToCNFNoNoclause(self):
        examinee = et.parse('./test/sat/testConvertDNCToCNFNoNoclause.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertDNCToCNFNoNoclause.xml').getroot()

        sat._ConvertDNCToCNF(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testConvertDNCToCNFNegation(self):
        examinee = et.parse('./test/sat/testConvertDNCToCNFNegation.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertDNCToCNFNegation.xml').getroot()

        sat._ConvertDNCToCNF(examinee)

        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testConvertDNCToCNFConjunction(self):
        examinee = et.parse('./test/sat/testConvertDNCToCNFConjunction.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertDNCToCNFConjunction.xml').getroot()

        sat._ConvertDNCToCNF(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testConvertDNCToCNFDisjunction(self):
        examinee = et.parse('./test/sat/testConvertDNCToCNFDisjunction.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertDNCToCNFDisjunction.xml').getroot()

        sat._ConvertDNCToCNF(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testConvertDNCToCNFAll(self):
        examinee = et.parse('./test/sat/testConvertDNCToCNFAll.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertDNCToCNFAll.xml').getroot()

        sat._ConvertDNCToCNF(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testConvertToCNFEquality(self):
        examinee = et.parse('./test/sat/testConvertToCNFEquality.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToCNFEquality.xml').getroot()

        sat.ConvertToCNF(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testConvertToCNFComplex(self):
        examinee = et.parse('./test/sat/testConvertToCNFComplex.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToCNFComplex.xml').getroot()

        sat.ConvertToCNF(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


    def testConvertToCNFAll(self):
        examinee = et.parse('./test/sat/testConvertToCNFAll.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToCNFAll.xml').getroot()

        sat.ConvertToCNF(examinee)
        self.assertTrue(SATUtilsTest.equal(examinee,expectation))


def main():
    unittest.main()


if __name__ == '__main__':
    main()
