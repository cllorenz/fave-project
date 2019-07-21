IfI workload with a central router and several subnets distinguished by VLANs.

Files:

``acls.txt`` - IfI's ACLs deployed on the central router.
``benchmark.py`` - Script to execute the IfI benchmark.
``checkgen.py`` - DEPRECATED by ``reach_csv_to_check.py`` - Generates ``checks.json`` for static post execution examination which includes allowed and disallowed reachability in the network.
``ifi.csv`` - IfI's subnets as CSV.
``inventory.py`` - Includes subnets with and without IP prefixes.
``inventorygen.py`` - Generates ``inventory.json`` which includes a list of all domains as well as a mapping between VLANs and domains.
``np.conf`` - The NetPlumber logging configuration file.
``pass_acls.txt`` - Dummy ACL that allows all traffic. For testing purposes only.
``policygen.py`` - Generates ``policies.json`` which includes all probes to be deployed in NetPlumber to cover the reachability policy.
``reach_csv_to_check.py`` - Generates ``checks.json`` for post execution examination which includes all allowed and disallowed reachabilities in the network.
``routegen.py`` - Generates ``routes.json`` which includes all routes deployed on the central router.
``topogen.py`` - Generates ``topology.json`` which includes devices and links with domain prefixes as identifiers as well as VLANs for the traffic generators.
``vlan_to_dn.json`` - Includes a mapping between VLANs and the subnets' domain names.

