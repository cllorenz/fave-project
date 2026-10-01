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
   The concrete-packet oracle (VERIFLOW_PLAN.md §8, rule 3; D3 condition 5).

   At small header widths every packet can be enumerated. The oracle decides
   each one at each table by a LINEAR SCAN over the rules -- no trie, no
   interval, nothing the engine uses -- and then checks the engine against the
   thesis's own definition of an EC (T p.36): "for any p1, p2 in P and any
   network device R, the forwarding action is identical for p1 and p2 at R".

   It checks, for every insertion:
     * the ECs are disjoint and cover exactly the new rule's range (Q15);
     * each EC is action-uniform, and the engine's forwarding graph names the
       same deciding rule the oracle finds for every packet in it.
*/

#include <cppunit/TestFixture.h>
#include <cppunit/extensions/HelperMacros.h>

#include <map>
#include <random>
#include <sstream>

#include "../src/veriflow.h"
#include "test_util.h"

using namespace vf;

namespace {

// Does concrete packet `bits` (only '0'/'1') match ternary `match`?
bool matches(const std::string &match, const std::string &bits) {
  for (size_t i = 0; i < bits.size(); ++i)
    if (match[i] != 'x' && match[i] != bits[i]) return false;
  return true;
}

std::string to_bits(unsigned long value, unsigned width) {
  std::string s(width, '0');
  for (unsigned i = 0; i < width; ++i)
    if (value & (1ul << (width - 1 - i))) s[i] = '1';
  return s;
}

// The per-field value of a packet, from its bits.
std::vector<u128> field_values(const Layout &layout, const std::string &bits) {
  std::vector<u128> out;
  for (size_t f = 0; f < layout.size(); ++f) {
    u128 v = 0;
    for (unsigned b = 0; b < layout.field(f).width; ++b)
      v = (v << 1) | (bits[layout.offset(f) + b] == '1');
    out.push_back(v);
  }
  return out;
}

// The oracle's rule store: kept separately, in insertion order.
struct Oracle {
  std::vector<Rule> rules;

  // The deciding rule id at `table` for arrival `in_port`, 0 for none:
  // highest priority, a tie to the earlier insertion.
  uint64_t decide(uint32_t table, int64_t in_port, const std::string &bits) const {
    const Rule *best = nullptr;
    for (const Rule &r : rules) {
      if (r.table != table || !matches(r.match, bits)) continue;
      if (r.in_port != ANY_PORT && r.in_port != in_port) continue;
      if (!best || r.priority > best->priority) best = &r;
    }
    return best ? best->id : 0;
  }
};

// Check one insertion's ECs against the oracle.
void check(const Network &net, const Oracle &oracle, const Rule &inserted,
           const std::vector<EC> &ecs, const std::vector<uint32_t> &tables,
           const std::vector<int64_t> &arrivals) {
  const Layout &layout = net.layout();
  const unsigned width = layout.width();
  std::map<unsigned long, int> covered;  // packet -> times covered

  for (const EC &ec : ecs) {
    ForwardingGraph g = net.forwarding_graph(ec);
    for (unsigned long p = 0; p < (1ul << width); ++p) {
      std::string bits = to_bits(p, width);
      std::vector<u128> vals = field_values(layout, bits);
      bool inside = true;
      for (size_t f = 0; f < layout.size(); ++f)
        if (vals[f] < ec.ranges[f].lo || vals[f] > ec.ranges[f].hi) inside = false;
      if (!inside) continue;
      covered[p]++;
      for (uint32_t t : tables)
        for (int64_t a : arrivals) {
          const Rule *r = g.decide(t, a);
          uint64_t got = r ? r->id : 0;
          uint64_t want = oracle.decide(t, a, bits);
          if (got != want) {
            std::ostringstream msg;
            msg << "packet " << bits << " table " << t << " arrival " << a
                << ": engine " << got << ", oracle " << want;
            CPPUNIT_FAIL(msg.str());
          }
        }
    }
  }
  // Counting agrees with building.
  ECCount count = net.ec_count(inserted.match);
  CPPUNIT_ASSERT(!count.saturated);
  CPPUNIT_ASSERT(count.exact == (u128)ecs.size());
  // The ECs partition exactly the new rule's range.
  for (unsigned long p = 0; p < (1ul << width); ++p) {
    bool in_rule = matches(inserted.match, to_bits(p, width));
    int times = covered.count(p) ? covered[p] : 0;
    CPPUNIT_ASSERT_EQUAL(in_rule ? 1 : 0, times);
  }
}

std::string random_prefix(std::mt19937 &rng, unsigned width) {
  std::uniform_int_distribution<unsigned> len(0, width);
  unsigned l = len(rng);
  std::string s(width, 'x');
  for (unsigned i = 0; i < l; ++i) s[i] = (rng() & 1) ? '1' : '0';
  return s;
}

}  // namespace

class OracleTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(OracleTest);
  CPPUNIT_TEST(test_L2_against_the_oracle);
  CPPUNIT_TEST(test_L4_against_the_oracle);
  CPPUNIT_TEST(test_random_single_field);
  CPPUNIT_TEST(test_random_two_fields_with_in_ports);
  CPPUNIT_TEST_SUITE_END();

 public:
  // The L2 values, re-checked exhaustively.
  void test_L2_against_the_oracle() {
    Network net(Layout({{"f", 8}}));
    vftest::one_table(net, 1, {10, 11, 12});
    Oracle oracle;
    std::vector<Rule> rs = {vftest::rule(1, 1, 3, "000101xx", {10}),
                            vftest::rule(2, 1, 2, "0001xxxx", {11}),
                            vftest::rule(3, 1, 1, "00xxxxxx", {12})};
    for (const Rule &r : rs) {
      oracle.rules.push_back(r);
      check(net, oracle, r, net.add_rule(r), {1}, {ANY_PORT});
    }
  }

  // The L4 values, re-checked exhaustively at every table.
  void test_L4_against_the_oracle() {
    Network net(Layout({{"dst", 4}}));
    for (uint32_t s = 1; s <= 4; ++s) net.add_table(s);
    net.add_port(12, 1); net.add_port(14, 1); net.add_port(21, 2);
    net.add_port(23, 2); net.add_port(31, 3); net.add_port(34, 3);
    net.add_port(41, 4); net.add_port(43, 4);
    Oracle oracle;
    std::vector<Rule> rs = {vftest::rule(1, 1, 1, "xxxx", {12}),
                            vftest::rule(2, 2, 1, "11xx", {23}),
                            vftest::rule(3, 3, 1, "111x", {34}),
                            vftest::rule(4, 1, 2, "1xxx", {14})};
    for (const Rule &r : rs) {
      oracle.rules.push_back(r);
      check(net, oracle, r, net.add_rule(r), {1, 2, 3, 4}, {ANY_PORT});
    }
  }

  // Random prefix rules on one 6-bit field over three tables, priorities
  // drawn with ties (which go to the earlier insertion).
  void test_random_single_field() {
    std::mt19937 rng(20260929);
    for (int trial = 0; trial < 20; ++trial) {
      Network net(Layout({{"f", 6}}));
      for (uint32_t t = 1; t <= 3; ++t) vftest::one_table(net, t, {t * 10});
      Oracle oracle;
      for (uint64_t id = 1; id <= 25; ++id) {
        Rule r = vftest::rule(id, 1 + rng() % 3, rng() % 5,
                              random_prefix(rng, 6), {(1 + rng() % 3) * 10});
        oracle.rules.push_back(r);
        check(net, oracle, r, net.add_rule(r), {1, 2, 3}, {ANY_PORT});
      }
    }
  }

  // Two fields of 3 bits (the cartesian product of T p.37), and rules
  // qualified by an ingress port (Q7): each is decided per arrival port.
  void test_random_two_fields_with_in_ports() {
    std::mt19937 rng(7);
    for (int trial = 0; trial < 20; ++trial) {
      Network net(Layout({{"a", 3}, {"b", 3}}));
      vftest::one_table(net, 1, {1, 2, 3});
      vftest::one_table(net, 2, {4, 5});
      Oracle oracle;
      const std::vector<std::vector<int64_t>> own = {{1, 2, 3}, {4, 5}};
      for (uint64_t id = 1; id <= 25; ++id) {
        uint32_t table = 1 + rng() % 2;
        const std::vector<int64_t> &ports = own[table - 1];
        // An ingress port must be one of the rule's own table's ports.
        int64_t in_port =
            (rng() % 3 == 0) ? ANY_PORT : ports[rng() % ports.size()];
        Rule r = vftest::rule(id, table, rng() % 4,
                              random_prefix(rng, 3) + random_prefix(rng, 3),
                              {1 + rng() % 5}, in_port);
        oracle.rules.push_back(r);
        check(net, oracle, r, net.add_rule(r), {1, 2},
              {ANY_PORT, 1, 2, 3, 4, 5});
      }
    }
  }
};

CPPUNIT_TEST_SUITE_REGISTRATION(OracleTest);
