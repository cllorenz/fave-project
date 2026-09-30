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
   The invariants of T Ch. 4, as functions of one EC's forwarding graph
   (§4.7: "an invariant is a function over one EC's forwarding graph"). VLAN
   isolation (T §4.5) needs rewrites and arrives with V3.
*/

#ifndef VERIFLOW_FR_QUERIES_H_
#define VERIFLOW_FR_QUERIES_H_

#include <cstdint>
#include <map>
#include <set>
#include <utility>
#include <vector>

#include "veriflow.h"

namespace vf {

// How one path through a forwarding graph ends (Q8).
enum class End {
  DELIVERED,  // a consuming rule matched: the packet is delivered here
  DROP_RULE,  // a rule matched and forwards nowhere (an explicit drop, ACL deny)
  NO_MATCH,   // no rule of the table matches (a missing permit or default route)
  UNWIRED,    // a rule forwards to a port that is linked nowhere
  LOOP,       // the path revisits a table (Q20)
};

struct Outcome {
  End end;
  uint32_t table;               // where it ended
  uint64_t rule;                // the deciding rule there, 0 if none
  std::vector<uint32_t> path;   // tables visited, start first, `table` last
};

// Every path of `graph` from `table`, arriving on `in_port` (T §4.1: a DFS
// over the graph, checking at every hop whether the device consumes the
// packet). Outcomes are in DFS order.
std::vector<Outcome> walk(const ForwardingGraph &graph, uint32_t table,
                          int64_t in_port);

// T §4.1: some path from the start is delivered at `dst`.
bool reaches(const std::vector<Outcome> &walked, uint32_t dst);
// T §4.2: no path loops.
bool loop_free(const std::vector<Outcome> &walked);
// T §4.3: the paths that end in a drop, of any of the three kinds, with the
// table and the rule (or its absence) causing it.
std::vector<Outcome> black_holes(const std::vector<Outcome> &walked);
// T §4.4: two starts meant to forward identically deliver to the same tables
// and drop at the same ones.
bool consistent(const std::vector<Outcome> &a, const std::vector<Outcome> &b);
// T §4.6: every delivered path visits every table of `via`, in any order.
bool loose_path(const std::vector<Outcome> &walked, const std::vector<uint32_t> &via);
// T §4.7: every delivered path visits `via` in this order (not necessarily
// adjacently), e.g. the firewall before the local network.
bool strict_path(const std::vector<Outcome> &walked, const std::vector<uint32_t> &via);
// T §4.8: every delivered path takes at most `hops` hops.
bool path_length_within(const std::vector<Outcome> &walked, size_t hops);

// Bulk mode (Q21): a FaVe check's packet set stands in for the new rule. For
// every start (table, arrival port), the tables at which some packet of `range`
// is delivered. The ECs of `range` and their graphs are computed once for all
// starts.
std::vector<std::set<uint32_t>> deliveries(
    const Network &net, const std::string &range,
    const std::vector<std::pair<uint32_t, int64_t>> &starts);

// Delta-net's "what if a link fails?" query (DN §4.3.2), which it adapts from
// the thesis's link-failure experiment (T p.50). OUR READING, pending Q11: the
// failing element is one node-level edge (table, in_port) -> (to_table,
// to_port), and the query constructs the forwarding graph of every EC whose
// packets use it -- whose deciding rule at (table, in_port) forwards on a port
// linked to to_port. Returns those ECs, sorted; `graphs` counts the graphs built.
std::vector<EC> link_failure(const Network &net, uint32_t table, int64_t in_port,
                             uint64_t to_port, size_t *graphs = nullptr);

// ---- device-local slicing (§4.5, T §3.1.3; Q3, Q4, Q22) -------------------

// A packet set: one interval per field.
typedef std::vector<Interval> Box;

// How a walk treats a table it comes back to (Q4).
enum class Revisit {
  // NetPlumber's rule: a PATH that revisits a table ends there, whatever the
  // header (net_plumber/FAVE_CHANGES.md §6). Work grows with the paths.
  PATH,
  // The thesis's: stop "at a device ... already visited for a previously
  // encountered packet set" (T §3.1.3) -- a visited set of (table, arrival,
  // packet set) states, per start, over VeriFlow's forwarding GRAPH (T §4.1:
  // a DFS). Work grows with the states.
  STATE,
};

struct LocalResult {
  std::vector<std::set<uint32_t>> delivered;  // per start: where packets arrive
  bool finished = true;       // false: the budget was exceeded (did not finish)
  uint32_t stopped_at = 0;    // the table where the budget was exceeded
  double predicted = 0;       // the local ECs predicted there
  bool single_table = false;  // that one prediction alone exceeds the budget
  uint64_t local_ecs = 0;     // local ECs sliced in total
  uint64_t hops = 0;          // (table, arrival, set) states expanded
  std::map<uint32_t, uint64_t> per_table;  // local ECs sliced, per table
};

// Bulk checks the thesis's way: device by device. At each table a packet set
// reaches, only the rules that apply there (matching its arrival, Q7) split it
// into LOCAL ECs; each is decided, rewritten, and forwarded, forking per local EC
// (Q3). A path ends where a rule consumes, drops or matches nothing, or where it
// revisits a table -- as NetPlumber's does, whatever the header (Q4, Q20).
// `budget` bounds the local ECs sliced in total (0: none); before slicing at a
// table the count is predicted, and a query that would exceed the budget stops,
// unfinished, naming the table (Q22). Starts are (table, arrival port).
LocalResult local_deliveries(const Network &net, const std::string &range,
                             const std::vector<std::pair<uint32_t, int64_t>> &starts,
                             uint64_t budget = 0, Revisit revisit = Revisit::PATH);

// T §4.5, VLAN isolation: can a packet of `range` from `start`, on some path,
// come to carry `to_value` in `field` (e.g. a VLAN it must not leak into)? The
// thesis keeps track of the VLANs a packet set traverses; with rewrites that is
// the field's interval at every hop.
bool may_carry(const Network &net, const std::string &range,
               std::pair<uint32_t, int64_t> start, size_t field, u128 to_value);

// T §4.9: the rules of the same table a rule overlaps, and so competes with by
// priority. The rule itself need not be in the network.
std::vector<uint64_t> overlapping_in_table(const Network &net, const Rule &rule);

// T §4.10: inserting `rule` would change the next hop, at its own table, of
// these ECs (for some arrival). The network is left unchanged.
std::vector<EC> next_hop_changes(Network &net, const Rule &rule);

}  // namespace vf

#endif  // VERIFLOW_FR_QUERIES_H_
