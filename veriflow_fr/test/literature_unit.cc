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
   The literature's own examples as tests: VERIFLOW_PLAN.md §8, catalogue
   L1-L6 (the V1 share). Each test names its source and derives its expected
   values in a comment. T = the thesis, DN = Delta-net (NSDI'17).
*/

#include <cppunit/TestFixture.h>
#include <cppunit/extensions/HelperMacros.h>

#include <stdexcept>

#include "../src/veriflow.h"
#include "test_util.h"

using namespace vf;
using vftest::ip;

class LiteratureTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(LiteratureTest);
  CPPUNIT_TEST(test_L1_thesis_11_8_example);
  CPPUNIT_TEST(test_L2_fig_3_2_is_not_minimal);
  CPPUNIT_TEST(test_L3_default_route_decides_but_does_not_split);
  CPPUNIT_TEST(test_L4_deltanet_fig1_forwarding_graphs);
  CPPUNIT_TEST(test_L5_prefix_to_interval);
  CPPUNIT_TEST(test_L6_trie_alg1_alg2);
  CPPUNIT_TEST(test_bulk_load_equals_insertion);
  CPPUNIT_TEST(test_L7_ecs_are_a_cartesian_product);
  CPPUNIT_TEST(test_ec_count_without_materialising);
  CPPUNIT_TEST_SUITE_END();

 public:
  // L1 -- T p.36. A switch holds 11.1.0.0/16 and 12.1.0.0/16; 11.0.0.0/8 is
  // inserted. Only the overlapping 11.1/16 is considered, 12.1/16 is not
  // ("the new rule will not affect packets outside the range 11.0.0.0/8"),
  // and the two produce three ECs. The thesis prints the third lower bound as
  // "11.2.255.255"; the partition requires 11.2.0.0 (§4.9). DEVIATION TEST:
  // it pins that correction.
  void test_L1_thesis_11_8_example() {
    Network net(Layout({{"dst", 32}}));
    vftest::one_table(net, 1, {10, 11, 12});
    net.add_rule(vftest::rule(1, 1, 16, ipv4_prefix("11.1.0.0/16"), {10}));
    net.add_rule(vftest::rule(2, 1, 16, ipv4_prefix("12.1.0.0/16"), {11}));
    std::vector<EC> ecs =
        net.add_rule(vftest::rule(3, 1, 8, ipv4_prefix("11.0.0.0/8"), {12}));

    CPPUNIT_ASSERT(net.overlapping_rules(ipv4_prefix("11.0.0.0/8")) ==
                   (std::vector<uint64_t>{1, 3}));
    std::vector<EC> expected = {
        {{{ip(11, 0, 0, 0), ip(11, 0, 255, 255)}}},
        {{{ip(11, 1, 0, 0), ip(11, 1, 255, 255)}}},
        {{{ip(11, 2, 0, 0), ip(11, 255, 255, 255)}}},
    };
    CPPUNIT_ASSERT(ecs == expected);
  }

  // L2 -- T Fig. 3.2, pp.37-38. Three nested rules on one field, A inside B
  // inside C, each strictly inside the next. Inserting C, the ranges no rule
  // splits are five, and "ECs 2 and 4 ... could have been combined into a
  // single EC": both lie in B but not A, so both are forwarded by B. The
  // figure has no values; ours, on 8 bits: A = 000101xx = [20,23],
  // B = 0001xxxx = [16,31], C = 00xxxxxx = [0,63]; priority A > B > C.
  // Expected ECs: [0,15] [16,19] [20,23] [24,31] [32,63] -- five, not the
  // minimal three.
  void test_L2_fig_3_2_is_not_minimal() {
    Network net(Layout({{"f", 8}}));
    vftest::one_table(net, 1, {10, 11, 12});
    net.add_rule(vftest::rule(1, 1, 3, "000101xx", {10}));  // A
    net.add_rule(vftest::rule(2, 1, 2, "0001xxxx", {11}));  // B
    std::vector<EC> ecs = net.add_rule(vftest::rule(3, 1, 1, "00xxxxxx", {12}));

    std::vector<EC> expected = {
        {{{0, 15}}}, {{{16, 19}}}, {{{20, 23}}}, {{{24, 31}}}, {{{32, 63}}}};
    CPPUNIT_ASSERT(ecs == expected);

    auto by = [&](size_t i) {
      return net.forwarding_graph(ecs[i]).decide(1, ANY_PORT)->id;
    };
    CPPUNIT_ASSERT_EQUAL((uint64_t)3, by(0));  // C
    CPPUNIT_ASSERT_EQUAL((uint64_t)2, by(1));  // B -- EC 2
    CPPUNIT_ASSERT_EQUAL((uint64_t)1, by(2));  // A
    CPPUNIT_ASSERT_EQUAL((uint64_t)2, by(3));  // B -- EC 4, same as EC 2
    CPPUNIT_ASSERT_EQUAL((uint64_t)3, by(4));  // C
  }

  // L3 -- T p.40. "For a new rule with 10.0.0.0/8 ... an existing 0.0.0.0/0
  // rule will not contribute to the generation of the affected ECs, but may
  // influence their forwarding behavior depending on its priority." So one
  // EC, the /8 itself, and the second trie traversal must find the /0: it
  // decides when its priority is higher, and the /8 decides otherwise.
  void test_L3_default_route_decides_but_does_not_split() {
    for (int default_wins = 0; default_wins < 2; ++default_wins) {
      Network net(Layout({{"dst", 32}}));
      vftest::one_table(net, 1, {10, 11});
      net.add_rule(vftest::rule(1, 1, default_wins ? 100 : 0,
                                ipv4_prefix("0.0.0.0/0"), {10}));
      std::vector<EC> ecs =
          net.add_rule(vftest::rule(2, 1, 8, ipv4_prefix("10.0.0.0/8"), {11}));

      std::vector<EC> expected = {{{{ip(10, 0, 0, 0), ip(10, 255, 255, 255)}}}};
      CPPUNIT_ASSERT(ecs == expected);
      const Rule *decides = net.forwarding_graph(ecs[0]).decide(1, ANY_PORT);
      CPPUNIT_ASSERT(decides != nullptr);
      CPPUNIT_ASSERT_EQUAL((uint64_t)(default_wins ? 1 : 2), decides->id);
    }
  }

  // L4 -- DN §2.1, Fig. 1: Delta-net's reading of VeriFlow. Switches s1..s4;
  // r1 s1->s2, r2 s2->s3, r3 s3->s4, all overlapping; r4 s1->s4 is inserted at
  // higher priority than r1. "Veriflow identifies at least three equivalence
  // classes"; in all three graphs "the edge ... from switch s1 to s2 is
  // excluded ... because on switch s1 ... the packet flow is determined by the
  // higher-priority rule r4". The figure is schematic; our nested prefixes on 4
  // bits are a recorded choice: r1 = [0,16), r4 = [8,16), r2 = [12,16),
  // r3 = [14,16). Inside r4's range the ECs are [8,11] (r1, r4), [12,13]
  // (+ r2) and [14,15] (+ r3), giving G1 = {s1->s4}, G2 = G1 + {s2->s3},
  // G3 = G2 + {s3->s4}. None has a loop.
  void test_L4_deltanet_fig1_forwarding_graphs() {
    Network net(Layout({{"dst", 4}}));
    for (uint32_t s = 1; s <= 4; ++s) net.add_table(s);
    // ports: s1 out 12 (to s2), 14 (to s4); s2 in 21, out 23; s3 in 31, out 34;
    // s4 in 41 (from s1), 43 (from s3)
    net.add_port(12, 1); net.add_port(14, 1);
    net.add_port(21, 2); net.add_port(23, 2);
    net.add_port(31, 3); net.add_port(34, 3);
    net.add_port(41, 4); net.add_port(43, 4);
    net.add_link(12, 21); net.add_link(14, 41);
    net.add_link(23, 31); net.add_link(34, 43);

    net.add_rule(vftest::rule(1, 1, 1, "xxxx", {12}));  // r1
    net.add_rule(vftest::rule(2, 2, 1, "11xx", {23}));  // r2
    net.add_rule(vftest::rule(3, 3, 1, "111x", {34}));  // r3
    std::vector<EC> ecs = net.add_rule(vftest::rule(4, 1, 2, "1xxx", {14}));

    std::vector<EC> expected = {{{{8, 11}}}, {{{12, 13}}}, {{{14, 15}}}};
    CPPUNIT_ASSERT(ecs == expected);

    typedef std::set<std::pair<uint32_t, uint32_t>> Edges;
    Edges g1 = {{1, 4}};
    Edges g2 = {{1, 4}, {2, 3}};
    Edges g3 = {{1, 4}, {2, 3}, {3, 4}};
    std::vector<Edges> graphs = {g1, g2, g3};
    for (size_t i = 0; i < ecs.size(); ++i) {
      ForwardingGraph g = net.forwarding_graph(ecs[i]);
      CPPUNIT_ASSERT(g.table_edges() == graphs[i]);
      CPPUNIT_ASSERT(g.table_edges().count({1, 2}) == 0);
      CPPUNIT_ASSERT(!g.has_loop());
    }
  }

  // L5 -- DN §2.1: "the IP prefix 0.0.0.10/31 ... corresponds to the
  // half-closed interval [10 : 12) = {10, 11}". Ours is closed: [10, 11].
  void test_L5_prefix_to_interval() {
    Interval i = prefix_to_interval(ipv4_prefix("0.0.0.10/31"));
    CPPUNIT_ASSERT(i == (Interval{10, 11}));
    CPPUNIT_ASSERT(prefix_to_interval("xxxx") == (Interval{0, 15}));
    CPPUNIT_ASSERT(prefix_to_interval("0101") == (Interval{5, 5}));
    // A ternary value that is not a prefix is no interval, and is refused.
    CPPUNIT_ASSERT_THROW(prefix_to_interval("x1x0"), std::invalid_argument);
  }

  // L6 -- T Alg. 1 and 2, pp.38-39, on a 2-bit trie holding a = 0x, b = 1x,
  // c = xx, d = 01. Alg. 1 follows the rule's bits, a wildcard down the
  // wildcard branch: inserting "0x" into an empty trie makes the root, its
  // '0' child and that node's 'x' child -- 3 nodes. Alg. 2: a concrete bit
  // visits its own branch and '*'; a '*' visits all three.
  void test_L6_trie_alg1_alg2() {
    TernaryTrie trie(2);
    trie.insert(1, "0x");
    CPPUNIT_ASSERT_EQUAL((size_t)3, trie.node_count());
    trie.insert(2, "1x");
    trie.insert(3, "xx");
    trie.insert(4, "01");

    typedef std::vector<uint64_t> Ids;
    CPPUNIT_ASSERT(trie.find_overlapping("00") == (Ids{1, 3}));
    CPPUNIT_ASSERT(trie.find_overlapping("xx") == (Ids{1, 2, 3, 4}));
    CPPUNIT_ASSERT(trie.find_overlapping("1x") == (Ids{2, 3}));
    CPPUNIT_ASSERT(trie.find_overlapping("x1") == (Ids{1, 2, 3, 4}));
    CPPUNIT_ASSERT(trie.find_overlapping("01") == (Ids{1, 3, 4}));

    CPPUNIT_ASSERT(trie.remove(4, "01"));
    CPPUNIT_ASSERT(trie.find_overlapping("01") == (Ids{1, 3}));
    CPPUNIT_ASSERT(!trie.remove(4, "01"));
  }

  // Bulk mode loads rules without verifying each insertion. What it loads must
  // be what insertion would have built: L1's network, loaded, gives L1's ECs.
  void test_bulk_load_equals_insertion() {
    Network net(Layout({{"dst", 32}}));
    vftest::one_table(net, 1, {10, 11, 12});
    net.load_rule(vftest::rule(1, 1, 16, ipv4_prefix("11.1.0.0/16"), {10}));
    net.load_rule(vftest::rule(2, 1, 16, ipv4_prefix("12.1.0.0/16"), {11}));
    net.load_rule(vftest::rule(3, 1, 8, ipv4_prefix("11.0.0.0/8"), {12}));
    CPPUNIT_ASSERT_EQUAL((size_t)3, net.affected_ecs(ipv4_prefix("11.0.0.0/8")).size());
    CPPUNIT_ASSERT(net.overlapping_rules(ipv4_prefix("11.0.0.0/8")) ==
                   (std::vector<uint64_t>{1, 3}));
  }

  // L7 -- T p.37, DERIVED (the thesis has no multi-field example): "For each
  // field, we find a set of disjoint ranges ... An EC is then defined by a
  // particular choice of one of the ranges for each of the fields." Two 4-bit
  // fields, src then dst. Existing rules: src 01xx (any dst), and dst 1xxx (any
  // src). Inserting the all-wildcard rule, src splits into [0,3] [4,7] [8,15]
  // and dst into [0,7] [8,15]: 3 x 2 = 6 ECs, first field outermost. It is
  // not minimal: [0,3]x* and [8,15]x* forward alike.
  void test_L7_ecs_are_a_cartesian_product() {
    Network net(Layout({{"src", 4}, {"dst", 4}}));
    vftest::one_table(net, 1, {10, 11, 12});
    net.add_rule(vftest::rule(1, 1, 2, "01xx" "xxxx", {10}));
    net.add_rule(vftest::rule(2, 1, 1, "xxxx" "1xxx", {11}));
    std::vector<EC> ecs = net.add_rule(vftest::rule(3, 1, 0, "xxxxxxxx", {12}));
    std::vector<EC> expected;
    for (Interval s : {Interval{0, 3}, Interval{4, 7}, Interval{8, 15}})
      for (Interval d : {Interval{0, 7}, Interval{8, 15}})
        expected.push_back({{s, d}});
    CPPUNIT_ASSERT(ecs == expected);
    CPPUNIT_ASSERT_EQUAL((uint64_t)1, net.forwarding_graph(ecs[2]).decide(1, ANY_PORT)->id);
    CPPUNIT_ASSERT_EQUAL((uint64_t)2, net.forwarding_graph(ecs[1]).decide(1, ANY_PORT)->id);
    CPPUNIT_ASSERT_EQUAL((uint64_t)3, net.forwarding_graph(ecs[0]).decide(1, ANY_PORT)->id);
  }

  // Counting ECs must not require building them: on a multi-field workload the
  // product runs far past memory (APKeep's Table 3: Delta-netMF, 15 million on
  // Stanford). ec_count() is the product of the per-field range counts --
  // L7's 3 x 2 -- and saturates rather than wrapping.
  void test_ec_count_without_materialising() {
    Network net(Layout({{"src", 4}, {"dst", 4}}));
    vftest::one_table(net, 1, {10});
    net.add_rule(vftest::rule(1, 1, 2, "01xx" "xxxx", {10}));
    net.add_rule(vftest::rule(2, 1, 1, "xxxx" "1xxx", {10}));
    ECCount c = net.ec_count("xxxxxxxx");
    CPPUNIT_ASSERT(!c.saturated);
    CPPUNIT_ASSERT(c.exact == 6);
    CPPUNIT_ASSERT_EQUAL((size_t)3, c.per_field[0]);
    CPPUNIT_ASSERT_EQUAL((size_t)2, c.per_field[1]);
    CPPUNIT_ASSERT_DOUBLES_EQUAL(6.0, c.approx, 1e-9);

    // Saturation, cheaply: 81 two-bit fields, each cut into three ranges by
    // "0x" and "00" -- [0,0] [1,1] [2,3]. 3^81 = 4.4e38 exceeds 2^128 = 3.4e38.
    std::vector<Field> fields;
    for (int f = 0; f < 81; ++f) fields.push_back({"f" + std::to_string(f), 2});
    Network big{Layout(fields)};
    vftest::one_table(big, 1, {10});
    const std::string all(162, 'x');
    uint64_t id = 1;
    for (int f = 0; f < 81; ++f)
      for (const char *v : {"0x", "00"}) {
        std::string m = all;
        m[2 * f] = v[0];
        m[2 * f + 1] = v[1];
        big.load_rule(vftest::rule(id++, 1, 0, m, {10}));
      }
    ECCount b = big.ec_count(all);
    CPPUNIT_ASSERT(b.saturated);
    CPPUNIT_ASSERT_EQUAL((size_t)3, b.per_field[80]);
    CPPUNIT_ASSERT_DOUBLES_EQUAL(4.434e38, b.approx, 1e36);
  }
};

CPPUNIT_TEST_SUITE_REGISTRATION(LiteratureTest);
