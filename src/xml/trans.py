import lxml.etree as et
import json
from functools import reduce

class Translator:
    def translate(data):
        if type(data) == type(et.Element('foo')):
            return Translator.XMLToJSON(data)
        elif type(data) == type(json.dumps([{'foo':'bar'}])): 
            return Translator.JSONToXML(json.loads(data))
        elif type(data) == type(json.loads(json.dumps([{'foo':'bar'}]))):
            return Translator.JSONToXML(data)
        else:
            raise Exception("Type not supported. Use XML or JSON instead.")


    def XMLToJSON(data):
        try:
            li = [ {"attrib" : list(map(lambda x: x + ":" + data.attrib[x], data.attrib)) }]
        except AttributeError:
            li = []
        if list(data):
            li.extend( list(map(Translator.XMLToJSON, list(data))))
        return [data.tag,li]

    def JSONToXML(data):
        tag = data[0]
        attrib = data[1][0]['attrib']
        elem = et.Element(tag)
        for attr in attrib:
            pair = attr.split(':')
            elem.attrib[pair[0]] = pair[1]
        elem.extend(list(map(Translator.JSONToXML,data[1][1:])))
        return elem
