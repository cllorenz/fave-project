import unittest
import lxml.etree as et
from src.sat.qbfutils import QBFUtils as qbf


class QBFUtilsTest(unittest.TestCase):
    def equal(et1,et2):
        if et1.tag != et2.tag:
            print("Failed tag with: " + et1.tag + " and " + et2.tag)
            print(str(et.tostring(et1)) + "\n" + str(et.tostring(et2)))
            return False
        if et1.attrib != et2.attrib:
            print("Failed attrib with: " + str(et1.attrib) + " and " + str(et2.attrib))
            print(str(et.tostring(et1)) + "\n" + str(et.tostring(et2)))
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
            print(str(et.tostring(et1)) + "\n" + str(et.tostring(et2)))
            return False
        if any(not QBFUtilsTest.equal(et1,et2) for et1,et2 in zip(et1,et2)):
            return False
        return True

    def testMarkUnbound(self):
        examinee = et.parse('./test/sat/testMarkUnbound.xml').getroot()
        expectation = et.parse('./test/sat/resultMarkUnbound.xml').getroot()

        qbf.markUnbound(examinee,[])
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testUnifyVariables(self):
        examinee = et.parse('./test/sat/testUnifyVariables.xml').getroot()
        expectation = et.parse('./test/sat/resultUnifyVariables.xml').getroot()

        qbf.unifyVariables(examinee,0)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexConjunction(self):
        examinee = et.parse('./test/sat/testConvertToPrenexConjunction.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexConjunction.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexNegationExists(self):
        examinee = et.parse('./test/sat/testConvertToPrenexNegationExists.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexNegationExists.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexNegationForall(self):
        examinee = et.parse('./test/sat/testConvertToPrenexNegationForall.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexNegationForall.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexImplicationFirst(self):
        examinee = et.parse('./test/sat/testConvertToPrenexImplicationFirst.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexImplicationFirst.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexImplicationSecond(self):
        examinee = et.parse('./test/sat/testConvertToPrenexImplicationSecond.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexImplicationSecond.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexImplicationBoth(self):
        examinee = et.parse('./test/sat/testConvertToPrenexImplicationBoth.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexImplicationBoth.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexEqualityFirstExists(self):
        examinee = et.parse('./test/sat/testConvertToPrenexEqualityFirstExists.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexEqualityFirstExists.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexEqualitySecondExists(self):
        examinee = et.parse('./test/sat/testConvertToPrenexEqualitySecondExists.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexEqualitySecondExists.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexEqualityFirstForall(self):
        examinee = et.parse('./test/sat/testConvertToPrenexEqualityFirstForall.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexEqualityFirstForall.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexEqualitySecondForall(self):
        examinee = et.parse('./test/sat/testConvertToPrenexEqualitySecondForall.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexEqualitySecondForall.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertToPrenexEqualityBoth(self):
        examinee = et.parse('./test/sat/testConvertToPrenexEqualityBoth.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertToPrenexEqualityBoth.xml').getroot()

        qbf.convertToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))




    def testConvertQBFToPrenex(self):
        examinee = et.parse('./test/sat/testConvertQBFToPrenex.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertQBFToPrenex.xml').getroot()

        qbf.convertQBFToPrenex(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testConvertPrenexToSkolem(self):
        examinee = et.parse('./test/sat/testConvertPrenexToSkolem.xml').getroot()
        expectation = et.parse('./test/sat/resultConvertPrenexToSkolem.xml').getroot()

        qbf.convertPrenexToSkolem(examinee)
        self.assertTrue(QBFUtilsTest.equal(examinee,expectation))


    def testNormalize(self):
        None


def main():
    unittest.main()


if __name__ == '__main__':
    main()
