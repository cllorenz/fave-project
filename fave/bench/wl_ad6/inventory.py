#!/usr/bin/env python2

AD6 = (
    [
        ("file", "2001:db8:abc:0::1", ["tcp:21", "tcp:115", "tcp:22", "udp:22"]),
        ("mail", "2001:db8:abc:0::2", [
            "tcp:25", "tcp:587", "tcp:110", "tcp:143", "tcp:220", "tcp:465",
            "tcp:993", "tcp:995", "udp:143", "udp:220", "tcp:22", "udp:22"
        ]),
        ("web", "2001:db8:abc:0::3", ["tcp:80", "tcp:443", "tcp:22", "udp:22"]),
        ("ldap", "2001:db8:abc:0::4", [
            "tcp:389", "tcp:636", "udp:389", "udp:123", "tcp:22", "udp:22"
        ]),
        ("vpn", "2001:db8:abc:0::5", [
            "tcp:1194", "tcp:1723", "udp:1194", "udp:1723", "tcp:22", "udp:22"
        ]),
        ("dns", "2001:db8:abc:0::6", ["tcp:53", "udp:53", "tcp:22", "udp:22"]),
        ("data", "2001:db8:abc:0::7", [
            "tcp:118", "tcp:156", "tcp:22", "udp:118", "udp:156", "udp:22"
        ]),
        ("adm", "2001:db8:abc:0::8", ["udp:161", "tcp:22", "udp:22"])
    ],
    [
        "api",
        "asta",
        "botanischer-garten-potsdam.de",
#        "chem", # XXX: uncommenting leads to very enormously long rule insertions
#        "cs",
#        "geo",
#        "geographie",
#        "hgp-potsdam.de",
#        "hpi",
#        "hssport",
#        "intern",
#        "jura",
#        "ling",
#        "math",
#        "mmz-potsdam.de",
#        "physik",
#        "pogs",
#        "psych",
#        "sq-brandenburg.de",
#        "ub",
        "welcome-center-potsdam.de"
    ],
    [
        ("web", ["tcp:80", "tcp:443", "tcp:22", "udp:22"]),
        ("voip", ["tcp:5060", "tcp:5061", "udp:5060", "tcp:22", "udp:22"]),
        ("print", ["tcp:631", "tcp:22", "udp:631", "udp:22"]),
        ("mail", [
            "tcp:25", "tcp:587", "tcp:110", "tcp:143", "tcp:220", "tcp:465",
            "tcp:993", "tcp:995", "tcp:22", "udp:143", "udp:220", "udp:22"
        ]),
        ("file", [
            "tcp:137", "tcp:138", "tcp:139", "tcp:445", "tcp:2049", "tcp:22",
            "udp:137", "udp:138", "udp:139", "udp:22"
        ])
    ]
)
