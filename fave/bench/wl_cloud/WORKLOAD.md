# wl_cloud: what the workload contains

**This file is GENERATED** by `cloud_census.py` out of the two vendored raw
files, and `test/test_cloud_census.py` re-derives it and compares byte for
byte. Do not edit it by hand -- run `python3 -m bench.wl_cloud.cloud_census`
from `fave/` instead. CLOUD_BENCH_PLAN.md §1.8 is why: a census nobody can
recompute is indistinguishable from a census that stopped being true.

Everything below is measured from these exact bytes:

| file | sha256 |
|---|---|
| `cloud-tf/README.txt` | `b237fbb576d9b9677a6efac57cf3229a499481fc25b18bf941483e698beee10d` |
| `cloud-tf/network.tf` | `626ea331f43dfe0003ba692e207d5aaf426917c28cb61944cd29d835db8120fb` |

`network.tf` states no topology, no device list and no field layout. All
three are derived -- see §1.1 and §1.2 of the plan for the derivations and
the cross-checks that make them measurements rather than guesses.

## Devices: 86

Ports in this dataset are **nodes, not interfaces**: a rule `fwd A -> B`
means a packet at node A moves to node B. A node carrying rules of its own
is a device; one that only injects is a generator; one that only receives is
a probe.

| class | count | what it is |
|---|---:|---|
| `internet_gw` | 1 | the one gateway: anti-spoof filter and inbound destination-NAT |
| `core` | 5 | datacenter cores: inter-leaf and inter-datacenter routing, outbound source-NAT |
| `leaf_in` | 40 | leaf-router ingress: the ACL, and the decision to go up or across |
| `leaf_out` | 40 | leaf-router egress: host distribution, nothing else |

> CLOUD_BENCH_PLAN.md §1.2 says **85** here and then adds the gateway back in
> §1.3. It classifies by "appears as both a rule in-port and an out-port",
> and every one of the gateway's 19 rules either drops or NATs, so the
> gateway never appears as anybody's out-port. `cloud_tf.classify_nodes`
> classifies by "has rules of its own" and gets 86 directly, which is what
> the model is built from. The two readings agree; one needs a footnote.

Around the devices, 2,401 endpoint nodes:

| class | count | what it is |
|---|---:|---|
| `host_tx` | 1,200 | host transmit nodes -> FaVe generators |
| `host_rx` | 1,200 | host receive nodes -> FaVe probes |
| `internet_rx` | 1 | the internet egress sink -> one more probe |

2,487 nodes are named in total. The host count is 5 datacenters x 8 leaf
routers x 30 hosts, which is `README.txt`'s generator parameters exactly --
and the `.tf` file states none of them.

## Topology: 145 links

| from | to | links |
|---|---|---:|
| `leaf_in` | `leaf_out` | 40 |
| `core` | `leaf_in` | 40 |
| `leaf_in` | `core` | 40 |
| `core` | `core` | 20 |
| `internet_gw` | `core` | 5 |

A fat tree of height 1 per datacenter, five datacenters in a full mesh
above them, and one gateway above that. The 2,400 host attachments and the
core-to-`internet_rx` egresses are generators and probes rather than links,
which is why `topology.json` carries 145 and not more.

## Rules: 2,941

2,913 `fwd` and 28 `rw`. 45 of them have no out-port and discard, spread over
41 distinct nodes.

1,200 sit on the host transmit nodes -- one each, a pure source-address
constraint -- and become FaVe **generators**, not table rules. The other
**1,741 are the data plane**, and that is the number `routes.json` carries.

> CLOUD_BENCH_PLAN.md §1.3 says "~1,722 table rules". It is 1,741. The figure
> was computed as 2,941 - 1,219, subtracting the gateway's 19 rules along with
> the 1,200 host injectors, while also counting the gateway as one of the 86
> tables. The gateway's rules ARE table rules. The model was never wrong --
> only the figure describing it.

### By function

A rule is classified by **what it does**, never by which device it sits on:

| function | test |
|---|---|
| `deny` | no out-port: the packet is discarded |
| `nat` | a `rw` rule: it rewrites the address it forwards on |
| `acl-permit` | constrains a transport port, so it admits a SERVICE rather than a destination |
| `forward` | everything else: a routing decision on the destination alone, or an unconditioned uplink |

| device class | `deny` | `nat` | `acl-permit` | `forward` | total |
|---|---:|---:|---:|---:|---:|
| `internet_gw` | 5 | 14 |  |  | 19 |
| `core` |  | 14 |  | 60 | 74 |
| `leaf_in` | 40 |  | 368 | 40 | 448 |
| `leaf_out` |  |  |  | 1,200 | 1,200 |
| **total** | **45** | **28** | **368** | **1,300** | **1,741** |

So the workload is **413 ACL rules** -- 368 permits and 45 denials, the
latter being 40 leaf default-denies plus the gateway's 5 anti-spoof drops
-- against **1,300 forwarding rules** and **28 NAT rules**.

The shape of each class is regular enough to state outright:

* **`leaf_in`** carries the whole access-control layer: 368 permits, one
  unconditioned default-deny per leaf (`dst in <my /25>` -> DROP), and one
  unconditioned uplink per leaf to its core.
* **`leaf_out`** is pure distribution: 1,200 `/30` host routes, 30 per leaf.
* **`core`** carries 12 routes each -- 8 local leaf `/25`s and 4 peer-
  datacenter `/22`s -- plus the outbound source-NAT.
* **`internet_gw`** is 5 anti-spoof drops (`121.140.254.0/27`, `127/8`,
  `10/8`, `172.16/12`, `192.168/16`) and 14 destination-NAT rules.

### The ACL permits split by source

| permits | count | meaning |
|---|---:|---|
| constrain a source | 339 | the matrix's private half: one rule per authorised pair, per direction |
| constrain no source | 29 | a PUBLIC service -- admits every source, not only the Internet |

That second row is the workload's own finding, not an artefact of the
reading: the generator implements "the Internet may reach service *i*" as a
rule with no source match at all, so every public service is reachable from
every role while the matrix authorises far fewer. `matrix/reach.txt` is
expected to report violations concentrated entirely there, and
`matrix/reach_public.txt` is expected to be clean.

## Header fields

The 128-bit match layout was **recovered by measuring** which bit positions
the 2,941 rules constrain; nothing in the file declares it. It is not
`wl_stanford`'s layout, but both put the destination at bit 48 -- so a
reader using the wrong one still produces plausible forwarding and goes
wrong only on the ACL and NAT fields.

| field | offset | width | rules constraining it |
|---|---:|---:|---:|
| `packet.ether.vlan` | 0 | 16 | **0 -- never used** |
| `packet.ipv4.source` | 16 | 32 | 1,558 |
| `packet.ipv4.destination` | 48 | 32 | 1,682 |
| `packet.ipv6.proto` | 80 | 8 | 396 |
| `packet.upper.sport` | 88 | 16 | 353 |
| `packet.upper.dport` | 104 | 16 | 382 |
| `packet.upper.tcp.flags` | 120 | 8 | **0 -- never used** |

Counted as **rules whose field is not fully wildcarded** -- one well-defined
number per field. CLOUD_BENCH_PLAN.md §1.1 tabulates per-BIT density
instead, which for an IP field is a range rather than a number (a `/22`
constrains 22 of its 32 bits and a `/30` constrains 30), and its "~1,555"
for the source is 1,558 under this definition.

Five of the seven are exercised. The only protocol value that ever appears
is 6 (TCP) and the only transport ports are 331..355, as destination and as
source both.

FaVe runs with one field the dataset does not have: **`related` at bit 128**,
taking the header to 136 bits. `bench/reach_csv_to_checks.py` puts
`f=related:0` on every conditionally permitted check, and this network has no
connection tracking at all -- no rule and no generator ever constrains the
field, so it stays wildcard and the condition overlaps every flow. That is
exactly the "all packets are new" reading a stateless model deserves, and it
is why the policy uses `--->` rather than `<->>`.

## The ACL matrix, and the two phases over it

`README.txt` carries a **26x26 matrix over 26 roles**: services 0-24 plus
the Internet at index 25. It is fully symmetric, its diagonal carries 0 permissions,
and it authorises **226 ordered pairs** of 676 -- 33.4% density.

The service algebra is measured, not assumed:

    service i  <->  TCP port 331 + i  <->  public address 121.140.254.i

and index 25 being the Internet is confirmed by four independently derived
sets coinciding exactly (`test_cloud_readme.py`). Two phases run over this
same data plane:

| phase | roles | endpoints | services | provenance of the policy |
|---|---:|---:|---:|---|
| oracle | 8 | 8 | 4 | HAND-WRITTEN: the dataset ships no inventory, so §1.9 states its six `.smt2` questions as FPL |
| matrix | 26 | 65 | 25 | GENERATED from `README.txt`: the roles, the services and the policy are all the dataset's |

Which is why the two phases' `roles_and_services.txt` and `reach.txt` have
the same names and do not share a directory. See `README.md`.

