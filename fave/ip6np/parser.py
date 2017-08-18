from antlr4 import *
from ip6tables_lexer import IP6TablesLexer
from ip6tables_parser import IP6TablesParser
from ip6tables_custom_listener import IP6TablesCustomListener

#import time

class ASTParser(object):
    _ast = None

    @staticmethod
    def writeAST(ast_in):
        ASTParser._ast = ast_in

    @staticmethod
    def parse(ruleset):
#        t = [time.time()]
        lexer = IP6TablesLexer(InputStream(ruleset))
#        t.append(time.time())
        tokens = CommonTokenStream(lexer)
#        t.append(time.time())
        parser = IP6TablesParser(tokens)
#        t.append(time.time())
        ctx = parser.entry()
#        t.append(time.time())
        walker = ParseTreeWalker()
#        t.append(time.time())
        listener = IP6TablesCustomListener()
#        t.append(time.time())
        walker.walk(listener, ctx)
#        t.append(time.time())
#        print "lexer: %s\ntokens: %s\nparser: %s\nctx: %s\nwalker: %s\nlistener: %s\nwalk: %s" % tuple([str(x-t[i]) for i,x in enumerate(t[1:])])
        return ASTParser._ast
