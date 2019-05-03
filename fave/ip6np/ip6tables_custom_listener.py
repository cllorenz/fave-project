""" This module provides a parse tree listener which constructs an AST from an
    ip6tables rule set token stream.
"""

import parser

from ip6tables_listener import IP6TablesListener
from util.tree_util import Tree

class IP6TablesCustomListener(IP6TablesListener):
    """ This class implements a parse tree listener for ip6tables rule set token
        streams.
    """

    _ast = None
    _negated = False

    # entry :         (SPACE? ip6tables? NL)+ EOF;
    def enterEntry(self, ctx):
        self._ast = Tree("root")

    def exitEntry(self, ctx):
        parser.ASTParser.write_ast(self._ast)

    # ip6tables :     IP6TABLES (SPACE command_t)? SPACE command;
    def enterIp6tables(self, ctx):
        self._ast = self._ast.add_child(ctx.getText())

    def exitIp6tables(self, ctx):
        if not self._ast.get_child("-t"):
            self._ast.add_child("-t").add_child("filter")
        self._ast = self._ast.parent

    # command_t :     ARGTYPE_t SPACE table;
    def enterCommand_t(self, ctx):
        self._ast = self._ast.add_child("-t")

    def exitCommand_t(self, ctx):
        self._ast = self._ast.parent

    # command_A :     ARGTYPE_A SPACE identifier SPACE rule_spec;
    def enterCommand_A(self, ctx):
        self._ast = self._ast.add_child("-A")

    # command_P :     ARGTYPE_P SPACE identifier SPACE target;
    def enterCommand_P(self, ctx):
        self._ast = self._ast.add_child("-P")

    def exitCommand_P(self, ctx):
        self._ast = self._ast.parent

    def enterJump(self, ctx):
        self._ast.add_child("-j")

    def exitJump(self, ctx):
        self._ast = self._ast.parent

    def enterTarget(self, ctx):
        self._ast.get_last().add_child(ctx.getText())

    def enterTable(self, ctx):
        self._ast.add_child(ctx.getText())

    def enterChain(self, ctx):
        self._ast.get_last().add_child(ctx.getText())

    def enterIdentifier(self, ctx):
        self._ast.add_child(ctx.getText())

    def enterValue(self, ctx):
        val = self._ast.get_last().add_child(ctx.getText())
        if self._negated:
            val.set_negated(True)
            self._negated = False

    # arg :           negation? DASH (DASH)? identifier SPACE value;
    def enterNegation(self, ctx):
        self._negated = True
