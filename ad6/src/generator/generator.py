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



import random
import math
import lxml.etree as et

from copy import deepcopy

from src.xml.genutils import GenUtils

class Generator:
    def _firewall(self,fwname,services=([],[],[],[]),intable=True,outtable=True,fwdtable=True,minimal=False,gateway=False):
        publictcp,privatetcp,publicudp,privateudp = services
        firewall = GenUtils.firewall(fwname)
        tables = []
        if intable:
            inputtable = GenUtils.table('input')

            index = 0
            if minimal:
                rule = GenUtils.rule(str(index))
                rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                if intable:
                    inputtable = GenUtils.table('input')
                    inputtable.append(rule)
                    tables.append(inputtable)
                if outtable:
                    outputtable = GenUtils.table('output')
                    outputtable.append(deepcopy(rule))
                    tables.append(outputtable)
                if fwdtable:
                    forwardtable = GenUtils.table('forward')
                    forwardtable.append(deepcopy(rule))
                    tables.append(forwardtable)
    
            else:
                rule = GenUtils.rule(str(index))
                rule.append(GenUtils.proto('icmp6'))
                rule.append(GenUtils.icmp6type('destination-unreachable'))
                rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                inputtable.append(rule)

                index += 1
                rule = GenUtils.rule(str(index))
                rule.append(GenUtils.proto('icmp6'))
                rule.append(GenUtils.icmp6type('packet-too-big'))
                rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                inputtable.append(rule)

                index += 1
                rule = GenUtils.rule(str(index))
                rule.append(GenUtils.proto('icmp6'))
                rule.append(GenUtils.icmp6type('time-exceeded'))
                rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                inputtable.append(rule)

                index += 1
                rule = GenUtils.rule(str(index))
                rule.append(GenUtils.proto('icmp6'))
                rule.append(GenUtils.icmp6type('parameter-problem'))
                rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                inputtable.append(rule)

                index += 1
                rule = GenUtils.rule(str(index))
                rule.append(GenUtils.proto('icmp6'))
                rule.append(GenUtils.icmp6type('echo-request'))
                rule.append(GenUtils.icmp6limit('900-m'))
                rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                inputtable.append(rule)

                index += 1
                rule = GenUtils.rule(str(index))
                rule.append(GenUtils.proto('icmp6'))
                rule.append(GenUtils.icmp6type('echo-reply'))
                rule.append(GenUtils.icmp6limit('900-m'))
                rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                inputtable.append(rule)

                index += 1
                rule = GenUtils.rule(str(index))
                rule.append(GenUtils.proto('icmp6'))
                rule.append(GenUtils.icmp6type('neighbor-solicitation'))
                rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                inputtable.append(rule)

                index += 1
                rule = GenUtils.rule(str(index))
                rule.append(GenUtils.proto('icmp6'))
                rule.append(GenUtils.icmp6type('neighbor-advertisement'))
                rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                inputtable.append(rule)

                if not gateway:
                    for public in publictcp:
                        index += 1
                        rule = self._publicservice(index,public,'tcp',False)
                        rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                        inputtable.append(rule)

                    for private in privatetcp:
                        index += 1
                        rule = self._privateservice(index,private,'tcp',False)
                        rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                        inputtable.append(rule)

                    for public in publicudp:
                        index += 1
                        rule = self._publicservice(index,public,'udp',False)
                        rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                        inputtable.append(rule)

                    for private in privateudp:
                        index += 1
                        rule = self._privateservice(index,private,'udp',False)
                        rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                        inputtable.append(rule)

                index += 1
                rule = GenUtils.rule(str(index))
                rule.append(GenUtils.action('jump',fwname+'_drop_r0'))
                inputtable.append(rule)

                tables.append(inputtable)

                if outtable:
                    outputtable = GenUtils.table('output')

                    rule = GenUtils.rule('0')
                    rule.append(GenUtils.proto('icmp6'))
                    rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                    outputtable.append(rule)

                    rule = GenUtils.rule('1')
                    rule.append(GenUtils.state('NEW'))
                    rule.append(GenUtils.state('ESTABLISHED'))
                    rule.append(GenUtils.state('RELATED'))
                    rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                    outputtable.append(rule)

                    rule = GenUtils.rule('2')
                    rule.append(GenUtils.action('jump',fwname+'_drop_r0'))
                    outputtable.append(rule)

                    tables.append(outputtable)

                if fwdtable:
                    forwardtable = GenUtils.table('forward')

                    index = 0
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.proto('icmp6'))
                    rule.append(GenUtils.icmp6type('destination-unreachable'))
                    rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                    forwardtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.proto('icmp6'))
                    rule.append(GenUtils.icmp6type('packet-too-big'))
                    rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                    forwardtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.proto('icmp6'))
                    rule.append(GenUtils.icmp6type('parameter-problem'))
                    rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                    forwardtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.proto('icmp6'))
                    rule.append(GenUtils.icmp6type('echo-request'))
                    rule.append(GenUtils.icmp6limit('900-m'))
                    rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                    forwardtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.proto('icmp6'))
                    rule.append(GenUtils.icmp6type('echo-reply'))
                    rule.append(GenUtils.icmp6limit('900-m'))
                    rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                    forwardtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.proto('icmp6'))
                    rule.append(GenUtils.icmp6type('neighbor-solicitation'))
                    rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                    forwardtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.proto('icmp6'))
                    rule.append(GenUtils.icmp6type('neighbor-advertisement'))
                    rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                    forwardtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.ipv6header())
                    rule.append(GenUtils.ipv6route())
                    rule.append(GenUtils.action('jump',fwname+'_routinghdr_r0'))
                    forwardtable.append(rule)
                    routingindex = index + 1

                    for public in publictcp:
                        index += 1
                        rule = self._publicservice(index,public,'tcp')
                        rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                        forwardtable.append(rule)

                    for private in privatetcp:
                        index += 1
                        rule = self._privateservice(index,private,'tcp')
                        rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                        forwardtable.append(rule)

                    for public in publicudp:
                        index += 1
                        rule = self._publicservice(index,public,'tcp')
                        rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                        forwardtable.append(rule)

                    for private in privatetcp:
                        index += 1
                        rule = self._privateservice(index,private,'tcp')
                        rule.append(GenUtils.action('jump',fwname+'_accept_r0'))
                        forwardtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.action('jump',fwname+'_drop_r0'))
                    forwardtable.append(rule)

                    tables.append(forwardtable)

                    routinghdrtable = GenUtils.table('routinghdr')
                    index = 0
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.rttype('0'))
                    rule.append(GenUtils.notrtsegsleft('0'))
                    rule.append(GenUtils.action('jump',fwname+'_drop_r0'))
                    routinghdrtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.rttype('2'))
                    rule.append(GenUtils.notrtsegsleft('1'))
                    rule.append(GenUtils.action('jump',fwname+'_drop_r0'))
                    routinghdrtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.rttype('0'))
                    rule.append(GenUtils.rtsegsleft('0'))
                    rule.append(GenUtils.action('jump',fwname+'_forward_r'+str(routingindex)))
                    routinghdrtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.rttype('2'))
                    rule.append(GenUtils.rtsegsleft('1'))
                    rule.append(GenUtils.action('jump',fwname+'_forward_r'+str(routingindex)))
                    routinghdrtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.notrtsegsleft('0'))
                    rule.append(GenUtils.action('jump',fwname+'_drop_r0'))
                    routinghdrtable.append(rule)

                    index += 1
                    rule = GenUtils.rule(str(index))
                    rule.append(GenUtils.action('jump',fwname+'_forward_r'+str(routingindex)))
                    routinghdrtable.append(rule)

                    tables.append(routinghdrtable)


        accepttable = GenUtils.table('accept')
        rule = GenUtils.rule('0',fwname+'_accept_r0')
        rule.append(GenUtils.action('accept'))
        accepttable.append(rule)

        droptable = GenUtils.table('drop')
        rule = GenUtils.rule('0',fwname+'_drop_r0')
        rule.append(GenUtils.action('drop'))
        droptable.append(rule)

        tables.extend([accepttable,droptable])

        firewall.extend(tables)

        return firewall


    def _service(self,index,service,proto,public=True,fwdtable=True):
        rule = GenUtils.rule(str(index))

        if public:
            dst,port = service
        else:
            dst,port,src = service
            rule.append(GenUtils.address(src,'src'))

        rule.append(GenUtils.proto(proto))
        if fwdtable:
            rule.append(GenUtils.address(dst,'dst'))
        rule.append(GenUtils.port(port,'dst'))

        return rule

    def _publicservice(self,index,service,proto,fwdtable=True):
        return self._service(index,service,proto,True,fwdtable)

    def _privateservice(self,index,service,proto,fwdtable=True):
        return self._service(index,service,proto,False,fwdtable)


    def _interface(self,name,key,connections=[],routes=[]):
        interface = GenUtils.interface(name,key)

        if connections != []:
            conns = GenUtils.connections()
            interface.append(conns)
        for connection in connections:
            conns.append(GenUtils.connection(connection))

        if routes != []:
            rts = GenUtils.routes()
            interface.append(rts)
        for route in routes:
            rts.append(GenUtils.route(*route))

        return interface

    def _node(self,name,ip,interfaces,firewall):
        node = GenUtils.node(name)
        node.extend([self._interface(*interface) for interface in interfaces])
        node.append(GenUtils.nodeFirewall(firewall))
        node.append(GenUtils.address(ip))
        return node

    def _network(self,name,nodes):
        network = GenUtils.network(name)
        network.extend([self._node(*node) for node in nodes])
        return network


    def _config(self,firewalls,networks):
        config = GenUtils.config()
        fws = GenUtils.firewalls()
        fws.extend(firewalls)

        nets = GenUtils.networks()
        nets.extend(networks)

        config.extend([fws,nets])

        return config


    def generate(self):
        firewalls = []
        names = []

        gatewaypublictcp = []
        gatewayprivatetcp = []
        gatewaypublicudp = []
        gatewayprivateudp = []

        nets = [('api','2001:abc:def:3::1','2001:abc:def:1003::0/64'),
            ('asta','2001:abc:def:4::1','2001:abc:def:1004::0/64'),
            ('bgp','2001:abc:def:5::1','2001:abc:def:1005::0/64'),
            ('chem','2001:abc:def:6::1','2001:abc:def:1006::0/64'),
            ('cs','2001:abc:def:7::1','2001:abc:def:1007::0/64'),
            ('geo','2001:abc:def:8::1','2001:abc:def:1008::0/64'),
            ('geog','2001:abc:def:9::1','2001:abc:def:1009::0/64'),
            ('hgp','2001:abc:def:a::1','2001:abc:def:100a::0/64'),
            ('hpi','2001:abc:def:b::1','2001:abc:def:100b::0/64'),
            ('hssp','2001:abc:def:c::1','2001:abc:def:100c::0/64'),
            ('intern','2001:abc:def:d::1','2001:abc:def:100f::0/64'),
            ('jura','2001:abc:def:e::1','2001:abc:def:100e::0/64'),
            ('ling','2001:abc:def:f::1','2001:abc:def:100f::0/64'),
            ('math','2001:abc:def:10::1','2001:abc:def:1010::0/64'),
            ('mmz','2001:abc:def:11::1','2001:abc:def:1011::0/64'),
            ('physik','2001:abc:def:12::1','2001:abc:def:1012::0/64'),
            ('pogs','2001:abc:def:13::1','2001:abc:def:1013::0/64'),
            ('psych','2001:abc:def:14::1','2001:abc:def:1014::0/64'),
            ('sq','2001:abc:def:15::1','2001:abc:def:1015::0/64'),
            ('stud','2001:abc:def:16::1','2001:abc:def:1016::0/64'),
            ('ub','2001:abc:def:17::1','2001:abc:def:1017::0/64'),
            ('welc','2001:abc:def:18::1','2001:abc:def:1018::0/64'),
        ]

        for net,ip,pips in nets:
            publictcp = [(ip,str(port)) for port in [80,443,5060,5061,25,587,110,143,220,465,993,995]]
            gatewaypublictcp.extend(publictcp)
            privatetcp = [(ip,str(port),pips) for port in [22,631,137,138,139,445,2049]]
            gatewayprivatetcp.extend(privatetcp)
            publicudp = [(ip,str(port)) for port in [5060,143,220]]
            gatewaypublicudp.extend(publicudp)
            privateudp = [(ip,str(port),pips) for port in [22,631,137,138,139]]
            gatewayprivateudp.extend(privateudp)

            name = net + '_server_fw'
            services = (publictcp,privatetcp,publicudp,privateudp)

            normalfw = (name,services,True,True,False,False)
            firewalls.append(self._firewall(*normalfw))

        server = [
            ('ups_file_fw','2001:abc:def:1::1',([21,115],[22],[],[22])),
            ('ups_mail_fw','2001:abc:def:1::2',([25,587,110,143,220,465,993,995],[22],[143,220],[22])),
            ('ups_web_fw','2001:abc:def:1::3',([80,443],[22],[],[22])),
            ('ups_ldap_fw','2001:abc:def:1::4',([389,636],[22],[389,123],[22])),
            ('ups_vpn_fw','2001:abc:def:1::5',([1194,1723],[22],[1194,1723],[22])),
            ('ups_dns_fw','2001:abc:def:1::6',([53],[22],[53],[22])),
            ('ups_data_fw','2001:abc:def:1::7',([],[22,118,156],[],[22,118,156])),
            ('ups_admin_fw','2001:abc:def:1::8',([21,115],[22],[],[22,161])),
        ]
        pip = '2001:abc:def:2::0/64'

        for name,ip,services in server:
            publictcp,privatetcp,publicudp,privateudp = services
            publictcp = [(ip,str(port)) for port in publictcp]
            gatewaypublictcp.extend(publictcp)
            privatetcp = [(ip,str(port),pip) for port in privatetcp]
            gatewayprivatetcp.extend(privatetcp)
            publicudp = [(ip,str(port)) for port in publicudp]
            gatewaypublicudp.extend(publicudp)
            privateudp = [(ip,str(port),pip) for port in privateudp]
            gatewayprivateudp.extend(privateudp)
            services = (publictcp,privatetcp,publicudp,privateudp)
            serverfw = (name,services,True,True,True,False)

            firewalls.append(self._firewall(*serverfw))


        services = (gatewaypublictcp,gatewayprivatetcp,gatewaypublicudp,gatewayprivateudp)
        name = 'up_gateway_fw'

        gatewayfw = (name,services,True,True,True,False,True)
        firewalls.append(self._firewall(*gatewayfw))


        services = ([],[],[],[])
        names = ['upc_client0_fw','upc_client1_fw','internet_provider_fw','api_client_fw','asta_client_fw','bgp_client_fw','chem_client_fw','cs_client_fw','geo_client_fw','geom_client_fw','hgp_client_fw','hpi_client_fw','hssp_client_fw','intern_client_fw','jura_client_fw','ling_client_fw','math_client_fw','mmz_client_fw','physik_client_fw','pogs_client_fw','psych_client_fw','sq_client_fw','stud_client_fw','ub_client_fw','welc_client_fw']
        for name in names:
            clientfw = (name,services,True,True,False,True)
            firewalls.append(self._firewall(*clientfw))


        names = ['ups_switch_fw','upc_router_fw']
        for name in names:
            switchfw = (name,services,False,False,True,True)
            firewalls.append(self._firewall(*switchfw))


        networks = []
        nets = {}
        nets['internet'] = [(
            'provider',
            '2001::1',
            [('ppp0',
                'internet_provider_ppp0',
                ['up_gateway_ppp0'],
                [('2001:abc:def::0/48',True)]
            )],
            'internet_provider_fw'
        )]

        names = ['api','asta','bgp','chem','cs','geo','geom','hgp','hpi','hssp','intern','jura','ling','math','mmz','physik','pogs','psych','sq','stud','ub','welc']

        interfaces = [('ppp0',
                'up_gateway_ppp0',
                ['internet_provider_ppp0'],
                [('2001:abc:def::0/48',False)]
            ),('eth0',
                'up_gateway_eth0',
                ['ups_switch_eth0'],
                [('2001:abc:def:1::0/64',True)]
            ),('eth1','up_gateway_eth1',
                ['upc_router_eth0'],
                [('2001:abc:def:2::0/64',True)]
            )]

        index = 3
        for name in names:
            interface = ('eth'+str(2*index-3),
                'up_gateway_eth'+str(2*index-3),
                [name+'_server_eth0'],
                [('2001:abc:def:'+str(index)+'::0/64',True)]
            )
            interfaces.append(interface)
            interface = ('eth'+str(2*index-2),
                name+'_client_eth'+str(2*index-2),
                [name+'_client_eth0'],
                [('2001:abc:def:1'+'{:03x}'.format(index)+'::0/64',True)]
            )
            interfaces.append(interface)
            index += 1

        nets['up'] = [(
            'gateway',
            '2001:abc:def::1',
            interfaces,
            'up_gateway_fw'
        )]

        nets['ups'] = []
        nets['ups'].append((
            'switch',
            '2001:abc:def:1::ffff',
            [('eth0',
                'ups_switch_eth0',
                ['up_gateway_eth0'],
                [('2001:abc:def:1::0/64',False)]
            ),('eth1',
                'ups_switch_eth1',
                ['ups_file_eth0'],
                [('2001:abc:def:1::1',True)]
            ),('eth2',
                'ups_switch_eth2',
                ['ups_mail_eth0'],
                [('2001:abc:def:1::2',True)]
            ),('eth3',
                'ups_switch_eth3',
                ['ups_web_eth0'],
                [('2001:abc:def:1::3',True)]
            ),('eth4',
                'ups_switch_eth4',
                ['ups_ldap_eth0'],
                [('2001:abc:def:1::4',True)]
            ),('eth5',
                'ups_switch_eth5',
                ['ups_vpn_eth0'],
                [('2001:abc:def:1::5',True)]
            ),('eth6',
                'ups_switch_eth6',
                ['ups_dns_eth0'],
                [('2001:abc:def:1::6',True)]
            ),('eth7',
                'ups_switch_eth7',
                ['ups_data_eth0'],
                [('2001:abc:def:1::7',True)]
            ),('eth8',
                'ups_switch_eth8',
                ['ups_admin_eth0'],
                [('2001:abc:def:1::8',True)]
            )],
            'ups_switch_fw'
        ))
        nets['ups'].append((
            'file',
            '2001:abc:def:1::1',
            [('eth0',
                'ups_file_eth0',
                ['ups_switch_eth1'],
                [('2001:abc:def:1::1',False)],
            )],
            'ups_file_fw'
        ))
        nets['ups'].append((
            'mail',
            '2001:abc:def:1::2',
            [('eth0',
                'ups_mail_eth0',
                ['ups_switch_eth2'],
                [('2001:abc:def:1::2',False)],
            )],
            'ups_mail_fw'
        ))
        nets['ups'].append((
            'web',
            '2001:abc:def:1::3',
            [('eth0',
                'ups_web_eth0',
                ['ups_switch_eth3'],
                [('2001:abc:def:1::3',False)],
            )],
            'ups_web_fw'
        ))
        nets['ups'].append((
            'ldap',
            '2001:abc:def:1::4',
            [('eth0',
                'ups_ldap_eth0',
                ['ups_switch_eth4'],
                [('2001:abc:def:1::4',False)],
            )],
            'ups_ldap_fw'
        ))
        nets['ups'].append((
            'vpn',
            '2001:abc:def:1::5',
            [('eth0',
                'ups_vpn_eth0',
                ['ups_switch_eth5'],
                [('2001:abc:def:1::5',False)],
            )],
            'ups_vpn_fw'
        ))
        nets['ups'].append((
            'dns',
            '2001:abc:def:1::6',
            [('eth0',
                'ups_dns_eth0',
                ['ups_switch_eth6'],
                [('2001:abc:def:1::6',False)],
            )],
            'ups_dns_fw'
        ))
        nets['ups'].append((
            'data',
            '2001:abc:def:1::7',
            [('eth0',
                'ups_data_eth0',
                ['ups_switch_eth7'],
                [('2001:abc:def:1::7',False)],
            )],
            'ups_data_fw'
        ))
        nets['ups'].append((
            'admin',
            '2001:abc:def:1::8',
            [('eth0',
                'ups_admin_eth0',
                ['ups_switch_eth8'],
                [('2001:abc:def:1::8',False)],
            )],
            'ups_admin_fw'
        ))
        nets['upc'] = []
        nets['upc'].append((
            'router',
            '2001:abc:def:2::ffff',
            [('eth0',
                'upc_router_eth0',
                ['up_gateway_eth1'],
                [('2001:abc:def:2::0/64',False)]
            ),('eth1',
                'upc_router_eth1',
                ['upc_client0_eth0'],
                [('2001:abc:def:2:1::0/80',True)]
            ),('wlan0',
                'upc_router_wlan0',
                ['upc_client1_wlan0'],
                [('2001:abc:def:2:2::0/80',True)]
            )],
            'upc_router_fw'
        ))
        nets['upc'].append((
            'client0',
            '2001:abc:def:2:1::1',
            [('eth0',
                'upc_client0_eth0',
                ['upc_router_eth1'],
                [('2001:abc:def:2:1::1',False)]
            )],
            'upc_client0_fw'
        ))
        nets['upc'].append((
            'client1',
            '2001:abc:def:2:2::1',
            [('wlan0',
                'upc_client1_wlan0',
                ['upc_router_wlan0'],
                [('2001:abc:def:2:2::1',False)]
            )],
            'upc_client1_fw'
        ))


        index = 3
        for name in names:
            ip = '2001:abc:def:' + str(index) + '::1'

            nets[name] = []
            nets[name].append((
                'server',
                ip,
                [('eth0',
                    name+'_server_eth0',
                    ['up_gateway_eth'+str(2*index-3)],
                    [(ip,False)]
                )],
                name+'_server_fw'
            ))
            ip = '2001:abc:def:1' + '{:03x}'.format(index) + '::1'
            nets[name].append((
                'client',
                ip,
                [('eth0',
                    name+'_client_eth0',
                    ['up_gateway_eth'+str(2*index-2)],
                    [(ip,False)]
                )],
                name+'_client_fw'
            ))
            index += 1


        for name in nets:
            network = (name,nets[name])
            networks.append(self._network(*network))

        config = self._config(firewalls,networks)

        return config
