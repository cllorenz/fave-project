#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2023 Claas Lorenz
# List of co-authors:
#    Claas Lorenz <cllorenz@uni-potsdam.de>


# This file is part of Policy Translator.

# Policy Translator is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Policy Translator is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Policy Translator.  If not, see <https://www.gnu.org/licenses/>.

import argparse
import sys
import pyparsing as pp

from pprint import pprint, pformat

def run_test(subject_under_test, input_):
    print(
        "test parsing %s with input '%s'" % (subject_under_test, input_)
    )
    res = subject_under_test.parseString(input_)
    assert res
    print(
        "\ntest result: %s\n" % pformat(res.asList(), indent=4)
    )

def parse_fpl(raw_policy: str, use_tests=False):
    comment = pp.Char('#') + pp.SkipTo(pp.LineEnd())
    comment.setName('comment')

    quote = pp.Char("\"'")
    quote.setName('quote')

    name = pp.Word(pp.alphas, pp.alphanums)
    name.setName('name')

    value_word = pp.Word(pp.alphanums+".:/-_")
    value_word.setName('value_word')
    value_text = pp.Word(pp.alphanums+".:/-_ ")
    value_text.setName('value_text')
    quoted_value = pp.Suppress(quote) + value_text + pp.Suppress(quote)
    quoted_value.setName('quoted_value')

    single_value = quoted_value | \
                   value_word
    single_value.setName('single_value')

    values = single_value | \
             pp.Group(pp.Suppress('[') + \
                pp.delimitedList(single_value, ',') + \
             pp.Suppress(']'))
    values.setName('values')

    field = pp.Group(name + pp.Suppress('=') + values)
    field.setName('field')

    definition = pp.Literal('define') | \
                 pp.Literal('def') | \
                 pp.Literal('describe') | \
                 pp.Literal('desc')
    definition.setName('definition')

    role_name = pp.Word(pp.alphas, pp.alphanums)
    role_name.setName('role_name')

    include = pp.Group('includes' + role_name)
    include.setName('include')

    service_name = pp.Word(pp.alphas, pp.alphanums)
    service_name.setName('service_name')

    offer = pp.Group('offers' + service_name)
    offer.setName('offer')

    role = pp.Group(
        pp.Suppress(definition) + 'role' + role_name + pp.ZeroOrMore(
            pp.Suppress(comment) | \
            include | \
            offer | \
            field
        ) + pp.Suppress('end')
    )
    role.setName('role')

    proto = pp.Group(
        pp.Literal('protocol') + \
        pp.Suppress('=') + \
        pp.Suppress(quote) + \
        pp.Word(pp.alphas) + \
        pp.Suppress(quote)
    )
    proto.setName('proto')

    port = pp.Group(pp.Literal('port') + pp.Suppress('=') + pp.Word(pp.nums))
    port.setName('port')

    service = pp.Group(pp.Suppress(definition) + \
              'service' + \
              service_name + \
              proto + \
              pp.Optional(port) + \
              pp.Suppress('end'))
    service.setName('service')

    inventory = pp.Optional(pp.Suppress(comment)) + pp.OneOrMore(
        pp.Optional(pp.Suppress(comment)) + (role | service)
    )
    inventory.setName('inventory')

    subject = role_name
    subject.setName('subject')
    object_ = pp.Group(role_name + pp.Optional(
        pp.Suppress(pp.Char('.')) + (service_name | pp.Char('*'))
    ))
    object_.setName('object_')
    operator = pp.Literal('--->') | \
               pp.Literal('<-->') | \
               pp.Literal('<->>') | \
               pp.Literal('--/->') | \
               pp.Literal('<-/->') | \
               pp.Literal('-/->>')
    operator.setName('operator')

    rule = pp.Group(subject + operator + object_)
    rule.setName('rule')

    default_policy = pp.Literal('allow') | \
                     pp.Literal('deny')
    default_policy.setName('default_policy')

    default_rule = pp.Suppress('default:') + default_policy
    default_rule.setName('default_rule')

    policy = pp.Group(
        pp.Optional(pp.Suppress(comment)) + \
        pp.Suppress(definition) + \
            'policies' + \
            pp.Suppress('(') + \
                default_rule + \
            pp.Suppress(')') + \
        pp.OneOrMore(pp.Suppress(comment) | rule) + \
        pp.Suppress('end')
    )
    policy.setName('policy')

    fpl = comment | pp.Optional(inventory) + pp.Optional(policy)
    fpl.setName('fpl')

    if use_tests:
        test_name = 'ipv6'
        test_value_word = '2001:db8::100/120'
        test_value_text = "The public file server in the DMZ."
        test_quoted = "'admin.cs.uni-potsdam.de'"
        test_qlist = '[' + test_quoted + ", '" + test_value_text + "'" + ']'
        test_field = test_name + ' = ' + test_value_word
        test_field_list = "hosts = ['cluster.cs.uni-potsdam.de', 'printer.cs.uni-potsdam.de']"
        test_role = 'WithInternetAccess'
        test_include = 'includes ' + test_role
        test_service = 'ICMPv6'
        test_offer = 'offers ' + test_service
        test_role_minimal = 'def role Servers end'
        test_role_field = 'def role Servers\n\tipv6 = 2001:db8::100/120\nend'
        test_role_field_list = "def role Intern\n\thosts = ['cluster.cs.uni-potsdam.de', 'printer.cs.uni-potsdam.de']\n\tvlan = 6\nend"
        test_role_include_field = 'def role Servers\n\tincludes WebServers\n\tipv6 = 2001:db8::100/120\nend'
        test_role_include_offer_field = 'def role Servers\n\tincludes WebServers\n\toffers SSH\n\tipv6 = 2001:db8::100/120\nend'
        test_proto = "protocol = 'foo'"
        test_port = 'port = 1234'
        test_service_icmp = "desc service ICMP\n\tprotocol = 'icmp'\nend"
        test_service = "desc service SSH\n\tprotocol = 'tcp'\n\tport = 22\nend"
        test_object_simple = 'WebServer'
        test_object = 'WebServer.HTTP'
        test_object_ast = 'Servers.*'
        test_rule = 'Clients <->> WebServer.HTTP'
        test_policy = 'define policies(default: deny)\n\tClients <->> WebServer.HTTP\nend'
        test_fpl_comment = "# Some comment!\n"
        test_fpl_inventory = "def role Servers\n\tincludes WebServers\n\toffers SSH\n\tipv6 = 2001:db8::100/120\nend\n\ndesc service ICMP\n\tprotocol = 'icmp'\nend\n\ndesc service SSH\n\tprotocol = 'tcp'\n\tport = 22\nend"
        test_inventory = "def role Servers\n\tincludes WebServers\n\toffers SSH\n\tipv6 = 2001:db8::100/120\nend\n\ndesc service ICMP\n\tprotocol = 'icmp'\nend\n\ndesc service SSH\n\tprotocol = 'tcp'\n\tport = 22\nend"


        tests = [
            (comment, '# This is some random comment!\n'),
            (name, test_name),
            (value_word, test_value_word),
            (quoted_value, test_quoted),
            (value_text, test_value_text),
            (values, test_quoted),
            (values, test_qlist),
            (field, test_field),
            (field, test_field_list),
            (definition, 'def'),
            (role_name, test_role),
            (include, test_include),
            (service_name, test_service),
            (offer, test_offer),
            (role, test_role_minimal),
            (role, test_role_field),
            (role, test_role_field_list),
            (role, test_role_include_field),
            (role, test_role_include_offer_field),
            (proto, test_proto),
            (port, test_port),
            (service, test_service_icmp),
            (service, test_service),
            (inventory, test_inventory),
            (object_, test_object_simple),
            (object_, test_object),
            (object_, test_object_ast),
            (rule, test_rule),
            (policy, test_policy),
            (fpl, test_fpl_comment),
            (fpl, test_fpl_inventory),
            (fpl, test_policy),
            (fpl, test_fpl_inventory + '\n\n' + test_policy)
        ]

        for test in tests:
            run_test(*test)

    else:
        res = fpl.parseString(raw_policy)
        return res.asList()

head_tail = lambda lst: (lst[0], lst[1:])

prosa_list = lambda lst: (', '.join(lst[:-1]) + ', and ' + lst[-1]) if len(lst) > 2 else ' and '.join(lst)

operator_to_str = {
    '--->' : 'unidirectionally',
    '<-->' : 'bidirectionally',
    '<->>' : 'statefully',
    '--/->' : 'unidirectionally',
    '<-/->' : 'bidirectionally',
    '<-/->>' : 'statefully'
}


def print_prosa(fpl_policy):
    for entry in fpl_policy:
        head, tail = head_tail(entry)

        if head == 'role':
            role_name, attributes = head_tail(tail)
            includes = [v for a,v in attributes if a == 'includes']
            services = [v for a,v in attributes if a == 'offers']
            attributes = [f"{a}={v}" for a,v in attributes if a not in [
                'includes', 'offers', 'description'
            ]]

            includes_str = (
                'includes the roles ' + prosa_list(includes)
            ) if includes else ''
            offers_str = (
                'offers the services ' + prosa_list(services)
            ) if services else ''
            attributes_str = (
                'has the attributes ' + prosa_list(attributes)
            ) if attributes else ''

            print(
                f"The role {role_name} {prosa_list([s for s in [includes_str, offers_str, attributes_str] if s != ''])}."
            )

        elif head == 'service':
            service_name, attributes = head_tail(tail)
            try:
                proto, port = attributes
                _, proto_str = proto
                _, port = port
                port_str = f' port {port}'
            except ValueError:
                proto = attributes[0]
                _, proto_str = proto.upper()
                port_str = ''

            print(
                f"The service {service_name} runs on {proto_str.upper()}{port_str}."
            )

        elif head == 'policies':
            default, rules = head_tail(tail)
            print(f"By default the policy {'allows' if default == 'allow' else 'denies'} accesses.")

            default_str = 'may' if default == 'deny' else 'may not'

            for rule in rules:
                subject, operator, object_ = rule
                try:
                    object_, service = object_
                    object_str = f"the role {object_}"
                    service_str = f"service {service} offered by " if service != '*' else 'all services offered by '
                except ValueError:
                    object_str = f"the role {object_.pop()}"
                    service_str = ''

                operator_str = ' ' + operator_to_str[operator]

                print(
                    f"The role {subject} {default_str} access {service_str}{object_str}{operator_str}."
                )

        else:
            print(f"cannot handle entry: {entry}. Abort!")
            break


def main(argv):
    parser = argparse.ArgumentParser(
        description='Parses FPL inventories and policies.'
    )
    parser.add_argument(
        'files',
        metavar='FILE',
        nargs='+',
        help='inventory and policy files (or files that integrate both)'
    )
    parser.add_argument(
        '-t',
        '--tests',
        dest='use_tests',
        action='store_const',
        const=True,
        default=False,
        help='run self tests'
    )

    parser.add_argument(
        '-p',
        '--prosa',
        dest='use_prosa',
        action='store_const',
        const=True,
        default=False,
        help='print a prosaic representation'
    )

    args = parser.parse_args(argv)

    for fpl_file in args.files:
        with open(fpl_file, 'r') as f:
            res = parse_fpl(f.read(), use_tests=args.use_tests)
            if args.use_prosa:
                print_prosa(res)
            else:
                pprint(res, indent=4)

if __name__ == '__main__':
    main(sys.argv[1:])
