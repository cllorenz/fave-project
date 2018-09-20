## TODOs

### FaVe

 - remove MISS duplicates from state tables -> expand() vectors in FaVe as well to make diff() work properly again
 - replace FirewallRule with SwitchRule
 - fix removal of firewall rules
 - automate in-/out-port mappings for firewalls
 - improve integration and system tests by checking log output
 - improve integration and system tests by using reachability tree analysis
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
 - bring NetPlumber to C++11 (or higher)
 - improve code readability
 - use -Wextra and -Wpedantic
 - libnetplumber? (C++ plus Python)
 - BDDs instead of Header Spaces?
