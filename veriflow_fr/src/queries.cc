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
#include <functional>
#include <set>
#include <stdexcept>

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

std::vector<std::set<uint32_t>> deliveries(
    const Network &net, const std::string &range,
    const std::vector<std::pair<uint32_t, int64_t>> &starts) {
  if (net.has_rewrites())
    throw std::logic_error(
        "network-wide slicing cannot follow rewrites: \"we can no longer compute "
        "network-wide equivalence classes\" (T 3.1.3) -- use local_deliveries");
  std::vector<std::set<uint32_t>> out(starts.size());
  for (const EC &ec : net.affected_ecs(range)) {
    const ForwardingGraph g = net.forwarding_graph(ec);
    for (size_t i = 0; i < starts.size(); ++i) {
      // Breadth-first over (table, arrival) states. It delivers where the
      // path walk does, and a visited state is never expanded twice, so a
      // loop ends by construction and large graphs stay linear.
      std::set<std::pair<uint32_t, int64_t>> seen = {starts[i]};
      std::vector<std::pair<uint32_t, int64_t>> queue = {starts[i]};
      for (size_t k = 0; k < queue.size(); ++k) {
        const auto [table, in_port] = queue[k];
        const Rule *r = g.decide(table, in_port);
        if (!r) continue;
        if (r->consume) {
          out[i].insert(table);
          continue;
        }
        for (const auto &hop : g.next_hops(table, in_port))
          if (seen.insert(hop).second) queue.push_back(hop);
      }
    }
  }
  return out;
}

namespace {

// Device-local slicing (T §3.1.3): the walk over (table, arrival, packet set).
struct Slicer {
  const Network &net;
  uint64_t budget;
  LocalResult &res;
  std::function<void(uint32_t, const Box &)> on_state;

  struct Abort {};

  void walk(uint32_t table, int64_t arrival, const Box &box,
            std::vector<uint32_t> &path, std::set<uint32_t> &out) {
    // Q4, Q20: a path that revisits a table ends there, whatever the header.
    if (std::find(path.begin(), path.end(), table) != path.end()) return;
    if (on_state) on_state(table, box);

    // The rules that apply here (IN_PORT is a matched field, Q7) and overlap
    // the set; best first.
    std::vector<uint64_t> cand;
    for (uint64_t id : net.table_rules(table)) {
      const Rule &r = net.rule(id);
      if (r.in_port != ANY_PORT && (arrival == ANY_PORT || r.in_port != arrival)) continue;
      const std::vector<Interval> &iv = net.rule_intervals(id);
      bool meets = true;
      for (size_t f = 0; f < box.size() && meets; ++f)
        meets = iv[f].lo <= box[f].hi && box[f].lo <= iv[f].hi;
      if (meets) cand.push_back(id);
    }
    std::sort(cand.begin(), cand.end(), [this](uint64_t a, uint64_t b) {
      const Rule &ra = net.rule(a), &rb = net.rule(b);
      if (ra.priority != rb.priority) return ra.priority > rb.priority;
      return net.insertion_seq(a) < net.insertion_seq(b);
    });

    // Local ECs: per field, the ranges the candidates' boundaries cut in the set.
    std::vector<std::vector<Interval>> per_field(box.size());
    double predicted = 1;
    for (size_t f = 0; f < box.size(); ++f) {
      std::vector<u128> cuts = {box[f].lo};
      for (uint64_t id : cand) {
        const Interval i = net.rule_intervals(id)[f];
        if (i.lo > box[f].lo) cuts.push_back(i.lo);
        if (i.hi < box[f].hi) cuts.push_back(i.hi + 1);
      }
      std::sort(cuts.begin(), cuts.end());
      cuts.erase(std::unique(cuts.begin(), cuts.end()), cuts.end());
      for (size_t k = 0; k < cuts.size(); ++k)
        per_field[f].push_back({cuts[k], k + 1 < cuts.size() ? cuts[k + 1] - 1 : box[f].hi});
      predicted *= (double)per_field[f].size();
    }
    // Q22: predict before enumerating, and stop unfinished past the budget.
    if (budget && (double)res.local_ecs + predicted > (double)budget) {
      res.finished = false;
      res.stopped_at = table;
      res.predicted = predicted;
      throw Abort{};
    }
    res.local_ecs += (uint64_t)predicted;
    ++res.hops;

    path.push_back(table);
    std::vector<size_t> pick(box.size(), 0);
    while (true) {
      Box ec(box.size());
      for (size_t f = 0; f < box.size(); ++f) ec[f] = per_field[f][pick[f]];
      // No candidate splits a local EC, so the first containing its low
      // corner decides it.
      const Rule *best = nullptr;
      for (uint64_t id : cand) {
        const std::vector<Interval> &iv = net.rule_intervals(id);
        bool in = true;
        for (size_t f = 0; f < box.size() && in; ++f)
          in = iv[f].lo <= ec[f].lo && ec[f].lo <= iv[f].hi;
        if (in) { best = &net.rule(id); break; }
      }
      if (best && best->consume) {
        out.insert(table);
      } else if (best) {
        Box next = ec;
        for (const auto &rw : best->rewrites) next[rw.first] = rw.second;
        if (on_state) on_state(table, next);
        for (uint64_t p : best->out_ports)
          for (uint64_t to : net.links_from(p))
            walk(net.port_table(to), (int64_t)to, next, path, out);
      }
      size_t f = box.size();
      bool done = true;
      while (f > 0) {
        --f;
        if (++pick[f] < per_field[f].size()) { done = false; break; }
        pick[f] = 0;
      }
      if (done) break;
    }
    path.pop_back();
  }
};

Box box_of(const Network &net, const std::string &range) {
  const Layout &l = net.layout();
  if (range.size() != l.width()) throw std::invalid_argument("range width");
  Box b;
  for (size_t f = 0; f < l.size(); ++f)
    b.push_back(prefix_to_interval(range.substr(l.offset(f), l.field(f).width)));
  return b;
}

}  // namespace

LocalResult local_deliveries(const Network &net, const std::string &range,
                             const std::vector<std::pair<uint32_t, int64_t>> &starts,
                             uint64_t budget) {
  LocalResult res;
  res.delivered.resize(starts.size());
  const Box box = box_of(net, range);
  Slicer s{net, budget, res, nullptr};
  try {
    for (size_t i = 0; i < starts.size(); ++i) {
      std::vector<uint32_t> path;
      s.walk(starts[i].first, starts[i].second, box, path, res.delivered[i]);
    }
  } catch (const Slicer::Abort &) {
  }
  return res;
}

bool may_carry(const Network &net, const std::string &range,
               std::pair<uint32_t, int64_t> start, size_t field, u128 to_value) {
  LocalResult res;
  bool carries = false;
  Slicer s{net, 0, res, [&](uint32_t, const Box &b) {
             if (b[field].lo <= to_value && to_value <= b[field].hi) carries = true;
           }};
  std::vector<uint32_t> path;
  std::set<uint32_t> out;
  s.walk(start.first, start.second, box_of(net, range), path, out);
  return carries;
}

std::vector<EC> link_failure(const Network &net, uint32_t table, int64_t in_port,
                             uint64_t to_port, size_t *graphs) {
  // The table's ports that the failing edge leaves by.
  std::set<uint64_t> via;
  for (uint64_t p : net.table_ports(table))
    for (uint64_t q : net.links_from(p))
      if (q == to_port) via.insert(p);
  auto uses = [&via](const Rule *r) {
    if (!r) return false;
    for (uint64_t p : r->out_ports)
      if (via.count(p)) return true;
    return false;
  };
  std::set<EC> hit, tried;
  size_t built = 0;
  if (!via.empty()) {
    for (uint64_t id : net.table_rules(table)) {
      const Rule &r = net.rule(id);
      // Only a rule that can decide at this node, and forwards on the edge,
      // can put packets on it; its ECs are where to look.
      const bool arrives = r.in_port == ANY_PORT ||
                           (in_port != ANY_PORT && r.in_port == in_port);
      if (!arrives || !uses(&r)) continue;
      for (const EC &ec : net.affected_ecs(r.match)) {
        if (!tried.insert(ec).second) continue;
        const ForwardingGraph g = net.forwarding_graph(ec);
        ++built;
        if (uses(g.decide(table, in_port))) hit.insert(ec);
      }
    }
  }
  if (graphs) *graphs = built;
  return std::vector<EC>(hit.begin(), hit.end());
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
