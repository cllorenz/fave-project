/*
   Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

   This file is part of FaVe.

   FaVe is free software: you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   FaVe is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with FaVe.  If not, see <https://www.gnu.org/licenses/>.
*/

/*
   VeriFlow-FR: an independent implementation of VeriFlow (Khurshid et al.,
   NSDI'13; Khurshid, PhD thesis, UIUC 2015), written from those publications
   alone under the clean-room protocol of VERIFLOW_PLAN.md §5. No code of any
   other VeriFlow implementation was read or used.

   References in comments: T = the thesis, P = the NSDI paper, §/Q/L/D = the
   sections, questions, tests and decisions of VERIFLOW_PLAN.md.
*/

#ifndef VERIFLOW_FR_H_
#define VERIFLOW_FR_H_

#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace vf {

// Header fields are up to 128 bits wide (IPv6 addresses).
__extension__ typedef unsigned __int128 u128;

// ---- header layout ---------------------------------------------------------

struct Field {
  std::string name;
  unsigned width;
};

// The ordered header fields. The order is the trie's dimension order, which the
// thesis measured to matter by an order of magnitude (T Table 3.1): a stamp.
class Layout {
 public:
  explicit Layout(std::vector<Field> fields);
  size_t size() const { return fields_.size(); }
  const Field &field(size_t i) const { return fields_[i]; }
  unsigned offset(size_t i) const { return offsets_[i]; }
  unsigned width() const { return width_; }

 private:
  std::vector<Field> fields_;
  std::vector<unsigned> offsets_;
  unsigned width_;
};

// A match or header set is a ternary string over the whole layout: one of
// '0', '1', 'x' per bit, fields concatenated in layout order.

// ---- intervals -------------------------------------------------------------

struct Interval {
  u128 lo;  // inclusive
  u128 hi;  // inclusive
  bool operator==(const Interval &o) const { return lo == o.lo && hi == o.hi; }
  bool operator<(const Interval &o) const {
    return lo < o.lo || (lo == o.lo && hi < o.hi);
  }
};

// The interval a field's ternary bits denote. Exact, prefix and ANY values are
// intervals; any other ternary value is not, and is refused (std::invalid_argument).
// The V0 survey found none in the suite (VERIFLOW_PLAN.md §9, finding 1).
Interval prefix_to_interval(const std::string &bits);

// "a.b.c.d/len" or "a.b.c.d" as 32 ternary bits.
std::string ipv4_prefix(const std::string &cidr);

// ---- the multi-dimensional ternary trie (§4.2, T Alg. 1/2) ------------------

class TernaryTrie {
 public:
  explicit TernaryTrie(unsigned depth);
  // Alg. 1: follow the rule's bits, a wildcard bit down the wildcard branch,
  // and store the rule at the node reached.
  void insert(uint64_t id, const std::string &bits);
  bool remove(uint64_t id, const std::string &bits);
  // Alg. 2: the rules whose match overlaps `bits`. A concrete bit visits its
  // own branch and the wildcard branch; a wildcard bit visits all three.
  // Sorted ascending.
  std::vector<uint64_t> find_overlapping(const std::string &bits) const;
  size_t node_count() const { return nodes_.size(); }

 private:
  struct Node {
    int32_t child[3];  // '0', '1', 'x'
    std::vector<uint64_t> rules;
  };
  unsigned depth_;
  std::vector<Node> nodes_;
};

// ---- rules, ECs, forwarding graphs -----------------------------------------

constexpr int64_t ANY_PORT = -1;

struct Rule {
  uint64_t id = 0;
  uint32_t table = 0;
  int64_t priority = 0;        // higher wins; a tie goes to the earlier insertion
  int64_t in_port = ANY_PORT;  // Q7: IN_PORT is a matched field, one value or ANY
  std::string match;           // ternary over the layout
  std::vector<uint64_t> out_ports;  // empty: drop (Q8)
  bool consume = false;        // a probe's rule: the packet is delivered here (Q8)
};

// An equivalence class: one interval per field (§4.3, T p.37).
struct EC {
  std::vector<Interval> ranges;
  bool operator==(const EC &o) const { return ranges == o.ranges; }
  bool operator<(const EC &o) const { return ranges < o.ranges; }
};

class Network;

// The forwarding graph of one EC (§4.4): which rule decides at each table, per
// arrival port where that matters.
class ForwardingGraph {
 public:
  // The rule deciding at `table` for a packet of this EC arriving on
  // `in_port`, or nullptr when no rule matches (a drop, Q8). ANY_PORT means
  // the packet arrived on no port (e.g. injected at a source), so a rule
  // qualified by an ingress port does not match it.
  const Rule *decide(uint32_t table, int64_t in_port) const;
  // Where a packet of this EC at (table, in_port) goes: (table, arrival port).
  std::vector<std::pair<uint32_t, int64_t>> next_hops(uint32_t table,
                                                      int64_t in_port) const;
  // Table-to-table edges X -> Y: some deciding rule at X forwards to a port
  // linked to a port of Y.
  std::set<std::pair<uint32_t, uint32_t>> table_edges() const;
  // A path that revisits a table (Q20), from any table and arrival.
  bool has_loop() const;

  // Valid while the network is unchanged: it points into the rule store.

 private:
  std::vector<int64_t> arrivals(uint32_t table) const;
  bool path_revisits(uint32_t table, int64_t in_port,
                     std::vector<uint32_t> &path) const;

  friend class Network;
  const Network *net_ = nullptr;
  // per table: candidate rules containing the EC, best first
  std::map<uint32_t, std::vector<const Rule *>> candidates_;
};

class Network {
 public:
  explicit Network(Layout layout);
  const Layout &layout() const { return layout_; }

  void add_table(uint32_t table);
  void add_port(uint64_t port, uint32_t table);
  void add_link(uint64_t from_port, uint64_t to_port);
  bool remove_link(uint64_t from_port, uint64_t to_port);

  // Insert a rule; returns the ECs it affects, computed with it in place.
  std::vector<EC> add_rule(const Rule &rule);
  // Remove a rule (Q5); returns the ECs it affected.
  std::vector<EC> remove_rule(uint64_t id);

  // GetAffectedEquivalenceClasses over a header set (T §3.2.3): the rules
  // overlapping it network-wide (Q1) split it, per field, into disjoint ranges
  // clipped to the set (Q15); an EC is one range per field (a cartesian product,
  // not minimal, T p.37).
  std::vector<EC> affected_ecs(const std::string &range) const;
  // Rules, at every table, whose match overlaps `range`. Sorted by id.
  std::vector<uint64_t> overlapping_rules(const std::string &range) const;

  // GetForwardingGraph (T §3.2.3), by a second trie traversal (T p.40).
  ForwardingGraph forwarding_graph(const EC &ec) const;

  const Rule &rule(uint64_t id) const { return rules_.at(id); }
  // The table a port belongs to; the ports a port is linked to.
  uint32_t port_table(uint64_t port) const { return port_table_.at(port); }
  const std::vector<uint64_t> &links_from(uint64_t port) const;
  const std::vector<uint64_t> &table_ports(uint32_t table) const;

 private:
  std::string point_of(const EC &ec) const;
  // Per field, the interval a match denotes; refuses a non-prefix field.
  std::vector<Interval> intervals_of(const std::string &match) const;

  Layout layout_;
  TernaryTrie trie_;
  std::map<uint64_t, Rule> rules_;
  std::map<uint64_t, std::vector<Interval>> intervals_;
  std::map<uint64_t, uint64_t> seq_;  // id -> insertion sequence (tie-break)
  uint64_t next_seq_ = 0;
  std::set<uint32_t> tables_;
  std::map<uint64_t, uint32_t> port_table_;
  std::map<uint32_t, std::vector<uint64_t>> table_ports_;
  std::map<uint64_t, std::vector<uint64_t>> links_;
};

}  // namespace vf

#endif  // VERIFLOW_FR_H_
