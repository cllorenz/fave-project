#!/usr/bin/env python2

import sys
import re

IPV4_REGEX=r"(\d{1,3}\.){3}\d{1,3}(\/\d{1,2})?"

def _convert_ipv4_to_ipv6(address):
    tokens = address.split('/')
    prefix = 32
    if len(tokens) == 1:
        address = tokens[0]
    else:
        address, prefix = tokens
        prefix = int(prefix)


    bytes = address.split('.')
    address_int = 0
    for idx, byte in enumerate(bytes):
        address_int += (int(byte) << (3-idx)*8)

    return "64:ff9b::%s/%s" % ("%04x:%04x" % (
        (address_int & 0xffff0000) >> 16,
        address_int & 0xffff), prefix + 96
    )


def _print_help():
    print "usage: python2 %s <in-file> <out-file>" % sys.argv[0]


if __name__ == '__main__':
    if len(sys.argv) != 3:
        _print_help()
        sys.exit(1)

    in_file = sys.argv[1]
    out_file = sys.argv[2]

    result = []

    with open(in_file, 'r') as f:
        for line in f.readlines():
            res_line = line.rstrip().replace('iptables', 'ip6tables')

            tokens = res_line.split(' ')
            for token in tokens:
                match = re.match(IPV4_REGEX, token)
                if match:
                    if token == '0.0.0.0/0':
                        res_line = res_line.replace('0.0.0.0/0' '0::0/0')
                    else:
                        res_line = res_line.replace(token, _convert_ipv4_to_ipv6(token))

            result.append(res_line)

    with open(out_file, 'w') as f:
        f.write('\n'.join(result)+'\n')
