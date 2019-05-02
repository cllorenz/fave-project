#!/usr/bin/env python2

from bison import BisonParser, BisonNode
import pyparsing as pp

class IP6TablesParser(BisonParser):
    bisonEngineLibName = "ip6tables-parser"
    interactive = False

    tokens = ['IPT', 'POLICY_CMD', 'APPEND_CMD', 'ACCEPT', 'DROP', 'JUMP_SHORT', 'JUMP_LONG', 'NEGATION', 'ARG_SHORT', 'ARG_LONG', 'MOD_SHORT', 'MOD_LONG', 'OUT_SHORT', 'OUT_LONG', 'IN_SHORT', 'IN_LONG', 'SPORT', 'DPORT', 'PROTO_SHORT', 'PROTO_LONG', 'SRC_SHORT', 'SRC_LONG', 'DST_SHORT', 'DST_LONG', 'PORTNO', 'IPV6_CIDR', 'IDENT', 'WORD', 'NEWLINE', 'WS']

    precedences = ()

    start = 'ruleset'

    def on_ruleset(self, **kw):
        """
        ruleset :
                | ruleset line
        """
        return


    def on_line(self, **kw):
        """
        line : NEWLINE
             | IPT WS APPEND_CMD WS IDENT body WS jump WS action NEWLINE
             | IPT WS POLICY_CMD WS IDENT WS action NEWLINE
        """
        return


    def on_body(self, **kw):
        """
        body :
             | body neg_argument
        """
        return


    def on_neg_argument(self, **kw):
        """
        neg_argument : WS NEGATION WS argument
                     | WS argument
        """
        return


    def on_argument(self, **kw):
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
        return


    def on_saddr(self, **kw):
        """
        saddr : SRC_SHORT WS IPV6_CIDR
              | SRC_LONG WS IPV6_CIDR
        """
        return


    def on_daddr(self, **kw):
        """
        daddr : DST_SHORT WS IPV6_CIDR
              | DST_LONG WS IPV6_CIDR
        """
        return


    def on_sport(self, **kw):
        """
        sport : SPORT WS PORTNO
        """
        return


    def on_dport(self, **kw):
        """
        dport : DPORT WS PORTNO
        """
        return


    def on_proto(self, **kw):
        """
        proto : PROTO_SHORT WS IDENT
              | PROTO_LONG WS IDENT
        """
        return


    def on_sinf(self, **kw):
        """
        sinf : IN_SHORT WS interface
             | IN_LONG WS interface
        """
        return


    def on_oinf(self, **kw):
        """
        oinf : OUT_SHORT WS interface
             | OUT_LONG WS interface
        """
        return


    def on_interface(self, **kw):
        """
        interface : PORTNO
                  | IDENT
        """
        return


    def on_module(self, **kw):
        """
        module : MOD_SHORT WS IDENT
               | MOD_LONG WS IDENT
        """
        return


    def on_module_body(self, **kw):
        """
        module_body : ARG_SHORT WS WORD
                    | ARG_SHORT WS IDENT
                    | ARG_SHORT WS PORTNO
                    | ARG_LONG WS WORD
                    | ARG_LONG WS IDENT
                    | ARG_LONG WS PORTNO
        """
        return


    def on_jump(self, **kw):
        """
        jump : JUMP_SHORT
             | JUMP_LONG
        """
        return


    def on_action(self, **kw):
        """
        action : ACCEPT
               | DROP
        """
        return


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


if __name__ == '__main__':
    import time
    t1 = time.time()
    p = IP6TablesParser(verbose=0)
    t2 = time.time()
    ret = p.run(file="bench/wl_ad6/rulesets/pgf-ruleset", debug=0)
    t3 = time.time()
    print(ret)

    print("create parser: %s, parse file: %s" % (t2-t1, t3-t2))
