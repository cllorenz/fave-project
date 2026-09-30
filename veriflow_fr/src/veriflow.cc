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

#include "veriflow.h"

#include <algorithm>
#include <cstdio>
#include <sstream>
#include <stdexcept>

namespace vf {

// ---- layout ----------------------------------------------------------------

Layout::Layout(std::vector<Field> fields) : fields_(std::move(fields)), width_(0) {
  for (const Field &f : fields_) {
    if (f.width == 0 || f.width > 128)
      throw std::invalid_argument("field " + f.name + ": width must be 1..128");
    offsets_.push_back(width_);
    width_ += f.width;
  }
}

// ---- intervals -------------------------------------------------------------

Interval prefix_to_interval(const std::string &bits) {
  if (bits.empty() || bits.size() > 128)
    throw std::invalid_argument("a field is 1..128 bits");
  u128 lo = 0, hi = 0;
  bool wild = false;
  for (char c : bits) {
    if (c == 'x') {
      wild = true;
      lo = lo << 1;
      hi = (hi << 1) | 1;
    } else if (c == '0' || c == '1') {
      if (wild)
        throw std::invalid_argument("not a prefix: " + bits);
      lo = (lo << 1) | (u128)(c == '1');
      hi = (hi << 1) | (u128)(c == '1');
    } else {
      throw std::invalid_argument("not a ternary bit string: " + bits);
    }
  }
  return {lo, hi};
}

std::string ipv4_prefix(const std::string &cidr) {
  unsigned a, b, c, d, len = 32;
  char slash = 0;
  int n = sscanf(cidr.c_str(), "%u.%u.%u.%u%c%u", &a, &b, &c, &d, &slash, &len);
  if (!(n == 4 || (n == 6 && slash == '/')) || a > 255 || b > 255 || c > 255 ||
      d > 255 || len > 32)
    throw std::invalid_argument("not an IPv4 prefix: " + cidr);
  uint32_t addr = (a << 24) | (b << 16) | (c << 8) | d;
  std::string s(32, 'x');
  for (unsigned i = 0; i < len; ++i) s[i] = (addr >> (31 - i)) & 1 ? '1' : '0';
  return s;
}

// ---- the ternary trie ------------------------------------------------------

namespace {
int branch(char c) {
  switch (c) {
    case '0': return 0;
    case '1': return 1;
    case 'x': return 2;
  }
  throw std::invalid_argument(std::string("not a ternary bit: ") + c);
}
}  // namespace

TernaryTrie::TernaryTrie(unsigned depth) : depth_(depth) {
  nodes_.push_back(Node{{-1, -1, -1}, {}});
}

void TernaryTrie::insert(uint64_t id, const std::string &bits) {
  if (bits.size() != depth_) throw std::invalid_argument("match width");
  int32_t node = 0;
  for (char c : bits) {
    int b = branch(c);
    if (nodes_[node].child[b] < 0) {
      nodes_[node].child[b] = (int32_t)nodes_.size();
      nodes_.push_back(Node{{-1, -1, -1}, {}});
    }
    node = nodes_[node].child[b];
  }
  nodes_[node].rules.push_back(id);
}

bool TernaryTrie::remove(uint64_t id, const std::string &bits) {
  if (bits.size() != depth_) throw std::invalid_argument("match width");
  int32_t node = 0;
  for (char c : bits) {
    node = nodes_[node].child[branch(c)];
    if (node < 0) return false;
  }
  std::vector<uint64_t> &rs = nodes_[node].rules;
  auto it = std::find(rs.begin(), rs.end(), id);
  if (it == rs.end()) return false;
  rs.erase(it);
  return true;
}

std::vector<uint64_t> TernaryTrie::find_overlapping(const std::string &bits) const {
  if (bits.size() != depth_) throw std::invalid_argument("query width");
  std::vector<uint64_t> out;
  std::vector<std::pair<int32_t, unsigned>> stack = {{0, 0}};
  while (!stack.empty()) {
    auto [node, level] = stack.back();
    stack.pop_back();
    if (level == depth_) {
      out.insert(out.end(), nodes_[node].rules.begin(), nodes_[node].rules.end());
      continue;
    }
    const int32_t *ch = nodes_[node].child;
    const char c = bits[level];
    // A concrete bit visits its own branch and the wildcard branch; a
    // wildcard visits all three (T Alg. 2).
    if (c != '1' && ch[0] >= 0) stack.push_back({ch[0], level + 1});
    if (c != '0' && ch[1] >= 0) stack.push_back({ch[1], level + 1});
    if (ch[2] >= 0) stack.push_back({ch[2], level + 1});
    if (c != '0' && c != '1' && c != 'x') branch(c);  // throws
  }
  std::sort(out.begin(), out.end());
  return out;
}

// ---- network ---------------------------------------------------------------

Network::Network(Layout layout) : layout_(std::move(layout)), trie_(layout_.width()) {}

void Network::add_table(uint32_t table) { tables_.insert(table); }

void Network::add_port(uint64_t port, uint32_t table) {
  if (!tables_.count(table)) throw std::invalid_argument("unknown table");
  if (port_table_.count(port)) throw std::invalid_argument("duplicate port");
  port_table_[port] = table;
  table_ports_[table].push_back(port);
}

void Network::add_link(uint64_t from_port, uint64_t to_port) {
  if (!port_table_.count(from_port) || !port_table_.count(to_port))
    throw std::invalid_argument("link between unknown ports");
  links_[from_port].push_back(to_port);
}

bool Network::remove_link(uint64_t from_port, uint64_t to_port) {
  auto it = links_.find(from_port);
  if (it == links_.end()) return false;
  auto &v = it->second;
  auto pos = std::find(v.begin(), v.end(), to_port);
  if (pos == v.end()) return false;
  v.erase(pos);
  return true;
}

const std::vector<uint64_t> &Network::links_from(uint64_t port) const {
  static const std::vector<uint64_t> none;
  auto it = links_.find(port);
  return it == links_.end() ? none : it->second;
}

const std::vector<uint64_t> &Network::table_ports(uint32_t table) const {
  static const std::vector<uint64_t> none;
  auto it = table_ports_.find(table);
  return it == table_ports_.end() ? none : it->second;
}

const std::vector<uint64_t> &Network::table_rules(uint32_t table) const {
  static const std::vector<uint64_t> none;
  auto it = table_rules_.find(table);
  return it == table_rules_.end() ? none : it->second;
}

std::vector<Interval> Network::intervals_of(const std::string &match) const {
  if (match.size() != layout_.width())
    throw std::invalid_argument("match width differs from the layout");
  std::vector<Interval> out;
  for (size_t f = 0; f < layout_.size(); ++f)
    out.push_back(prefix_to_interval(
        match.substr(layout_.offset(f), layout_.field(f).width)));
  return out;
}

void Network::load_rule(const Rule &rule) {
  if (rules_.count(rule.id)) throw std::invalid_argument("duplicate rule id");
  if (!tables_.count(rule.table)) throw std::invalid_argument("unknown table");
  for (uint64_t p : rule.out_ports)
    if (!port_table_.count(p)) throw std::invalid_argument("unknown out port");
  if (rule.in_port != ANY_PORT &&
      (!port_table_.count((uint64_t)rule.in_port) ||
       port_table_.at((uint64_t)rule.in_port) != rule.table))
    throw std::invalid_argument("in_port is not a port of the rule's table");
  intervals_[rule.id] = intervals_of(rule.match);  // refuses a non-prefix field
  for (const auto &rw : rule.rewrites)
    if (rw.first >= layout_.size())
      throw std::invalid_argument("rewrite of an unknown field");
  if (!rule.rewrites.empty()) ++rewriting_;
  rules_[rule.id] = rule;
  seq_[rule.id] = next_seq_++;
  trie_.insert(rule.id, rule.match);
  table_rules_[rule.table].push_back(rule.id);
}

std::vector<EC> Network::add_rule(const Rule &rule) {
  load_rule(rule);
  return affected_ecs(rule.match);
}

std::vector<EC> Network::remove_rule(uint64_t id) {
  auto it = rules_.find(id);
  if (it == rules_.end()) throw std::invalid_argument("unknown rule id");
  // Q5: the ECs the rule affects, computed while it is still in place, the same
  // partition its insertion produced.
  std::vector<EC> ecs = affected_ecs(it->second.match);
  if (!it->second.rewrites.empty()) --rewriting_;
  trie_.remove(id, it->second.match);
  std::vector<uint64_t> &tr = table_rules_[it->second.table];
  tr.erase(std::find(tr.begin(), tr.end(), id));
  intervals_.erase(id);
  seq_.erase(id);
  rules_.erase(it);
  return ecs;
}

std::vector<uint64_t> Network::overlapping_rules(const std::string &range) const {
  return trie_.find_overlapping(range);
}

std::vector<std::vector<Interval>> Network::field_ranges(const std::string &range) const {
  const std::vector<Interval> bounds = intervals_of(range);
  const std::vector<uint64_t> overlap = trie_.find_overlapping(range);

  // Per field, the cut points: where a rule's range, clipped to the set,
  // begins or ends (Q15). Between two cuts no rule changes, so no rule splits
  // the range (T p.37).
  std::vector<std::vector<Interval>> per_field(layout_.size());
  for (size_t f = 0; f < layout_.size(); ++f) {
    const Interval r = bounds[f];
    std::vector<u128> cuts = {r.lo};
    for (uint64_t id : overlap) {
      const Interval i = intervals_.at(id)[f];
      u128 lo = std::max(i.lo, r.lo), hi = std::min(i.hi, r.hi);
      if (lo > r.lo) cuts.push_back(lo);
      if (hi < r.hi) cuts.push_back(hi + 1);
    }
    std::sort(cuts.begin(), cuts.end());
    cuts.erase(std::unique(cuts.begin(), cuts.end()), cuts.end());
    for (size_t k = 0; k < cuts.size(); ++k)
      per_field[f].push_back({cuts[k], k + 1 < cuts.size() ? cuts[k + 1] - 1 : r.hi});
  }
  return per_field;
}

ECCount Network::ec_count(const std::string &range) const {
  ECCount c;
  c.exact = 1;
  c.approx = 1;
  for (const auto &ranges : field_ranges(range)) {
    const size_t n = ranges.size();
    c.per_field.push_back(n);
    c.approx *= (double)n;
    if (!c.saturated) {
      const u128 max = ~(u128)0;
      if (c.exact > max / n) c.saturated = true;
      else c.exact *= n;
    }
  }
  if (c.saturated) c.exact = ~(u128)0;
  return c;
}

std::vector<EC> Network::affected_ecs(const std::string &range) const {
  const std::vector<std::vector<Interval>> per_field = field_ranges(range);

  // An EC is one range per field: the cartesian product, first field
  // outermost, so the result is sorted.
  std::vector<EC> out;
  std::vector<size_t> pick(layout_.size(), 0);
  while (true) {
    EC ec;
    for (size_t f = 0; f < layout_.size(); ++f) ec.ranges.push_back(per_field[f][pick[f]]);
    out.push_back(ec);
    size_t f = layout_.size();
    while (f > 0) {
      --f;
      if (++pick[f] < per_field[f].size()) break;
      pick[f] = 0;
      if (f == 0) return out;
    }
    if (layout_.size() == 0) return out;
  }
}

std::string Network::point_of(const EC &ec) const {
  std::string s(layout_.width(), '0');
  for (size_t f = 0; f < layout_.size(); ++f) {
    const unsigned w = layout_.field(f).width, off = layout_.offset(f);
    for (unsigned b = 0; b < w; ++b)
      s[off + b] = (ec.ranges[f].lo >> (w - 1 - b)) & 1 ? '1' : '0';
  }
  return s;
}

ForwardingGraph Network::forwarding_graph(const EC &ec) const {
  if (ec.ranges.size() != layout_.size()) throw std::invalid_argument("EC arity");
  ForwardingGraph g;
  g.net_ = this;
  // The second trie traversal (T p.40): every rule containing the EC, including
  // those that did not help form it. Looking up one point suffices, because no
  // rule splits an EC: a rule overlapping it contains it.
  for (uint64_t id : trie_.find_overlapping(point_of(ec))) {
    const std::vector<Interval> &iv = intervals_.at(id);
    for (size_t f = 0; f < layout_.size(); ++f)
      if (iv[f].lo > ec.ranges[f].lo || iv[f].hi < ec.ranges[f].hi)
        throw std::logic_error("rule " + std::to_string(id) +
                               " splits the given EC: not an EC of this network");
    const Rule &r = rules_.at(id);
    g.candidates_[r.table].push_back(&r);
  }
  for (auto &entry : g.candidates_)
    std::sort(entry.second.begin(), entry.second.end(),
              [this](const Rule *a, const Rule *b) {
                if (a->priority != b->priority) return a->priority > b->priority;
                return seq_.at(a->id) < seq_.at(b->id);
              });
  return g;
}

// ---- forwarding graph ------------------------------------------------------

const Rule *ForwardingGraph::decide(uint32_t table, int64_t in_port) const {
  auto it = candidates_.find(table);
  if (it == candidates_.end()) return nullptr;
  for (const Rule *r : it->second)
    if (r->in_port == ANY_PORT || (in_port != ANY_PORT && r->in_port == in_port))
      return r;
  return nullptr;
}

std::vector<std::pair<uint32_t, int64_t>> ForwardingGraph::next_hops(
    uint32_t table, int64_t in_port) const {
  std::vector<std::pair<uint32_t, int64_t>> out;
  const Rule *r = decide(table, in_port);
  if (!r) return out;
  for (uint64_t p : r->out_ports)
    for (uint64_t to : net_->links_from(p))
      out.push_back({net_->port_table(to), (int64_t)to});
  return out;
}

std::vector<int64_t> ForwardingGraph::arrivals(uint32_t table) const {
  std::vector<int64_t> out = {ANY_PORT};
  for (uint64_t p : net_->table_ports(table)) out.push_back((int64_t)p);
  return out;
}

std::set<std::pair<uint32_t, uint32_t>> ForwardingGraph::table_edges() const {
  std::set<std::pair<uint32_t, uint32_t>> out;
  for (const auto &entry : candidates_)
    for (int64_t a : arrivals(entry.first))
      for (const auto &hop : next_hops(entry.first, a))
        out.insert({entry.first, hop.first});
  return out;
}

bool ForwardingGraph::path_revisits(uint32_t table, int64_t in_port,
                                    std::vector<uint32_t> &path) const {
  if (std::find(path.begin(), path.end(), table) != path.end()) return true;
  path.push_back(table);
  for (const auto &hop : next_hops(table, in_port))
    if (path_revisits(hop.first, hop.second, path)) return true;
  path.pop_back();
  return false;
}

bool ForwardingGraph::has_loop() const {
  // Q20: a loop is a path that revisits a TABLE, as NetPlumber's default
  // loop check has it. Every table is a possible start, from any arrival.
  for (const auto &entry : candidates_)
    for (int64_t a : arrivals(entry.first)) {
      std::vector<uint32_t> path;
      if (path_revisits(entry.first, a, path)) return true;
    }
  return false;
}

}  // namespace vf
