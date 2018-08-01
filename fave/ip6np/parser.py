""" This module provides a parser for ip6tables rule sets.
"""

from antlr4 import InputStream, CommonTokenStream, ParseTreeWalker

from ip6tables_lexer import IP6TablesLexer
from ip6tables_parser import IP6TablesParser
from ip6tables_custom_listener import IP6TablesCustomListener


class ASTParser(object):
    """ This class offers a parser for ip6tables rule sets.
    """

    _ast = None

    @staticmethod
    def write_ast(ast_in):
        """ Persists an AST.

        Keyword arguments:
        ast_in -- an AST to be persisted
        """

        ASTParser._ast = ast_in

    @staticmethod
    def parse(ruleset):
        """ Parses an ip6tables rule set.

        Keyword arguments:
        ruleset -- an ip6tables rule set as string
        """

        lexer = IP6TablesLexer(InputStream(ruleset))
        tokens = CommonTokenStream(lexer)
        parser = IP6TablesParser(tokens)
        ctx = parser.entry()
        walker = ParseTreeWalker()
        listener = IP6TablesCustomListener()
        walker.walk(listener, ctx)

        return ASTParser._ast
