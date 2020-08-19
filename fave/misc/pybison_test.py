#!/usr/bin/env python2

""" This module provides a fast parser for ip6tables rule sets based on GNU Flex
    and Bison.
"""

import sys

from bison import BisonParser
from util.tree_util import Tree

class IP6TablesParser(BisonParser):
    """ This class provides a fast ip6tables parser.
    """

    bisonEngineLibName = "ip6tables-parser"
    interactive = False

    tokens = [
        'IPT6', 'IPT', 'POLICY_CMD', 'APPEND_CMD', 'ACCEPT', 'DROP', 'RJCT', 'TABLE',
        'JUMP_SHORT', 'JUMP_LONG', 'NEGATION', 'ARG_SHORT', 'ARG_LONG',
        'MOD_SHORT', 'MOD_LONG', 'OUT_SHORT', 'OUT_LONG', 'IN_SHORT', 'IN_LONG',
        'SPORT', 'DPORT', 'PROTO_SHORT', 'PROTO_LONG', 'SRC_SHORT', 'SRC_LONG',
        'DST_SHORT', 'DST_LONG', 'PORTNO', 'PORTRANGE', 'IPV6_CIDR', 'IPV4_CIDR', 'IDENT', 'WORD',
        'NEWLINE', 'WS', 'COMMENT', 'FLAGS', 'STATES', 'DPORTS', 'SPORTS'
    ]

    _ast = None
    precedences = ()

    start = 'ruleset'

    def on_ruleset(self, *_args, **kwargs):
        """
        ruleset :
                | ruleset line
                | ruleset comment
        """
        target = kwargs["target"]
        option = kwargs["option"]
        names = kwargs["names"]
        values = kwargs["values"]

        if option == 0:
            return []
        elif option == 1:
            if values[1] is not None:
                self._ast.add_child(values[1])
            return self._ast
        elif option == 2:
            return self._ast
        else:
            raise "unexpected option for %s: %s with %s and %s", (target, option, names, values)


    def on_comment(self, *_args, **_kwargs):
        """
        comment : COMMENT NEWLINE
        """
        return None


    def on_line(self, *_args, **kwargs):
        """
        line : NEWLINE
             | ipt WS table APPEND_CMD WS IDENT body WS jump NEWLINE
             | ipt WS table POLICY_CMD WS IDENT WS action NEWLINE
        """
        target = kwargs["target"]
        option = kwargs["option"]
        names = kwargs["names"]
        values = kwargs["values"]

        if option == 0:
            return None

        elif option == 1:
            ipt, _ws, table, append_cmd, _ws, ident, body, _ws, jump, _nl = values

            flat_table = [" %s %s" % (table.value, table.get_last().value)] if table else []

            flat_body = []
            for arg in body:
                if arg.get_last().is_negated():
                    flat_body.append("! %s %s " % (arg.value, arg.get_last().value))
                else:
                    flat_body.append("%s %s " % (arg.value, arg.get_last().value))

            flat_jump = [jump.value, ' ', jump.get_last().value]

            line = Tree("".join(
                [ipt] + flat_table + [' '] + values[3:6] + [' '] + flat_body + flat_jump
            ))

            tmp = line.add_child(append_cmd)
            tmp.add_child(ident)
            tmp.add_children(body)
            tmp.add_child(jump)

            if table:
                line.add_child(table)
            else:
                line.add_child('-t').add_child('filter')

            has_sports = tmp.has_child('--sports')
            has_dports = tmp.has_child('--dports')
            if has_sports:
                sports = tmp.get_child('--sports')
                val = sports.get_first().value
                first, _last = val.split(':') # XXX: implement interval handling
                sports.value = '--sport'
                sports.get_first().value = first

            if has_dports:
                dports = tmp.get_child('--dports')
                val = dports.get_first().value
                first, _last = val.split(':') # XXX: implement interval handling
                dports.value = '--dport'
                dports.get_first().value = first

            return line

        elif option == 2:
            _ipt, _ws, table, policy_cmd, _ws, ident, _ws, action, _nl = values

            flat_table = ["%s %s " % (table.value, table.get_last().value)] if table else []
            flat_action = [action.value]

            line = Tree("".join(values[:2] + flat_table + values[3:7] + flat_action))
            if table:
                line.add_child(table)

            tmp = line.add_child(policy_cmd)
            tmp = tmp.add_child(ident)
            tmp.add_child(action)

            if table:
                line.add_child(table)
            else:
                line.add_child('-t').add_child('filter')

            return line

        else:
            raise "unexpected option for %s: %s with %s and %s", (target, option, names, values)

    def on_ipt(self, *_args, **kwargs):
        """
        ipt : IPT6
            | IPT
        """
        return kwargs['values'][0]


    def on_table(self, *_args, **kwargs):
        """
        table :
              | TABLE WS IDENT WS
        """
        target = kwargs["target"]
        option = kwargs["option"]
        names = kwargs["names"]
        values = kwargs["values"]

        if option == 0:
            return None
        elif option == 1:
            arg, _ws, val, _ws = values
            ret = Tree(arg)
            ret.add_child(val)
            return ret
        else:
            raise "unexpected option for %s: %s with %s and %s", (target, option, names, values)


    def on_body(self, *_args, **kwargs):
        """
        body :
             | body WS neg_argument
        """
        target = kwargs["target"]
        option = kwargs["option"]
        names = kwargs["names"]
        values = kwargs["values"]

        if option == 0:
            return []
        elif option == 1:
            body = values[0]
            body.append(values[2])
            return body
        else:
            raise "unexpected option for %s: %s with %s and %s", (target, option, names, values)


    def on_neg_argument(self, *_args, **kwargs):
        """
        neg_argument : NEGATION WS argument
                     | argument
        """
        target = kwargs["target"]
        option = kwargs["option"]
        names = kwargs["names"]
        values = kwargs["values"]

        if option == 0:
            _neg, _ws, arg = values
            arg.get_last().set_negated(True)
            return arg
        elif option == 1:
            return values[0]
        else:
            raise "unexpected option for %s: %s with %s and %s", (target, option, names, values)


    def on_argument(self, *_args, **kwargs):
        """
        argument : saddr
                 | daddr
                 | sport
                 | sports
                 | dport
                 | dports
                 | proto
                 | sinf
                 | oinf
                 | module
                 | module_body
        """
        return kwargs["values"][0]


    def on_saddr(self, *_args, **kwargs):
        """
        saddr : SRC_SHORT WS IPV6_CIDR
              | SRC_LONG WS IPV6_CIDR
              | SRC_SHORT WS IPV4_CIDR
              | SRC_LONG WS IPV4_CIDR
        """
        values = kwargs["values"]

        _arg, _ws, val = values
        ret = Tree("-s")
        ret.add_child(val)
        return ret


    def on_daddr(self, *_args, **kwargs):
        """
        daddr : DST_SHORT WS IPV6_CIDR
              | DST_LONG WS IPV6_CIDR
              | DST_SHORT WS IPV4_CIDR
              | DST_LONG WS IPV4_CIDR
        """
        values = kwargs["values"]

        _arg, _ws, val = values
        ret = Tree("-d")
        ret.add_child(val)
        return ret


    def on_sport(self, *_args, **kwargs):
        """
        sport : SPORT WS PORTNO
        """
        values = kwargs["values"]

        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_dport(self, *_args, **kwargs):
        """
        dport : DPORT WS PORTNO
        """
        values = kwargs["values"]

        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_sports(self, *_args, **kwargs):
        """
        sports : SPORTS WS PORTRANGE
        """
        values = kwargs["values"]

        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_dports(self, *_args, **kwargs):
        """
        dports : DPORTS WS PORTRANGE
        """
        values = kwargs["values"]

        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_proto(self, *_args, **kwargs):
        """
        proto : PROTO_SHORT WS IDENT
              | PROTO_LONG WS IDENT
        """
        values = kwargs["values"]

        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_sinf(self, *_args, **kwargs):
        """
        sinf : IN_SHORT WS PORTNO
             | IN_LONG WS PORTNO
             | IN_SHORT WS IDENT
             | IN_LONG WS IDENT
        """
        values = kwargs["values"]

        _arg, _ws, val = values
        ret = Tree('-i')
        ret.add_child(val.lstrip('eth'))
        return ret


    def on_oinf(self, *_args, **kwargs):
        """
        oinf : OUT_SHORT WS PORTNO
             | OUT_LONG WS PORTNO
             | OUT_SHORT WS IDENT
             | OUT_LONG WS IDENT
        """
        values = kwargs["values"]

        _arg, _ws, val = values
        ret = Tree('-o')
        ret.add_child(val.lstrip('eth'))
        return ret


    def on_module(self, *_args, **kwargs):
        """
        module : MOD_SHORT WS IDENT
               | MOD_LONG WS IDENT
        """
        values = kwargs["values"]

        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_generic_argument(self, *_args, **kwargs):
        """
        generic_argument : ARG_SHORT WS IDENT
                         | ARG_LONG WS IDENT
        """
        values = kwargs["values"]

        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_module_body(self, *_args, **kwargs):
        """
        module_body : ARG_SHORT WS FLAGS WS FLAGS
                    | ARG_LONG WS FLAGS WS FLAGS
                    | ARG_SHORT WS WORD
                    | ARG_SHORT WS IDENT
                    | ARG_SHORT WS PORTNO
                    | ARG_SHORT WS IPV6_CIDR
                    | ARG_SHORT WS IPV4_CIDR
                    | ARG_SHORT WS STATES
                    | ARG_SHORT WS PORTRANGE
                    | ARG_LONG WS WORD
                    | ARG_LONG WS IDENT
                    | ARG_LONG WS PORTNO
                    | ARG_LONG WS IPV6_CIDR
                    | ARG_LONG WS IPV4_CIDR
                    | ARG_LONG WS STATES
                    | ARG_LONG WS PORTRANGE
        """
        values = kwargs["values"]

        if kwargs["option"] in [0, 1]:
            arg, _ws1, val1, _ws2, val2 = values
            val = "%s %s" % (val1, val2)
        else:
            arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_jump(self, *_args, **kwargs):
        """
        jump : JUMP_SHORT WS action
             | JUMP_LONG WS action
        """
        values = kwargs["values"]

        jump = Tree('-j')
        jump.add_child(values[2])
        return jump


    def on_action(self, *_args, **kwargs):
        """
        action : ACCEPT
               | DROP
               | RJCT WS generic_argument
        """
        norm = "DROP" if kwargs["option"] == 2 else kwargs["values"][0]
        return Tree(norm)


    _ipv6_seg = '[[:xdigit:]]{1,4}'
    _ipv6_cidr = r"(%s)(\/[1-9][[:digit:]]{0,2})?" % "|".join([
        "((%s:){7}%s)" % (_ipv6_seg, _ipv6_seg),
        "((%s:){1,7}:)" % _ipv6_seg,
        "((%s:){1,6}:%s)" % (_ipv6_seg, _ipv6_seg),
        "((%s:){1,5}(:%s){1,2})" % (_ipv6_seg, _ipv6_seg),
        "((%s:){1,4}(:%s){1,3})" % (_ipv6_seg, _ipv6_seg),
        "((%s:){1,3}(:%s){1,4})" % (_ipv6_seg, _ipv6_seg),
        "((%s:){1,2}(:%s){1,5})" % (_ipv6_seg, _ipv6_seg),
        "(%s:((:%s){1,2}))" % (_ipv6_seg, _ipv6_seg),
        "(:((:%s){1,7}|:))" % _ipv6_seg
    ])

    _port = '[1-9][[:digit:]]{0,4}'
    _portrange = r"%s:%s" % (_port, _port)

    _ipv4_seg = '[[:digit:]]{1,3}'
    _ipv4_cidr = r"%s(\.%s){3}(\/[[:digit:]]{1,2})?" % (_ipv4_seg, _ipv4_seg)

    _flag = '(SYN|ACK|FIN|RST|URG|PSH|ALL|NONE)'
    _flags = r"%s(,%s)*" % (_flag, _flag)

    _state = '(INVALID|NEW|ESTABLISHED|RELATED|UNTRACKED|SNAT|DNAT|NONE|EXPECTED|SEEN_REPLY|ASSURED|CONFIRMED)'
    _states = r"%s(,%s)*" % (_state, _state)

    _word = '[[:alnum:]_\-/]+'
    _wordlist = '%s(,%s)*' % (_word, _word)

#    """ + _wordlist + r"""  { returntoken(WORDLIST); }
    lexscript = r"""
    %{
    #include <stdio.h>
    #include <string.h>
    #include "Python.h"
    #define YYSTYPE void *
    #include "tokens.h"
    extern void *py_parser;
    extern void (*py_input)(PyObject *parser, char *buf, int *result, int max_size);
    #define returntoken(tok) yylval = PyString_FromString(strdup(yytext)); return (tok);
    #define YY_INPUT(buf,result,max_size) { (*py_input)(py_parser, buf, &result, max_size); }
    %}

    %%

    "ip6tables"             { returntoken(IPT6); }
    "iptables"              { returntoken(IPT); }
    "-P"                    { returntoken(POLICY_CMD); }
    "-A"                    { returntoken(APPEND_CMD); }
    "ACCEPT"                { returntoken(ACCEPT); }
    "DROP"                  { returntoken(DROP); }
    "REJECT"                { returntoken(RJCT); }
    "!"                     { returntoken(NEGATION); }
    "-t"                    { returntoken(TABLE); }
    "-j"                    { returntoken(JUMP_SHORT); }
    "--jump"                { returntoken(JUMP_LONG); }
    "-m"                    { returntoken(MOD_SHORT); }
    "--module"              { returntoken(MOD_LONG); }
    "-o"                    { returntoken(OUT_SHORT); }
    "--out-interface"       { returntoken(OUT_LONG); }
    "-i"                    { returntoken(IN_SHORT); }
    "--in-interface"        { returntoken(IN_LONG); }
    "--sport"               { returntoken(SPORT); }
    "--dport"               { returntoken(DPORT); }
    "--sports"              { returntoken(SPORTS); }
    "--dports"              { returntoken(DPORTS); }
    "-p"                    { returntoken(PROTO_SHORT); }
    "--proto"               { returntoken(PROTO_LONG); }
    "-s"                    { returntoken(SRC_SHORT); }
    "--source"              { returntoken(SRC_LONG); }
    "-d"                    { returntoken(DST_SHORT); }
    "--destination"         { returntoken(DST_LONG); }
    "-"[[:alpha:]]          { returntoken(ARG_SHORT); }
    "--"[[:alpha:]][[:alnum:]_\-]+ { returntoken(ARG_LONG); }
    """ + _port + r"""      { returntoken(PORTNO); }
    """ + _portrange + r""" { returntoken(PORTRANGE); }
    """ + _ipv6_cidr + r""" { returntoken(IPV6_CIDR); }
    """ + _ipv4_cidr + r""" { returntoken(IPV4_CIDR); }
    [\n]                    { yylineno++; returntoken(NEWLINE); }
    """ + _flags + r"""     { returntoken(FLAGS); }
    """ + _states + r"""    { returntoken(STATES); }
    [[:alpha:]][[:alnum:]_\-\.]*  { returntoken(IDENT); }
    [[:alnum:]_\-/]+        { returntoken(WORD); }
    [ \t]+                  { returntoken(WS); }
    "#"[[:print:]]*         { returntoken(COMMENT); }
    .                       { printf("unknown char %c ignored, yytext=%s\n", yytext[0], yytext); /* ignore bad chars */ }

    %%

    int yywrap() { return(1); }
    """


    def parse(self, ruleset):
        """ Retrieve an AST for an ip6tables rule set.

        Keyword arguments:
        ruleset - a file name containing an ip6tables rule set
        """

        self._ast = Tree('root')
        ast = self.run(file=str(ruleset))
        return ast


if __name__ == '__main__':
    ruleset = "bench/wl_up/rulesets/pgf.uni-potsdam.de-ruleset"
    if len(sys.argv) == 2: ruleset = sys.argv[1]

    IP6TablesParser().parse(ruleset).print_tree()
