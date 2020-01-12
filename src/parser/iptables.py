from src.xml.genutils import GenUtils


class IP6TablesMixin:
    # functions to use in iptables adapters
    def ip(ast):
        return GenUtils.ip(ast.addr)


class IP6TablesAdapter:
    mapping = {
               "ip" : IP6TablesMixin.ip
    }

    def _TraverseAST(ast):
        try:
            # handle known
            subtree = IP6TablesAdapter.mapping[ast.label](ast)
            subtree.extend(map(IPTablesAdapter._TraverseAST,list(ast)))
            return subtree
        except KeyError:
            # try subast
            return map(IP6TablesAdapter._TraverseAST,list(ast))


    def ParsePolicy(policy):
        file = open(policy)
        filestr = file.readFile()
        file.close()
        ast = IP6TablesParser.parse(filestr)
        return IP6TablesAdapter._TraverseAST(ast)
