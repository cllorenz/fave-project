$ topology_gen.py --nodes-per-datacenter=200 --router-replication=2 --ports-per-router=32 --ports-per-leaf-router=32 --random-seed=346376325

Datacenter tree height: 1
Public services IP: 121.140.254.0
Public TCP port: 331
Number of hosts per leaf router: 30
Number of leaf routers: 8
Number of bits of leaf IPs: 7
Number of bits per datacenter: 10
Router branching: 8

Services per Datacenter:
Datacenter 0: #8 [5, 11, 15, 17, 19, 20, 23, 24]
Datacenter 1: #1 [1]
Datacenter 2: #4 [8, 12, 18, 21]
Datacenter 3: #4 [4, 5, 9, 13]
Datacenter 4: #16 [0, 1, 2, 3, 6, 7, 10, 11, 14, 16, 17, 20, 21, 22, 23, 24]

Services' IPs:
Service 0: #1 10.0.17.128/25
Service 1: #2 10.0.4.0/22, 10.0.18.0/25
Service 2: #1 10.0.17.0/25
Service 3: #1 10.0.17.0/25
Service 4: #1 10.0.14.0/23
Service 5: #2 10.0.1.0/24, 10.0.14.0/23
Service 6: #1 10.0.18.0/25
Service 7: #1 10.0.19.128/25
Service 8: #1 10.0.10.0/24
Service 9: #1 10.0.12.0/23
Service 10: #1 10.0.16.128/25
Service 11: #2 10.0.0.0/24, 10.0.16.0/25
Service 12: #1 10.0.11.0/24
Service 13: #1 10.0.12.0/23
Service 14: #1 10.0.18.128/25
Service 15: #1 10.0.3.0/24
Service 16: #1 10.0.16.0/25
Service 17: #2 10.0.3.0/24, 10.0.19.0/25
Service 18: #1 10.0.8.0/24
Service 19: #1 10.0.0.0/24
Service 20: #2 10.0.2.0/24, 10.0.17.128/25
Service 21: #2 10.0.9.0/24, 10.0.18.128/25
Service 22: #1 10.0.19.128/25
Service 23: #2 10.0.2.0/24, 10.0.19.0/25
Service 24: #2 10.0.1.0/24, 10.0.16.128/25

ACL Matrix:
0: 00100000001000000011010011
1: 00010011000010000011010001
2: 10000010101111010000001100
3: 01000111110010000000001010
4: 00000010000001101000010000
5: 00010011000100000011000000
6: 01111100100001010001000100
7: 01010100100000000101000010
8: 00110011000010001010110011
9: 00010000001101011000000010
10: 10100000010110100100100001
11: 00100100011011100110001011
12: 01110000101101000011000010
13: 00101010010110011000011011
14: 00001000001100011101110001
15: 00100010010001100010110100
16: 00001000110001100100000000
17: 00000001001100101000010010
18: 11000100100110010000000111
19: 11000111000010100000000001
20: 00000000101000110000001100
21: 11001000100001110100000100
22: 00110000000101000000100011
23: 00100010000000010010110011
24: 10010001110111000110001100
25: 11000000101101100011001100

Datacenter 0: 10.0.0.0 (port 1000000)
Services of router 1000001: set([19, 11])
Services of router 1000063: set([19, 11])
Services of router 1000125: set([24, 5])
Services of router 1000187: set([24, 5])
Services of router 1000249: set([20, 23])
Services of router 1000311: set([20, 23])
Services of router 1000373: set([17, 15])
Services of router 1000435: set([17, 15])
Datacenter 1: 10.0.4.0 (port 1100000)
Services of router 1100001: set([1])
Services of router 1100063: set([1])
Services of router 1100125: set([1])
Services of router 1100187: set([1])
Services of router 1100249: set([1])
Services of router 1100311: set([1])
Services of router 1100373: set([1])
Services of router 1100435: set([1])
Datacenter 2: 10.0.8.0 (port 1200000)
Services of router 1200001: set([18])
Services of router 1200063: set([18])
Services of router 1200125: set([21])
Services of router 1200187: set([21])
Services of router 1200249: set([8])
Services of router 1200311: set([8])
Services of router 1200373: set([12])
Services of router 1200435: set([12])
Datacenter 3: 10.0.12.0 (port 1300000)
Services of router 1300001: set([9, 13])
Services of router 1300063: set([9, 13])
Services of router 1300125: set([9, 13])
Services of router 1300187: set([9, 13])
Services of router 1300249: set([4, 5])
Services of router 1300311: set([4, 5])
Services of router 1300373: set([4, 5])
Services of router 1300435: set([4, 5])
Datacenter 4: 10.0.16.0 (port 1400000)
Services of router 1400001: set([16, 11])
Services of router 1400063: set([24, 10])
Services of router 1400125: set([2, 3])
Services of router 1400187: set([0, 20])
Services of router 1400249: set([1, 6])
Services of router 1400311: set([21, 14])
Services of router 1400373: set([17, 23])
Services of router 1400435: set([22, 7])
Internet port: 1500000
