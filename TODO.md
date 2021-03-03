## TODOs

### Benchmarks

 - IFI:
    - generate all flow in subnets instead of subnet specific traffic
    - add hosts as packet filters (optional)
 - UP:
    - fix usage of bdd packet sets by either implementing flow tree checks in NetPlumber or fixing dumping of packet sets
 - Internet2: fix benchmark
 - Stanford: fix benchmark

### Policy Translator

 - introduce waypoint policies: `RoleA <-[RoleB]->> RoleC` where ''RoleA may reach RoleC statefully while traversing RoleB.''
 - improve inventory brevity:
    - abstract roles which can be used by roles and super roles but do not instantiate, e.g., generic server offering `ssh`
    - host name prefixes in subroles which can be applied to host names specified in super roles, e.g., prefixes `www.` and `mail.` in subroles and `uni-potsdam.de` in superclass lead to `www.uni-potsdam.de` and `mail.uni-potsdam.de` respectively when the classes are instantiated.
 - generate virtual network reachability matrix

### FaVe

 - fix removal of firewall rules
 - improve integration and system tests by checking log output
 - improve reachability tree analysis by using more generic flow specifications
 - improve reachability tree analysis by implementing a better subset of CTL
 - improve test coverage
 - Upgrade code to Python3
 - libnetplumber
    - replace rpc calls with library calls

### NetPlumber

 - enable output ports to be used in flowexp expressions
 - Fix Rule Reachability and Shadowing detection which slows down rule insertion
in large tables tremendously
 - improve test coverage
 - bring NetPlumber to C++11 (or higher) to improve readability:
    - use lambdas where suitable
 - improve code readability
 - libnetplumber (C++ plus Python)
    - wrapper around net_plumber.cc
    - native json data format instead of json string parsing
 - BDDs instead of Header Spaces
    - `[DONE]` generic interface for set representations and operations
    - implement and test bdd based packet set class
    - benchmarks:
      - [DONE] IFI
      - [ ] UP
 - Unify the empty set for arrays by a NULL representation, i.e., whenever a
'z' is found remove the array. Pros: makes checks for the empty set more
efficient and the memory footprint might be lowered. Cons: might break stuff at
funny places... which leads to the question: why is that code even there?
 - Replace strange hs representation by simpler $A - A_d$ data structure
    - pass unit tests
    - meaningful debug output for unit tests
    - pass integration tests
    - pass benchmarks
    - optimization: in-situ (less copying)
    - optimization: cosequent reduction to NULL
    - optimization: function inlining
    - optimization: cover trivial cases
 - documentation
   - abstract (and static) doc
   - generated low level docs from code

### AP-Verifyer

 - better integration with IFI benchmark
 - better reporting: check reachability trees against policy-matrix

### AD6

 - read topology and config from benchmark input files
 - use reachability matrix
 - better reporting
