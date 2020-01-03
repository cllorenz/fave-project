## TODOs

### Benchmarks

 - IFI:
    - generate all flow in subnets instead of subnet specific traffic
    - add hosts as packet filters (optional)
 - AD6:
    - include policy translator
    - check state table traversal
 - Internet2:
    - create benchmark from originial config instead of TF format
    - construct by using FaVe instead of a direct read
 - Stanford: create benchmark from original configuration
 - TUM-i8: create benchmark

### Policy Translator

 - introduce waypoint policies
 - generate virtual network reachability matrix

### FaVe

 - fix removal of firewall rules
 - automate in-/out-port mappings for firewalls and routers
 - improve integration and system tests by checking log output
 - improve reachibility tree analysis featuring stateful connections
 - improve reachability tree analysis by using more generic flow specifications
 - improve reachability tree analysis by implementing a better subset of CTL
 - improve test coverage
 - Gitlab-CI
 - use asynchronous rpc calls to improve performance? -> complex, better use libnetplumber instead?
    - introduce counter for FaVe events
    - save mapping generations marked by event counters
    - extend dumping with mapping generations
    - enhance rpc calls with event counter as identifyer
    - use rpc calls asynchonously
    - support asynchronous handling of rpc return values
 - Upgrade code to Python3
 - libnetplumber
    - replace rpc calls with library calls

### NetPlumber

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
    - [DONE] generic interface for set representations and operations
    - implement and test bdd based packet set class
    - benchmarks: IFI, UP
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
 - support asynchronous rpc calls? -> complex, better use libnetplumber instead?
    - extend callbacks with rpc identifyer
    - extend logs with rpc identifyer

### AP-Verifyer

 - better integration with IFI benchmark
 - better reporting: check reachability trees against policy-matrix

### AD6

 - read topology and config from benchmark input files
 - use reachability matrix
 - better reporting
