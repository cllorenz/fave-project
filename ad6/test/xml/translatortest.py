import unittest
import lxml.etree as et
from src.xml.trans import Translator
import json

class TranslatorTest(unittest.TestCase):
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
        if any(not TranslatorTest.equal(et1,et2) for et1,et2 in zip(et1,et2)):
            return False
        return True


    def testXMLToJSON(self):
        examinee = et.parse('./test/xml/testXMLToJSON.xml').getroot()
        expectation = open('./test/xml/resultXMLToJSON.json','r').read()

        self.assertEqual(Translator.XMLToJSON(examinee),json.loads(expectation))


    def testJSONToXML(self):
        examinee = open('./test/xml/testJSONToXML.json','r').read()
        expectation = et.parse('./test/xml/resultJSONToXML.xml').getroot()

        self.assertTrue(TranslatorTest.equal(Translator.translate(examinee),expectation))

    def testTranslate(self):
        examinee = et.parse('./test/xml/testXMLToJSON.xml').getroot()
        expectation = open('./test/xml/resultXMLToJSON.json','r').read()

        self.assertEqual(Translator.translate(examinee),json.loads(expectation))

        examinee = open('./test/xml/testJSONToXML.json','r').read()
        expectation = et.parse('./test/xml/resultJSONToXML.xml').getroot()

        self.assertTrue(TranslatorTest.equal(Translator.translate(examinee),expectation))

        examinee = json.loads(examinee)

        self.assertTrue(TranslatorTest.equal(Translator.translate(examinee),expectation))


def main():
    unittest.main()


if __name__ == '__main__':
    main()
