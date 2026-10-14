# wl_tum

One stateful IPv4 firewall, `fw.tum`, filtering the VLANs of TUM's Chair of
Network Architectures and Services: `rulesets/tum-ruleset`, 3,794 flattened
`iptables -A FORWARD` rules (policy DROP; 3,224 ACCEPT, 570 DROP) over 21
VLANs on one interface `eth1`, flattened by fffuu from the 2015 dump
`iptables-save-2015-05-15_15-23-41_tum` (`fffuu_to_fave.sh`).

Since 2026-10-14 (owner) wl_tum has **two models**:

| | the policy model (default) | the single variant |
|---|---|---|
| where | `bench/wl_tum/*.json` | `bench/wl_tum/single/*.json` |
| sources | 247: the Internet and one per endpoint | 1, `source.tum` (`tcp_src=10000;tcp_dst=80`) |
| probes | 247, behind the VLAN demultiplexer `vlans.tum` | 1, universal, on `fw.tum.forward_filter_accept` |
| checks | 8,497 (`checks.json`) | none |
| used by | the incremental campaign (D10) onwards | V5, the D11 run, `test_apkeep_tum`, `test_apkeep_ndd_fwd`, `test_veriflow_differential` |

`test/gen_wl_tum_inputs.sh` generates both; `bench/wl_tum/benchmark.py` runs
the policy model. A replay of the single variant is `replay('bench/wl_tum/single')`.

## The policy is FABRICATED, and derived

The dataset ships a ruleset and no policy. The FPL inventory and policy here
(`roles_and_services.txt`, `reach.txt`, generated, gitignored) are read off
the ruleset by `service_matrix.py`, which **does not use FaVe's engines**:
the policy states what an independent reading of the ruleset says, so checking
an engine against it cross-checks the engine. The owner chose this over a
generic `A <-> B` policy (2026-10-14) for that reason.

- **Endpoints** (`service_matrix.endpoints`). Every host a rule names as a
  single destination (227), the rest of each inside VLAN (19; subnets from
  the 2015 dump's `-j mac_<v>` and `-j filter_<v>` jumps, `vlans.py`), and
  the Internet.
- **The Internet** is an ANONYMOUS outside host, `198.51.100.0/24` (RFC 5737,
  TEST-NET-2), on uplink VLAN 110 in and either uplink (110, 1024) out --
  not "any address": some rules single out partners (`138.246.253.5` may reach
  every port of whole subnets), and with any address as the Internet nearly
  everything counted as reachable. Every rule contains the prefix whole or
  misses it, so all its addresses behave alike (asserted).
- **Services.** One per TCP and UDP destination-port class -- the ports every
  rule treats alike, split at every boundary a rule names (173 + 136) -- and
  one per portless protocol (icmp, esp, gre): 312.
- **What a role offers.** The services its own rules name, every service the
  Internet reaches on it, and one port per protocol no rule names
  specifically (`other_service`: tcp 44445-65535, udp 29999-59999).
- **The rules.** `Internet <->> R.S` for every service S the Internet reaches
  on R (7,301), and `R <->> Internet` for every role that can open any
  connection out (all 246) -- the owner's "B <->> Internet", per role.
- **The checks** (`reach_csv_to_checks.py --strict --only-with Internet
  --deny-unpermitted-services`): 7,301 must-reach per service, 704
  must-not-reach for offered and unreachable services, 246 return traffic,
  246 outbound. Traffic between inside roles is not stated, so not checked.

A packet in the evaluator is a NEW connection's first packet (state NEW, a TCP
SYN). It refuses any iptables feature it does not model.

## The model

`layout.py` is shared by the generators. `fw.tum`'s chains tag a flow's
destination VLAN (`-o eth1.<v>` is `dvlan=<v>`, FaVe's `-o` semantics,
`devices/abstract_firewall.py`), and nothing in the firewall model separates
destinations: every VLAN is `eth1`, and its post-routing drops a packet leaving
by its ingress port. So a FaVe **switch**, `vlans.tum`, hangs off the forward
chain's accept port and selects what routing would send to each endpoint: a
rule per endpoint matching its VLAN AND its addresses (a host's /32 before its
VLAN's prefixes; the Internet's prefix on each uplink), 249 rules. Each
source enters the forward chain as from its VLAN (`in_port` eth1's ingress,
`svlan`, `ipv4_src`).

## Found while building it (2026-10-14)

1. **FaVe lost a port range's upper bound** (`util/packet_util.py`, fixed in
   `0ca9dbf5`): `--dports 21:22` was port 21 alone -- 244 of this ruleset's
   356 ranges, on every engine. NetPlumber disagreed with the evaluator on
   exactly six checks, all such a bound; after the fix on none.
2. **NetPlumber's adapter took a switch's declared table id as its table
   index**, unchecked, and reset its counter after it: `vlans.tum` declaring
   id 1 landed on `fw.tum`'s first table and nothing passed. Fixed: the
   adapter picks a fresh index per table name (owner, 2026-10-14), and
   `vlans.tum` declares no id.
3. **A switch port named `1` is its table's name** (`devices/switch.py`
   names a switch's table `<node>.1`): `vlans.tum` numbers its ports from 1000.
4. **Both APKeep engines drop `svlan` and `dvlan` from packet-filter rules**
   (`apkeep/adapter.py`, `_capture_pf_rule`), so a rule bound to one VLAN acts
   on all of them. See TODO.md.
