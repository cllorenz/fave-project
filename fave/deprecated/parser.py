# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

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
