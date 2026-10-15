# Report
<introductionary text>

## Compliance Check
The following compliance violations have been found:

- `source.internet` reaches `probe.dc0_leaf1_host1`
- `source.dc0_leaf1_host1` reaches `probe.dc0_leaf1_host1`
- `source.dc1_leaf0_host20` reaches `probe.dc0_leaf1_host1`
- `source.dc1_leaf5_host5` reaches `probe.dc0_leaf1_host1`
- `source.dc1_leaf6_host0` does not reach `probe.dc0_leaf1_host1` with 
    - related=0
    - packet.ipv6.proto=6
    - packet.upper.dport=351
- `source.dc1_leaf6_host0` reaches `probe.dc0_leaf1_host1` with 
    - related=0
    - packet.upper.dport=351
- `source.dc1_leaf6_host2` reaches `probe.dc0_leaf1_host1` with 
    - related=0
    - packet.upper.dport=350
- `source.dc2_leaf7_host6` reaches `probe.dc0_leaf1_host1`
- `source.dc4_leaf3_host22` reaches `probe.dc0_leaf1_host1`
- `source.dc0_leaf1_host1` reaches `probe.dc1_leaf0_host20`
- `source.dc1_leaf0_host20` reaches `probe.dc1_leaf0_host20`
- `source.dc1_leaf5_host5` reaches `probe.dc1_leaf0_host20`
- `source.dc1_leaf6_host0` reaches `probe.dc1_leaf0_host20`
- `source.dc1_leaf6_host2` reaches `probe.dc1_leaf0_host20`
- `source.dc2_leaf7_host6` reaches `probe.dc1_leaf0_host20`
- `source.dc4_leaf3_host22` reaches `probe.dc1_leaf0_host20`
- `source.dc0_leaf1_host1` reaches `probe.dc1_leaf5_host5`
- `source.dc1_leaf0_host20` reaches `probe.dc1_leaf5_host5`
- `source.dc1_leaf5_host5` reaches `probe.dc1_leaf5_host5`
- `source.dc1_leaf6_host0` reaches `probe.dc1_leaf5_host5`
- `source.dc1_leaf6_host2` reaches `probe.dc1_leaf5_host5`
- `source.dc2_leaf7_host6` reaches `probe.dc1_leaf5_host5`
- `source.dc4_leaf3_host22` reaches `probe.dc1_leaf5_host5`
- `source.internet` reaches `probe.dc1_leaf6_host0`
- `source.dc0_leaf1_host1` reaches `probe.dc1_leaf6_host0`
- `source.dc1_leaf0_host20` reaches `probe.dc1_leaf6_host0`
- `source.dc1_leaf5_host5` reaches `probe.dc1_leaf6_host0`
- `source.dc1_leaf6_host0` reaches `probe.dc1_leaf6_host0`
- `source.dc1_leaf6_host2` reaches `probe.dc1_leaf6_host0`
- `source.dc2_leaf7_host6` reaches `probe.dc1_leaf6_host0`
- `source.dc4_leaf3_host22` reaches `probe.dc1_leaf6_host0`
- `source.internet` reaches `probe.dc1_leaf6_host2`
- `source.dc0_leaf1_host1` reaches `probe.dc1_leaf6_host2`
- `source.dc1_leaf0_host20` reaches `probe.dc1_leaf6_host2`
- `source.dc1_leaf5_host5` reaches `probe.dc1_leaf6_host2`
- `source.dc1_leaf6_host0` reaches `probe.dc1_leaf6_host2`
- `source.dc1_leaf6_host2` reaches `probe.dc1_leaf6_host2`
- `source.dc2_leaf7_host6` reaches `probe.dc1_leaf6_host2`
- `source.dc4_leaf3_host22` reaches `probe.dc1_leaf6_host2`
- `source.dc0_leaf1_host1` reaches `probe.dc2_leaf7_host6`
- `source.dc1_leaf0_host20` reaches `probe.dc2_leaf7_host6`
- `source.dc1_leaf5_host5` reaches `probe.dc2_leaf7_host6`
- `source.dc1_leaf6_host0` reaches `probe.dc2_leaf7_host6`
- `source.dc1_leaf6_host2` reaches `probe.dc2_leaf7_host6`
- `source.dc0_leaf1_host1` reaches `probe.dc4_leaf3_host22`
- `source.dc1_leaf0_host20` reaches `probe.dc4_leaf3_host22`
- `source.dc1_leaf5_host5` reaches `probe.dc4_leaf3_host22`
- `source.dc1_leaf6_host0` reaches `probe.dc4_leaf3_host22`
- `source.dc1_leaf6_host2` reaches `probe.dc4_leaf3_host22`
- `source.dc2_leaf7_host6` reaches `probe.dc4_leaf3_host22`
- `source.dc4_leaf3_host22` reaches `probe.dc4_leaf3_host22`
- `source.dc0_leaf1_host1` reaches `probe.internet`
- `source.dc1_leaf0_host20` reaches `probe.internet`
- `source.dc1_leaf5_host5` reaches `probe.internet`
- `source.dc1_leaf6_host0` reaches `probe.internet`
- `source.dc1_leaf6_host2` reaches `probe.internet`
- `source.dc4_leaf3_host22` reaches `probe.internet`

## Anomaly Check
Not checked: the ad6 backend does not implement anomaly detection.
