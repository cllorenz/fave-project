from antlr4 import *
from parser import ASTParser
import time

def main():
    #ifile = "./iptables_ruleset_reduced.sh"
    ifile = "../pgf-ruleset"

    t1 = time.time()
    with open(ifile,'r') as f:
        ruleset = f.read()

    t2 = time.time()

    if ruleset:
        ast = ASTParser.parse(ruleset)

        t3 = time.time()


        td1 = t2-t1
        td2 = t3-t2
        res = td1+td2

        #print(json.dumps(json.loads(model),indent=2,sort_keys=True))
        print("file reading: %s\nparsing: %s\ntotal: %s" % (str(td1),str(td2),str(res)))


if __name__ == '__main__':
    main()
