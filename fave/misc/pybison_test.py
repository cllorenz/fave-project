#!/usr/bin/env python2

""" This module provides a fast parser for ip6tables rule sets based on GNU Flex
    and Bison.
"""

from bison import BisonParser
from util.tree_util import Tree

class IP6TablesParser(BisonParser):
    """ This class provides a fast ip6tables parser.
    """

    bisonEngineLibName = "ip6tables-parser"
    interactive = False

    tokens = [
        'IPT', 'POLICY_CMD', 'APPEND_CMD', 'ACCEPT', 'DROP', 'TABLE',
        'JUMP_SHORT', 'JUMP_LONG', 'NEGATION', 'ARG_SHORT', 'ARG_LONG',
        'MOD_SHORT', 'MOD_LONG', 'OUT_SHORT', 'OUT_LONG', 'IN_SHORT', 'IN_LONG',
        'SPORT', 'DPORT', 'PROTO_SHORT', 'PROTO_LONG', 'SRC_SHORT', 'SRC_LONG',
        'DST_SHORT', 'DST_LONG', 'PORTNO', 'IPV6_CIDR', 'IDENT', 'WORD',
        'NEWLINE', 'WS'
    ]

    _ast = None
    precedences = ()

    start = 'ruleset'

    def on_ruleset(self, target, option, names, values):
        """
        ruleset :
                | ruleset line
        """

        if option == 0:
            return []
        elif option == 1:
            if values[1] is not None:
                self._ast.add_child(values[1])
            return self._ast
        else:
            raise "unexpected option for %s: %s with %s and %s", (target, option, names, values)


    def on_line(self, target, option, names, values):
        """
        line : NEWLINE
             | IPT WS table APPEND_CMD WS IDENT body WS jump NEWLINE
             | IPT WS table POLICY_CMD WS IDENT WS action NEWLINE
        """

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


    def on_table(self, target, option, names, values):
        """
        table :
              | TABLE WS IDENT WS
        """

        if option == 0:
            return None
        elif option == 1:
            arg, _ws, val, _ws = values
            ret = Tree(arg)
            ret.add_child(val)
            return ret
        else:
            raise "unexpected option for %s: %s with %s and %s", (target, option, names, values)


    def on_body(self, target, option, names, values):
        """
        body :
             | body WS neg_argument
        """

        if option == 0:
            return []
        elif option == 1:
            body = values[0]
            body.append(values[2])
            return body
        else:
            raise "unexpected option for %s: %s with %s and %s", (target, option, names, values)


    def on_neg_argument(self, target, option, names, values):
        """
        neg_argument : NEGATION WS argument
                     | argument
        """

        if option == 0:
            _neg, _ws, arg = values
            arg.get_last().set_negated(True)
            return arg
        elif option == 1:
            return values[0]
        else:
            raise "unexpected option for %s: %s with %s and %s", (target, option, names, values)


    def on_argument(self, _target, _option, _names, values):
        """
        argument : saddr
                 | daddr
                 | sport
                 | dport
                 | proto
                 | sinf
                 | oinf
                 | module
                 | module_body
        """
        return values[0]


    def on_saddr(self, _target, _option, _names, values):
        """
        saddr : SRC_SHORT WS IPV6_CIDR
              | SRC_LONG WS IPV6_CIDR
        """
        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_daddr(self, _target, _option, _names, values):
        """
        daddr : DST_SHORT WS IPV6_CIDR
              | DST_LONG WS IPV6_CIDR
        """
        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_sport(self, _target, _option, _names, values):
        """
        sport : SPORT WS PORTNO
        """
        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_dport(self, _target, _option, _names, values):
        """
        dport : DPORT WS PORTNO
        """
        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_proto(self, _target, _option, _names, values):
        """
        proto : PROTO_SHORT WS IDENT
              | PROTO_LONG WS IDENT
        """
        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_sinf(self, _target, _option, _names, values):
        """
        sinf : IN_SHORT WS PORTNO
             | IN_LONG WS PORTNO
             | IN_SHORT WS IDENT
             | IN_LONG WS IDENT
        """
        _arg, _ws, val = values
        ret = Tree('-i')
        ret.add_child(val)
        return ret


    def on_oinf(self, _target, _option, _names, values):
        """
        oinf : OUT_SHORT WS PORTNO
             | OUT_LONG WS PORTNO
             | OUT_SHORT WS IDENT
             | OUT_LONG WS IDENT
        """
        _arg, _ws, val = values
        ret = Tree('-o')
        ret.add_child(val)
        return ret


    def on_module(self, _target, _option, _names, values):
        """
        module : MOD_SHORT WS IDENT
               | MOD_LONG WS IDENT
        """
        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_module_body(self, _target, _option, _names, values):
        """
        module_body : ARG_SHORT WS WORD
                    | ARG_SHORT WS IDENT
                    | ARG_SHORT WS PORTNO
                    | ARG_SHORT WS IPV6_CIDR
                    | ARG_LONG WS WORD
                    | ARG_LONG WS IDENT
                    | ARG_LONG WS PORTNO
                    | ARG_LONG WS IPV6_CIDR
        """
        arg, _ws, val = values
        ret = Tree(arg)
        ret.add_child(val)
        return ret


    def on_jump(self, _target, _option, _names, values):
        """
        jump : JUMP_SHORT WS action
             | JUMP_LONG WS action
        """
        jump = Tree('-j')
        jump.add_child(values[2])
        return jump


    def on_action(self, _target, _option, _names, values):
        """
        action : ACCEPT
               | DROP
        """
        return Tree(values[0])


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

    "ip6tables"             { returntoken(IPT); }
    "-P"                    { returntoken(POLICY_CMD); }
    "-A"                    { returntoken(APPEND_CMD); }
    "ACCEPT"                { returntoken(ACCEPT); }
    "DROP"                  { returntoken(DROP); }
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
    "-p"                    { returntoken(PROTO_SHORT); }
    "--proto"               { returntoken(PROTO_LONG); }
    "-s"                    { returntoken(SRC_SHORT); }
    "--source"              { returntoken(SRC_LONG); }
    "-d"                    { returntoken(DST_SHORT); }
    "--destination"         { returntoken(DST_LONG); }
    "-"[[:alpha:]]          { returntoken(ARG_SHORT); }
    "--"[[:alpha:]][[:alnum:]_\-]+ { returntoken(ARG_LONG); }
    [1-9][[:digit:]]{0,4}   { returntoken(PORTNO); }
    """ + _ipv6_cidr + r""" { returntoken(IPV6_CIDR); }
    [\n]                    { yylineno++; returntoken(NEWLINE); }
    [[:alpha:]][[:alnum:]_\-]*  { returntoken(IDENT); }
    [[:alnum:]_\-/]+        { returntoken(WORD); }
    [ \t]+                  { returntoken(WS); }
    .                       { printf("unknown char %c ignored, yytext=0x%lx\n", yytext[0], yytext); /* ignore bad chars */ }

    %%

    yywrap() { return(1); }
    """


    def parse(self, ruleset):
        """ Retrieve an AST for an ip6tables rule set.

        Keyword arguments:
        ruleset - a file name containing an ip6tables rule set
        """

        self._ast = Tree('root')
        ast = self.run(file=ruleset)
        return ast


if __name__ == '__main__':
    IP6TablesParser().parse("bench/wl_ad6/rulesets/pgf-ruleset").print_tree()
