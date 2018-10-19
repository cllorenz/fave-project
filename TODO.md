## TODOs

### FaVe

 - fix removal of firewall rules
 - automate in-/out-port mappings for firewalls and routers
 - improve integration and system tests by checking log output
 - fix infinite loop in netplumber seen with ad6
 - improve reachibility tree analysis featuring stateful connections
 - improve reachability tree analysis by using more generic flow specifications
 - improve reachability tree analysis by implementing a better subset of CTL
 - improve test coverage
 - create benchmark with IFI network
    - integrate router model into aggregator
    - define inventory
    - define topology
    - build network from inventory and topology
 - create benchmark with TUM-i8 network
 - create benchmark with Stanford network
 - create benchmark with Internet2 network
 - replace slow ip6tables parser
 - Gitlab-CI
 - integrate policy translator


### NetPlumber

 - fix memory leak in Pipeline setup (shows up in the NetPlumber destructor)
 - improve test coverage
 - bring NetPlumber to C++11 (or higher) to improve readability:
    - deduce iterator types using auto
    - use range based iteration where suitable
    - replace NULL by nullptr where suitable
    - use lambdas where suitable
 - improve code readability
 - use -Wextra and -Wpedantic
 - integrate test coverage tools: gcov
 - libnetplumber? (C++ plus Python)
 - BDDs instead of Header Spaces?
 - Remove or fix experiments: FirewallRuleNode, PolicyProbe
