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

class GenUtils():
    def config():
        elem = et.Element('config')
        elem.set('xmlns','http://config')
        return elem

    def firewalls():
        return et.Element('firewalls')

    def firewall(fwname):
        return et.Element('firewall',{'name':fwname.split('_').pop(),'key':fwname})

    def table(name):
        return et.Element('table',{'name':name})

    def rule(name,key="",raw="", raw_line_no=-1):
        rule = et.Element('rule',{'name':'r'+name})
        if key != "":
            rule.attrib['key'] = key
        if raw != "":
            rule.attrib['raw'] = raw
        if raw_line_no != -1:
            rule.attrib['raw_line_no'] = str(raw_line_no)
        return rule

    def action(actiontype,target=''):
        elem = et.Element('action',{'type':actiontype})
        if actiontype == 'jump':
            elem.attrib['target'] = target
        return elem

    def proto(name, negated=False):
        elem = et.Element('proto')
        elem.text = name
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def ip(version,direction="", negated=False):
        elem = et.Element('ip',{'version':version})
        if direction != "":
            elem.attrib['direction'] = direction
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def address(addr,direction="",version="6", negated=False):
        ip = GenUtils.ip(version,direction)
        address = et.Element('address')
        address.text = addr
        ip.append(address)
        if negated: ip.attrib['negated'] = 'true'
        return ip

    def port(no,direction, negated=False):
        elem = et.Element('port',{'direction':direction})
        elem.text = no
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def icmp6type(typename, negated=False):
        elem = et.Element('icmp6type')
        elem.text = typename
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def icmp6limit(limit, negated=False):
        elem = et.Element('icmp6limit')
        elem.text = limit
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def state(statetype, negated=False):
        elem = et.Element('state')
        elem.text = statetype
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def tcp_flags(flags, negated=False):
        elem = et.Element('tcp-flags')
        elem.text = flags
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def ipv6header(negated=False):
        elem = et.Element('ipv6-header')
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def ipv6route(negated=False):
        elem = et.Element('ipv6-route')
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def rttype(no, negated=False):
        elem = et.Element('rt-type')
        elem.text = no
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def notrttype(no):
        elem = GenUtils.rttype(no)
        elem.attrib['negated'] = 'true'
        return elem

    def rtsegsleft(no, negated=False):
        elem = et.Element('rt-segs-left')
        elem.text = no
        if negated: elem.attrib['negated'] = 'true'
        return elem

    def notrtsegsleft(no):
        elem = GenUtils.rtsegsleft(no)
        elem.attrib['negated'] = 'true'
        return elem

    def vlan(no, direction=None, negated=False):
        elem = et.Element('vlan')
        elem.text = no
        if negated: elem.attrib['negated'] = 'true'
        if direction:
            elem.attrib['direction'] = direction
        return elem

    def interface(name, key, direction=None, negated=False):
        if not direction:
            elem = et.Element('interface',{'name':name,'key':key})
            if negated: elem.attrib['negated'] = 'true'
            return elem
        else:
            elem = et.Element('interface',{'direction':direction})
            elem.text = key
            if negated: elem.attrib['negated'] = 'true'
            return elem

    def connections():
        return et.Element('connections')

    def connection(target):
        return et.Element('interface',{'keyref':target})

    def routes():
        return et.Element('routes')

    def route(target,flag=True):
        elem = GenUtils.address(target,'dst')
        elem.attrib['negated'] = 'false' if flag else 'true'
        return elem

    def node(name):
        return et.Element('node',{'name':name})

    def nodeFirewall(key):
        return et.Element('firewall',{'keyref':key})

    def networks():
        return et.Element('networks')

    def network(name):
        return et.Element('network',{'name':name})
