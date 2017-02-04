# Generated from ../ip6tables.g4 by ANTLR 4.5.3
from antlr4 import *
from tree import Tree
import parser

# This class defines a complete listener for a parse tree produced by ip6tablesParser.
class IP6TablesListener(ParseTreeListener):
    _ast = None

    # Enter a parse tree produced by ip6tablesParser#entry.
    def enterEntry(self, ctx):
        self._ast = Tree("root")

    # Exit a parse tree produced by ip6tablesParser#entry.
    def exitEntry(self, ctx):
        parser.ASTParser.writeAST(self._ast)


    # Enter a parse tree produced by ip6tablesParser#ip6tables.
    def enterIp6tables(self, ctx):
        self._ast = self._ast.add_child(ctx.getText())
        self._ast.add_child("-t").add_child("filter")

    # Exit a parse tree produced by ip6tablesParser#ip6tables.
    def exitIp6tables(self, ctx):
        self._ast = self._ast.parent


    # Enter a parse tree produced by ip6tablesParser#command_t.
    def enterCommand_t(self, ctx):
        self._ast = self._ast.get_child("-t")

    # Exit a parse tree produced by ip6tablesParser#command_t.
    def exitCommand_t(self, ctx):
        self._ast = self._ast.parent


    # Enter a parse tree produced by ip6tablesParser#command.
    def enterCommand(self, ctx):
        pass

    # Exit a parse tree produced by ip6tablesParser#command.
    def exitCommand(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_A.
    def enterCommand_A(self, ctx):
        self._ast.add_child("-A")

    # Exit a parse tree produced by ip6tablesParser#command_A.
    def exitCommand_A(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_D.
    def enterCommand_D(self, ctx):
        self._ast.add_child("-D")

    # Exit a parse tree produced by ip6tablesParser#command_D.
    def exitCommand_D(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_C.
    def enterCommand_C(self, ctx):
        self._ast.add_child("-C")

    # Exit a parse tree produced by ip6tablesParser#command_C.
    def exitCommand_C(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_I.
    def enterCommand_I(self, ctx):
        self._ast.add_child("-I")

    # Exit a parse tree produced by ip6tablesParser#command_I.
    def exitCommand_I(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_R.
    def enterCommand_R(self, ctx):
        self._ast.add_child("-R")

    # Exit a parse tree produced by ip6tablesParser#command_R.
    def exitCommand_R(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_S.
    def enterCommand_S(self, ctx):
        self._ast = self._ast.add_child("-S")

    # Exit a parse tree produced by ip6tablesParser#command_S.
    def exitCommand_S(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_L.
    def enterCommand_L(self, ctx):
        self._ast.add_child("-L")

    # Exit a parse tree produced by ip6tablesParser#command_L.
    def exitCommand_L(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_F.
    def enterCommand_F(self, ctx):
        self._ast.add_child("-F")

    # Exit a parse tree produced by ip6tablesParser#command_F.
    def exitCommand_F(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_Z.
    def enterCommand_Z(self, ctx):
        self._ast.add_child("-Z")

    # Exit a parse tree produced by ip6tablesParser#command_Z.
    def exitCommand_Z(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_N.
    def enterCommand_N(self, ctx):
        self._ast.add_child("-N")

    # Exit a parse tree produced by ip6tablesParser#command_N.
    def exitCommand_N(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_X.
    def enterCommand_X(self, ctx):
        self._ast.add_child("-X")

    # Exit a parse tree produced by ip6tablesParser#command_X.
    def exitCommand_X(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_P.
    def enterCommand_P(self, ctx):
        self._ast.add_child("-P")

    # Exit a parse tree produced by ip6tablesParser#command_P.
    def exitCommand_P(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#command_E.
    def enterCommand_E(self, ctx):
        self._ast.add_child("-E")

    # Exit a parse tree produced by ip6tablesParser#command_E.
    def exitCommand_E(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#target.
    def enterTarget(self, ctx):
        self._ast.get_last().add_child(ctx.getText())

    # Exit a parse tree produced by ip6tablesParser#target.
    def exitTarget(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#table.
    def enterTable(self, ctx):
        self._ast[0] = Tree(value=ctx.getText())

    # Exit a parse tree produced by ip6tablesParser#table.
    def exitTable(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#chain.
    def enterChain(self, ctx):
#        self._ast.print_tree()
        self._ast.get_last().add_child(ctx.getText())

    # Exit a parse tree produced by ip6tablesParser#chain.
    def exitChain(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#rulenum.
    def enterRulenum(self, ctx):
        self._ast.get_last().add_child(ctx.getText())

    # Exit a parse tree produced by ip6tablesParser#rulenum.
    def exitRulenum(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#rule_spec.
    def enterRule_spec(self, ctx):
        pass

    # Exit a parse tree produced by ip6tablesParser#rule_spec.
    def exitRule_spec(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#junk.
    def enterJunk(self, ctx):
        pass

    # Exit a parse tree produced by ip6tablesParser#junk.
    def exitJunk(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#argtype.
    def enterArgtype(self, ctx):
        self._ast = self._ast.add_child(ctx.getText().replace("! ",""))

    # Exit a parse tree produced by ip6tablesParser#argtype.
    def exitArgtype(self, ctx):
        self._ast = self._ast.parent


    # Enter a parse tree produced by ip6tablesParser#arg.
    def enterArg(self, ctx):
        self._ast.get_last().add_child(ctx.getText())

    # Exit a parse tree produced by ip6tablesParser#arg.
    def exitArg(self, ctx):
        pass


    # Enter a parse tree produced by ip6tablesParser#negation.
    def enterNegation(self, ctx):
        self._ast.set_negated(True)

    # Exit a parse tree produced by ip6tablesParser#negation.
    def exitNegation(self, ctx):
        pass


