## TODOs

### General

 - Update [README](README.md)

### Benchmarks

 - IFI:
    - generate all flow in subnets instead of subnet specific traffic
    - add hosts as packet filters (optional)
 - UP:
    - fix usage of bdd packet sets by either implementing flow tree checks in NetPlumber or fixing dumping of packet sets

### Policy Translator

 - introduce waypoint policies: `RoleA <-[RoleB]->> RoleC` where ''RoleA may reach RoleC statefully while traversing RoleB.''
 - introduce crypto policies: `RoleA <-&->> RoleB.ServiceC` where ''RoleA may reach RoleB statefully through an encrypted connection''. A service specification implies the usage of (D)TLS. If no service is specified IPSec is used instead.
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
 - improve test coverage
 - bring NetPlumber to C++11 (or higher) to improve readability:
    - use lambdas where suitable
 - improve code readability
 - libnetplumber (C++ plus Python)
    - wrapper around net_plumber.cc
    - native Python data format instead of json string parsing
 - BDDs instead of Header Spaces
    - `[DONE]` generic interface for set representations and operations
    - implement and test bdd based packet set class
    - benchmarks:
      - [DONE] IFI
      - [ ] UP
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

### AD6

 - read topology and config from benchmark input files
 - use reachability matrix
 - better reporting
