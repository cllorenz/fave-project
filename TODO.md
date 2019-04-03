## TODOs

### FaVe

 - fix removal of firewall rules
 - automate in-/out-port mappings for firewalls and routers
 - improve integration and system tests by checking log output
 - improve reachibility tree analysis featuring stateful connections
 - improve reachability tree analysis by using more generic flow specifications
 - improve reachability tree analysis by implementing a better subset of CTL
 - improve test coverage
 - create benchmark with IFI network
    - define inventory
    - define topology
    - build network from inventory and topology
 - create benchmark with TUM-i8 network
 - create benchmark with Stanford network
 - create benchmark with Internet2 network
    - include by using FaVe instead of a direct read
 - replace slow ip6tables parser
 - Gitlab-CI
 - integrate policy translator
 - use asynchronous rpc calls to improve performance
    - introduce counter for FaVe events
    - save mapping generations marked by event counters
    - extend dumping with mapping generations
    - enhance rpc calls with event counter as identifyer
    - use rpc calls asynchonously
    - support asynchronous handling of rpc return values


### NetPlumber

 - fix memory leak in Pipeline setup (shows up in the NetPlumber destructor)
 - improve test coverage
 - bring NetPlumber to C++11 (or higher) to improve readability:
    - use lambdas where suitable
 - improve code readability
 - use -Wextra and -Wpedantic
 - integrate test coverage tools: gcov
 - libnetplumber? (C++ plus Python)
 - BDDs instead of Header Spaces?
 - Unify the empty set for arrays by a NULL representation, i.e., whenever a
'z' is found remove the array. Pros: makes checks for the empty set more
efficient and the memory footprint might be lowered. Cons: might break stuff at
funny places... which leads to the question: why is that code even there?
 - support asynchronous rpc calls
    - extend callbacks with rpc identifyer
    - extend logs with rpc identifyer
