import unittest
import lxml.etree as et
from src.xml.xmlutils import XMLUtils


class XMLUtilsTest(unittest.TestCase):
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
        if any(not XMLUtilsTest.equal(et1,et2) for et1,et2 in zip(et1,et2)):
            return False
        return True


    def testIp4(self):
        examinee = et.parse('./test/xml/testIp4.xml').getroot()
        expectation = et.parse('./test/xml/resultIp4.xml').getroot()

        self.assertTrue(XMLUtilsTest.equal(XMLUtils.ConvertToVariables(examinee),expectation))


    def testIp6(self):
        examinee = et.parse('./test/xml/testIp6.xml').getroot()
        expectation = et.parse('./test/xml/resultIp6.xml').getroot()

        self.assertTrue(XMLUtilsTest.equal(XMLUtils.ConvertToVariables(examinee),expectation))

    def testCIDR(self):
        examinee = XMLUtils.ConvertToVariables(et.parse('./test/xml/testIp4.xml').getroot())
        expectation = et.parse('./test/xml/resultCIDRIp4.xml').getroot()

        examinee = examinee.attrib['name']
        self.assertTrue(XMLUtilsTest.equal(XMLUtils.ConvertCIDRToVariables(examinee),expectation))

        examinee = XMLUtils.ConvertToVariables(et.parse('./test/xml/testIp6.xml').getroot())
        expectation = et.parse('./test/xml/resultCIDRIp6.xml').getroot()

        examinee = examinee.attrib['name']
        self.assertTrue(XMLUtilsTest.equal(XMLUtils.ConvertCIDRToVariables(examinee),expectation))


    def testPort(self):
        examinee = et.parse('./test/xml/testPort.xml').getroot()
        expectation = et.parse('./test/xml/resultPort.xml').getroot()
        var = XMLUtils.ConvertToVariables(examinee)
        self.assertTrue(XMLUtilsTest.equal(var,expectation))

        direction = 'dst'
        port = '8080'

        expectation = et.parse('./test/xml/resultVarPort.xml').getroot()
        self.assertTrue(XMLUtilsTest.equal(XMLUtils.ConvertPortToVariables(port,direction),expectation))

    def testIf(self):
        examinee = et.parse('./test/xml/testIf.xml').getroot()
        expectation = et.parse('./test/xml/resultIf.xml').getroot()

        self.assertTrue(XMLUtilsTest.equal(XMLUtils.ConvertToVariables(examinee),expectation))


def main():
    unittest.main()


if __name__ == '__main__':
    main()
