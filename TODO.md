## TODOs

### FaVe

 - fix removal of firewall rules
 - automate in-/out-port mappings for firewalls
 - improve integration and system tests by checking log output
 - fix reachability tree analysis of ad6 by introducing client dummies
 - improve reachability tree analysis by using more generic flow specifications
 - improve reachability tree analysis by implementing a better subset of CTL
 - improve test coverage
 - create benchmark with IFI network
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
