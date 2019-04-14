#!/usr/bin/env python2

import re
import json
from xml.dom import minidom

ip4_regex = '(\d{1,3}(\.\d{1,3}){3}(/\d{1,5})?)'
m1 = re.match(ip4_regex, '1.2.3.4/5')
print m1.groups()
assert m1 is not None
ip6_regex = '([0-9a-f]{1,4}(::?[0-9a-f]{1,4}){1,7}(/\d{1,5})?)'
m2 = re.match(ip6_regex, '2001:db8::1/67')
print m2.groups()
assert m2 is not None
dst_regex = '(?P<dst>(%s|%s))?' % (ip4_regex, ip6_regex)
m3 = re.match(dst_regex, "123.123.231.1")
print m3.groups()
assert m3 is not None
m4 = re.match(dst_regex, "2001:db8:abc::def:1/123")
print m4.groups()
assert m4 is not None

type_regex = '(?P<type>\w+)?'
rtref_regex = '(?P<rtref>\d+)?'
next_hop_regex = '(?P<next_hop>(%s|%s))?' % (ip4_regex, ip6_regex)
action_regex = '(?P<action>\w+)?'
index_regex = '(?P<index>\d+)?'
nhref_regex = '(?P<nhref>\d+)?'
interface_regex = '(?P<interface>\w+)?'

row_regex = '^' + '\s+'.join([
    dst_regex,
    type_regex,
    rtref_regex,
    next_hop_regex,
    action_regex,
    index_regex,
    nhref_regex,
    interface_regex
]) + '$'

row_match = re.compile(row_regex)

with open("seat-show_route_forwarding-table_table_default.xml", "r") as f:
    lines = f.read().split("\n")
    maximum = 0
    minimum = 65535
    cnt = 0
    for line in lines:
        t = line.split()
        if line == '' or t == [] or line.startswith("<vn>") or line.startswith("Internet") or line.startswith("Destination") or line.startswith("Routing"):
            continue
        if len(t) > maximum:
            print "new maximum", len(t), t
        if len(t) < minimum:
            print "new minimum", len(t), t
        maximum = max(maximum, len(t))
        minimum = min(minimum, len(t))
        cnt += 1

    print "maximum:", maximum
    print "minimum:", minimum
    print "loc:", cnt

#test_line1 = '1.8.1.0/24         user     0                    indr 1048599  3789'
#m1 = re.match(row_match, test_line1)
#print m1.groupdict()
#assert m1 is not None
#test_line2 = '200.23.60.120/30              '
##test_line2 = '200.23.60.120/30   user     0 64.57.28.38        ucst  1210    62 ae8.10'
#m2 = re.match(row_match, test_line2)
#assert m2 is not None
#test_line3 = '                              64.57.28.38        ucst  1210    62 ae8.10'
#m3 = re.match(row_match, test_line3)
#assert m3 is not None


root = minidom.parse("seat-show_route_forwarding-table_table_default.xml")

routers = root.getElementsByTagName("router")
for router in routers:
    router_name = router.getAttribute("name")

    routing_table = []

    table = iter([l for l in router.childNodes[0].data.split("\n") if l])
    while True:
        line = table.next()

        if line.startswith("Routing table: default.mpls"):
            break

        elif line.startswith("Destination") or line.startswith("Routing") or line.startswith("Internet"):
            continue

        elif line.startswith("ISO"):
            for _ in range(5): table.next()

        tokens = line.split()

        if len(tokens) == 0:
            continue

        elif len(tokens) == 1:
            dst = tokens[0]
            line = table.next()

            tokens = line.split()
            if len(tokens) == 3:
                _type, _rtref, _next_hop = tokens

                line = table.next()
                tokens = line.split()

                if len(tokens) == 3:
                    _type, _index, _nhref = tokens
                    # XXX

            elif len(tokens) < 7:
                pass
                # XXX

            elif tokens[3] == 'ucst':
                _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                routing_table.append((int(dst.split('/')[1]), dst, [interface]))

            else:
                print "unknown action", len(tokens), tokens
                break

        elif len(tokens) == 3:
            if tokens[0] == 'locl':
                _type, _nhref, _nhref = tokens

            if tokens[0] == 'mcrt':
                _type, _index, _nhref = tokens
                # XXX

            else:
                print "unknown action", len(tokens), tokens

        elif len(tokens) == 4:
            dst, _type, _rtref, _next_hop = tokens
            line = table.next()
            tokens = line.split()

            if len(tokens) == 4:
                _type, _index, _nhref, interface = tokens
                routing_table.append((int(dst.split('/')[1]), dst, [interface]))

            else:
                print tokens
                break


        elif len(tokens) == 6:
            action = tokens[3]
            if action == 'ucst':
                dst, _type, _rtref, _type, _index, _nhref = tokens
                line = table.next()
                _next_hop, _type, _index, _nhref, interface = line.split()

                routing_table.append((int(dst.split('/')), dst, [interface]))

            elif action == 'indr':
                dst, _type, _rtref, _type, _index, _nhref = tokens
                line = table.next()
                tokens = line.split()
                if len(tokens) == 1:
                    _next_hop = tokens[0]
                    line = table.next()
                    tokens = line.split()
                    _type, _index, _nhref, interface = tokens

                    routing_table.append((int(dst.split('/')[1]), dst, [interface]))

                elif len(tokens) == 5:
                    _next_hop, _type, _index, _nhref, interface = tokens
                    routing_table.append((int(dst.split('/')[1]), dst, [interface]))


            elif action == 'dscd':
                dst, _type, _rtref, _type, _index, _nhref = tokens
                routing_table.append((int(dst.split('/')[1]), dst, []))

            elif action == 'ulst':
                dst, _type, _rtref, _type, _index, _nhref = tokens
                table.next()
                line = table.next()
                _next_hop, _type, _index, _nhref, if_1 = line.split()
                table.next()
                line = table.next()
                _next_hop, _type, _index, _nhref, if_2 = line.split()
                # XXX

            elif action == 'rslv':
                dst, _type, _rtref, _type, _index, _nhref = tokens

            elif action == 'mdsc':
                dst, _type, _rtref, _type, _index, _nhref = tokens
                routing_table.append((int(dst.split('/')[1]), dst, []))

            elif action == 'bcst':
                dst, _type, _rtref, _type, _index, _nhref = tokens
                # XXX

            elif action == 'rjct':
                dst, _type, _rtref, _type, _index, _nhref = tokens
                if dst == 'default':
                    routing_table.append((0, '0.0.0.0/0', []))
                else:
                    routing_table.append((int(dst.split('/')[1]), dst, []))

            else:
                print "unknown action:", action, len(tokens), tokens
                break


        elif len(tokens) == 7:
            if tokens[3] == 'rslv':
                dst, _type, _rtref, _type, _index, _nhref, interface = tokens
                # XXX

            elif tokens[4] == 'locl':
                dst, _type, _rtref, _next_hop, _type, _index, _nhref = tokens
                # XXX

            elif tokens[4] == 'mcst':
                dst, _type, _rtref, _next_hop, _type, _index, _nhref = tokens
                # XXX


            else:
                print "unknown action", len(tokens), tokens
                break


        elif len(tokens) == 8:
            action = tokens[4]
            if action == 'ucst':
                dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                routing_table.append((int(dst.split('/')[1]), dst, interface))

            elif action == 'recv':
                dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                # XXX

            elif action == 'bcst':
                dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                # XXX

            elif action == 'hold':
                dst, _type, _rtref, _next_hop, _type, _index, _nhref, interface = tokens
                # XXX


            else:
                print "unknown action", action, len(tokens), tokens
                break

        else:
            print "could not parse:", tokens


    from pprint import pprint
    pprint(sorted(routing_table, reverse=True))


#    for line in table:
        #row_regex = '^(?P<dst>((%s)|(%s)))?\s+(?P<type>\w+)?\s+(?P<rtref>\d?)?\s+(?P<next_hop>((%s)|(%s)))?\s+(?P<action>\w+)?\s+(?P<index>\d+)?\s+(?P<nhref>\d+)?\s+(?P<interface>\w+)?$' % (ip4_regex, ip6_regex, ip4_regex, ip6_regex)
#        row = re.match(row_match, line)
#        if row:
#            pass
#            #(row.group('dst'), row.group('next_hop'), row.group('interface'), row.group('action'))
#        else:
#            print "could not parse", line
#
#            #dst, _type, _rtref, next_hop, _action, _index, _nhref, interface = fields
