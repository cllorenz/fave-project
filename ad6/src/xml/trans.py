#/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2015 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of ad6.

# ad6 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ad6 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with ad6.  If not, see <https://www.gnu.org/licenses/>.

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
