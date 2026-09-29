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

#include "queries.h"

#include <algorithm>
#include <set>

namespace vf {

namespace {

void walk_from(const ForwardingGraph &g, uint32_t table, int64_t in_port,
               std::vector<uint32_t> &path, std::vector<Outcome> &out) {
  if (std::find(path.begin(), path.end(), table) != path.end()) {
    std::vector<uint32_t> p = path;
    p.push_back(table);
    out.push_back({End::LOOP, table, 0, p});
    return;
  }
  path.push_back(table);
  const Rule *r = g.decide(table, in_port);
  if (!r) {
    out.push_back({End::NO_MATCH, table, 0, path});
  } else if (r->consume) {
    out.push_back({End::DELIVERED, table, r->id, path});
  } else if (r->out_ports.empty()) {
    out.push_back({End::DROP_RULE, table, r->id, path});
  } else {
    // Per out port: a port linked nowhere loses the packet; a linked one
    // continues at the table the link enters, arriving on that port.
    bool unwired = false;
    for (uint64_t p : r->out_ports)
      if (g.network().links_from(p).empty()) unwired = true;
    if (unwired) out.push_back({End::UNWIRED, table, r->id, path});
    for (const auto &hop : g.next_hops(table, in_port))
      walk_from(g, hop.first, hop.second, path, out);
  }
  path.pop_back();
}

// Is `via` a subsequence of `path`?
bool in_order(const std::vector<uint32_t> &path, const std::vector<uint32_t> &via) {
  size_t k = 0;
  for (uint32_t t : path)
    if (k < via.size() && t == via[k]) ++k;
  return k == via.size();
}

}  // namespace

std::vector<Outcome> walk(const ForwardingGraph &graph, uint32_t table,
                          int64_t in_port) {
  std::vector<Outcome> out;
  std::vector<uint32_t> path;
  walk_from(graph, table, in_port, path, out);
  return out;
}

bool reaches(const std::vector<Outcome> &walked, uint32_t dst) {
  for (const Outcome &o : walked)
    if (o.end == End::DELIVERED && o.table == dst) return true;
  return false;
}

bool loop_free(const std::vector<Outcome> &walked) {
  for (const Outcome &o : walked)
    if (o.end == End::LOOP) return false;
  return true;
}

std::vector<Outcome> black_holes(const std::vector<Outcome> &walked) {
  std::vector<Outcome> out;
  for (const Outcome &o : walked)
    if (o.end == End::DROP_RULE || o.end == End::NO_MATCH || o.end == End::UNWIRED)
      out.push_back(o);
  return out;
}

bool consistent(const std::vector<Outcome> &a, const std::vector<Outcome> &b) {
  // The fate of the packets: where they are delivered, and where lost how.
  auto fate = [](const std::vector<Outcome> &w) {
    std::set<std::pair<int, uint32_t>> s;
    for (const Outcome &o : w) s.insert({(int)o.end, o.table});
    return s;
  };
  return fate(a) == fate(b);
}

bool loose_path(const std::vector<Outcome> &walked, const std::vector<uint32_t> &via) {
  for (const Outcome &o : walked) {
    if (o.end != End::DELIVERED) continue;
    for (uint32_t t : via)
      if (std::find(o.path.begin(), o.path.end(), t) == o.path.end()) return false;
  }
  return true;
}

bool strict_path(const std::vector<Outcome> &walked, const std::vector<uint32_t> &via) {
  for (const Outcome &o : walked)
    if (o.end == End::DELIVERED && !in_order(o.path, via)) return false;
  return true;
}

bool path_length_within(const std::vector<Outcome> &walked, size_t hops) {
  for (const Outcome &o : walked)
    if (o.end == End::DELIVERED && o.path.size() - 1 > hops) return false;
  return true;
}

std::vector<uint64_t> overlapping_in_table(const Network &net, const Rule &rule) {
  std::vector<uint64_t> out;
  for (uint64_t id : net.overlapping_rules(rule.match))
    if (id != rule.id && net.rule(id).table == rule.table) out.push_back(id);
  return out;
}

std::vector<EC> next_hop_changes(Network &net, const Rule &rule) {
  // The rule's range is not cut by the rule itself, so the ECs inside it are
  // the same before and after the insertion.
  const std::vector<EC> ecs = net.affected_ecs(rule.match);
  std::vector<std::vector<std::vector<std::pair<uint32_t, int64_t>>>> before;
  std::vector<int64_t> arrivals = {ANY_PORT};
  for (uint64_t p : net.table_ports(rule.table)) arrivals.push_back((int64_t)p);
  for (const EC &ec : ecs) {
    ForwardingGraph g = net.forwarding_graph(ec);
    before.emplace_back();
    for (int64_t a : arrivals) before.back().push_back(g.next_hops(rule.table, a));
  }
  net.add_rule(rule);
  std::vector<EC> changed;
  for (size_t i = 0; i < ecs.size(); ++i) {
    ForwardingGraph g = net.forwarding_graph(ecs[i]);
    for (size_t k = 0; k < arrivals.size(); ++k)
      if (g.next_hops(rule.table, arrivals[k]) != before[i][k]) {
        changed.push_back(ecs[i]);
        break;
      }
  }
  net.remove_rule(rule.id);
  return changed;
}

}  // namespace vf
