#!/usr/bin/env python2

UP = {
    'pgf' : [("pgf.uni-potsdam.de", "2001:db8:abc::1", ["tcp:22", "udp:22"])],
    'dmz' : [
        ("file.uni-potsdam.de", "2001:db8:abc:1::1", ["tcp:21", "tcp:115", "tcp:22", "udp:22"]),
        ("mail.uni-potsdam.de", "2001:db8:abc:1::2", [
            "tcp:25", "tcp:587", "tcp:110", "tcp:143", "tcp:220", "tcp:465",
            "tcp:993", "tcp:995", "udp:143", "udp:220", "tcp:22", "udp:22"
        ]),
        ("web.uni-potsdam.de", "2001:db8:abc:1::3", ["tcp:80", "tcp:443", "tcp:22", "udp:22"]),
        ("ldap.uni-potsdam.de", "2001:db8:abc:1::4", [
            "tcp:389", "tcp:636", "udp:389", "udp:123", "tcp:22", "udp:22"
        ]),
        ("vpn.uni-potsdam.de", "2001:db8:abc:1::5", [
            "tcp:1194", "tcp:1723", "udp:1194", "udp:1723", "tcp:22", "udp:22"
        ]),
        ("dns.uni-potsdam.de", "2001:db8:abc:1::6", ["tcp:53", "udp:53", "tcp:22", "udp:22"]),
        ("data.uni-potsdam.de", "2001:db8:abc:1::7", [
            "tcp:118", "tcp:156", "tcp:22", "udp:118", "udp:156", "udp:22"
        ]),
        ("adm.uni-potsdam.de", "2001:db8:abc:1::8", ["udp:161", "tcp:22", "udp:22"])
    ],
    "wifi" : [("clients.wifi.uni-potsdam.de", "2001:db8:abc:2::100/120", [])],
    "subnets" : [
        "api.uni-potsdam.de",
        "asta.uni-potsdam.de",
        "botanischer-garten-potsdam.de",
        "chem.uni-potsdam.de",
        "cs.uni-potsdam.de",
        "geo.uni-potsdam.de",
        "geographie.uni-potsdam.de",
        "hgp-potsdam.de",
        "hpi.uni-potsdam.de",
        "hssport.uni-potsdam.de",
        "intern.uni-potsdam.de",
        "jura.uni-potsdam.de",
        "ling.uni-potsdam.de",
        "math.uni-potsdam.de",
        "mmz-potsdam.de",
        "physik.uni-potsdam.de",
        "pogs.uni-potsdam.de",
        "psych.uni-potsdam.de",
        "sq-brandenburg.de",
        "ub.uni-potsdam.de",
        "welcome-center-potsdam.de"
    ],
    "subhosts" : [
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
}
