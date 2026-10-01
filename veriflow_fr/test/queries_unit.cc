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
   L10, V1's share: the invariants of T Ch. 4 (§4.1-4.4, 4.6-4.10). The thesis
   describes each in prose without an example network, so every network here
   is DERIVED -- the smallest one that makes the invariant's two answers differ
   -- and its expected outcome is worked out in the comment. One 8-bit
   destination field throughout; "0xxxxxxx" is [0,127], and so on.

   Port numbering: port TP is port P of table T, e.g. 12 is table 1's port 2.
*/

#include <cppunit/TestFixture.h>
#include <cppunit/extensions/HelperMacros.h>

#include "../src/queries.h"
#include "../src/veriflow.h"
#include "test_util.h"

using namespace vf;

namespace {

Network net8() { return Network(Layout({{"dst", 8}})); }

void tables(Network &net, std::vector<std::pair<uint32_t, std::vector<uint64_t>>> spec) {
  for (auto &t : spec) vftest::one_table(net, t.first, t.second);
}

Rule consume(uint64_t id, uint32_t table, const std::string &match) {
  Rule r = vftest::rule(id, table, 0, match, {});
  r.consume = true;
  return r;
}

// Walk the EC of `range` (which must be one EC) from table `from`.
std::vector<Outcome> walk_ec(const Network &net, const std::string &range,
                             uint32_t from, int64_t in_port = ANY_PORT) {
  std::vector<EC> ecs = net.affected_ecs(range);
  CPPUNIT_ASSERT_EQUAL((size_t)1, ecs.size());
  return walk(net.forwarding_graph(ecs[0]), from, in_port);
}

typedef std::vector<uint32_t> Path;

}  // namespace

class QueriesTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(QueriesTest);
  CPPUNIT_TEST(test_L10_4_1_reachability);
  CPPUNIT_TEST(test_L10_4_2_loop_freeness);
  CPPUNIT_TEST(test_L10_4_3_black_holes_three_causes);
  CPPUNIT_TEST(test_L10_4_3_unwired_port);
  CPPUNIT_TEST(test_L10_4_4_consistency);
  CPPUNIT_TEST(test_L10_4_6_4_7_loose_and_strict_path);
  CPPUNIT_TEST(test_L10_4_7_firewall_before_the_lan);
  CPPUNIT_TEST(test_L10_4_8_path_length);
  CPPUNIT_TEST(test_L10_4_9_overlapping_rules);
  CPPUNIT_TEST(test_L10_4_10_next_hop_change);
  CPPUNIT_TEST(test_Q21_deliveries_per_start);
  CPPUNIT_TEST(test_link_failure_on_L4);
  CPPUNIT_TEST(test_L10_V2_multi_field_acl_black_holes);
  CPPUNIT_TEST(test_L10_V2_multi_field_overlaps);
  CPPUNIT_TEST(test_link_failure_respects_the_ingress_port);
  CPPUNIT_TEST_SUITE_END();

 public:
  // T §4.1, derived. s1 -> s2 -> probe P. s1 forwards everything, s2 only
  // [0,127], P consumes all. [0,127] is delivered at P via 1, 2, 3; [128,255]
  // matches nothing at s2.
  void test_L10_4_1_reachability() {
    Network net = net8();
    tables(net, {{1, {11}}, {2, {21, 22}}, {3, {31}}});
    net.add_link(11, 21);
    net.add_link(22, 31);
    net.add_rule(vftest::rule(1, 1, 0, "xxxxxxxx", {11}));
    net.add_rule(vftest::rule(2, 2, 0, "0xxxxxxx", {22}));
    net.add_rule(consume(3, 3, "xxxxxxxx"));

    std::vector<Outcome> low = walk_ec(net, "0xxxxxxx", 1);
    CPPUNIT_ASSERT(reaches(low, 3));
    CPPUNIT_ASSERT_EQUAL((size_t)1, low.size());
    CPPUNIT_ASSERT(low[0].end == End::DELIVERED);
    CPPUNIT_ASSERT(low[0].path == (Path{1, 2, 3}));

    std::vector<Outcome> high = walk_ec(net, "1xxxxxxx", 1);
    CPPUNIT_ASSERT(!reaches(high, 3));
    CPPUNIT_ASSERT(high[0].end == End::NO_MATCH);
    CPPUNIT_ASSERT_EQUAL((uint32_t)2, high[0].table);
  }

  // T §4.2, derived. s2 sends [128,255] back to s1, which forwards
  // everything to s2: the path 1, 2, 1 revisits table 1.
  void test_L10_4_2_loop_freeness() {
    Network net = net8();
    tables(net, {{1, {11, 12}}, {2, {21, 22, 23}}, {3, {31}}});
    net.add_link(11, 21);
    net.add_link(22, 12);
    net.add_link(23, 31);
    net.add_rule(vftest::rule(1, 1, 0, "xxxxxxxx", {11}));
    net.add_rule(vftest::rule(2, 2, 0, "1xxxxxxx", {22}));
    net.add_rule(vftest::rule(3, 2, 0, "0xxxxxxx", {23}));
    net.add_rule(consume(4, 3, "xxxxxxxx"));

    std::vector<Outcome> high = walk_ec(net, "1xxxxxxx", 1);
    CPPUNIT_ASSERT(!loop_free(high));
    CPPUNIT_ASSERT(high[0].end == End::LOOP);
    CPPUNIT_ASSERT(high[0].path == (Path{1, 2, 1}));
    CPPUNIT_ASSERT(loop_free(walk_ec(net, "0xxxxxxx", 1)));
  }

  // T §4.3, derived: its three causes. Router 1 routes [0,127] to ACL 2 and
  // has no default route. ACL 2 denies [0,31], permits [32,63], and has no
  // final permit. So: [0,31] explicit drop at 2; [32,63] delivered; [64,127]
  // no match at 2 (the missing permit); [128,255] no match at 1 (the missing
  // default route, with no rule to name).
  void test_L10_4_3_black_holes_three_causes() {
    Network net = net8();
    tables(net, {{1, {11}}, {2, {21, 22}}, {3, {31}}});
    net.add_link(11, 21);
    net.add_link(22, 31);
    net.add_rule(vftest::rule(1, 1, 0, "0xxxxxxx", {11}));
    net.add_rule(vftest::rule(2, 2, 2, "000xxxxx", {}));    // deny
    net.add_rule(vftest::rule(3, 2, 1, "001xxxxx", {22}));  // permit
    net.add_rule(consume(4, 3, "xxxxxxxx"));

    std::vector<Outcome> deny = black_holes(walk_ec(net, "000xxxxx", 1));
    CPPUNIT_ASSERT_EQUAL((size_t)1, deny.size());
    CPPUNIT_ASSERT(deny[0].end == End::DROP_RULE);
    CPPUNIT_ASSERT_EQUAL((uint32_t)2, deny[0].table);
    CPPUNIT_ASSERT_EQUAL((uint64_t)2, deny[0].rule);

    CPPUNIT_ASSERT(black_holes(walk_ec(net, "001xxxxx", 1)).empty());

    std::vector<Outcome> no_permit = black_holes(walk_ec(net, "01xxxxxx", 1));
    CPPUNIT_ASSERT(no_permit[0].end == End::NO_MATCH);
    CPPUNIT_ASSERT_EQUAL((uint32_t)2, no_permit[0].table);

    std::vector<Outcome> no_route = black_holes(walk_ec(net, "1xxxxxxx", 1));
    CPPUNIT_ASSERT(no_route[0].end == End::NO_MATCH);
    CPPUNIT_ASSERT_EQUAL((uint32_t)1, no_route[0].table);
    CPPUNIT_ASSERT_EQUAL((uint64_t)0, no_route[0].rule);
  }

  // Q8's fourth way to lose a packet, FaVe's: forwarding to an unwired port.
  void test_L10_4_3_unwired_port() {
    Network net = net8();
    tables(net, {{1, {11}}});
    net.add_rule(vftest::rule(1, 1, 0, "xxxxxxxx", {11}));
    std::vector<Outcome> bh = black_holes(walk_ec(net, "xxxxxxxx", 1));
    CPPUNIT_ASSERT_EQUAL((size_t)1, bh.size());
    CPPUNIT_ASSERT(bh[0].end == End::UNWIRED);
    CPPUNIT_ASSERT_EQUAL((uint64_t)1, bh[0].rule);
  }

  // T §4.4, derived. Replicated routers 2 and 3 both forward to probe 4; router
  // 3 lacks the route for [128,255]. Consistent on [0,127], not on [128,255].
  void test_L10_4_4_consistency() {
    Network net = net8();
    tables(net, {{2, {21}}, {3, {31}}, {4, {41, 42}}});
    net.add_link(21, 41);
    net.add_link(31, 42);
    net.add_rule(vftest::rule(1, 2, 0, "xxxxxxxx", {21}));
    net.add_rule(vftest::rule(2, 3, 0, "0xxxxxxx", {31}));
    net.add_rule(consume(3, 4, "xxxxxxxx"));

    CPPUNIT_ASSERT(consistent(walk_ec(net, "0xxxxxxx", 2),
                              walk_ec(net, "0xxxxxxx", 3)));
    CPPUNIT_ASSERT(!consistent(walk_ec(net, "1xxxxxxx", 2),
                               walk_ec(net, "1xxxxxxx", 3)));
  }

  // T §4.6 and 4.7, derived. The path is 1, 3 (monitor M2), 2 (monitor M1),
  // 4 (probe). It visits both monitors -- loose path holds -- but M2 first,
  // so the strict path M1 then M2 does not; M2 then M1 does.
  void test_L10_4_6_4_7_loose_and_strict_path() {
    Network net = net8();
    tables(net, {{1, {11}}, {2, {21, 22}}, {3, {31, 32}}, {4, {41}}});
    net.add_link(11, 31);
    net.add_link(32, 21);
    net.add_link(22, 41);
    net.add_rule(vftest::rule(1, 1, 0, "xxxxxxxx", {11}));
    net.add_rule(vftest::rule(2, 3, 0, "xxxxxxxx", {32}));
    net.add_rule(vftest::rule(3, 2, 0, "xxxxxxxx", {22}));
    net.add_rule(consume(4, 4, "xxxxxxxx"));

    std::vector<Outcome> w = walk_ec(net, "xxxxxxxx", 1);
    CPPUNIT_ASSERT(loose_path(w, {2, 3}));
    CPPUNIT_ASSERT(!strict_path(w, {2, 3}));
    CPPUNIT_ASSERT(strict_path(w, {3, 2}));
  }

  // T §4.7's own example, derived network: "packets from the Internet always
  // visit the firewall before entering the local network". Internet 1 sends
  // [0,127] through firewall 2 to LAN 3, but [128,255] straight to the LAN.
  void test_L10_4_7_firewall_before_the_lan() {
    Network net = net8();
    tables(net, {{1, {11, 12}}, {2, {21, 22}}, {3, {31, 32}}});
    net.add_link(11, 21);
    net.add_link(22, 31);
    net.add_link(12, 32);
    net.add_rule(vftest::rule(1, 1, 0, "0xxxxxxx", {11}));
    net.add_rule(vftest::rule(2, 1, 0, "1xxxxxxx", {12}));
    net.add_rule(vftest::rule(3, 2, 0, "xxxxxxxx", {22}));
    net.add_rule(consume(4, 3, "xxxxxxxx"));

    CPPUNIT_ASSERT(strict_path(walk_ec(net, "0xxxxxxx", 1), {2, 3}));
    CPPUNIT_ASSERT(!strict_path(walk_ec(net, "1xxxxxxx", 1), {2, 3}));
  }

  // T §4.8, derived. Path 1, 2, 3 is two hops.
  void test_L10_4_8_path_length() {
    Network net = net8();
    tables(net, {{1, {11}}, {2, {21, 22}}, {3, {31}}});
    net.add_link(11, 21);
    net.add_link(22, 31);
    net.add_rule(vftest::rule(1, 1, 0, "xxxxxxxx", {11}));
    net.add_rule(vftest::rule(2, 2, 0, "xxxxxxxx", {22}));
    net.add_rule(consume(3, 3, "xxxxxxxx"));

    std::vector<Outcome> w = walk_ec(net, "xxxxxxxx", 1);
    CPPUNIT_ASSERT(path_length_within(w, 2));
    CPPUNIT_ASSERT(!path_length_within(w, 1));
  }

  // T §4.9, derived. Table 1 holds [0,127] and [128,255]; table 2 holds
  // everything. A new [64,127] at table 1 competes with [0,127] only -- not
  // with [128,255], which it does not overlap, nor with table 2's rule.
  void test_L10_4_9_overlapping_rules() {
    Network net = net8();
    tables(net, {{1, {11}}, {2, {21}}});
    net.add_rule(vftest::rule(1, 1, 0, "0xxxxxxx", {11}));
    net.add_rule(vftest::rule(2, 1, 0, "1xxxxxxx", {11}));
    net.add_rule(vftest::rule(3, 2, 0, "xxxxxxxx", {21}));
    Rule fresh = vftest::rule(9, 1, 1, "01xxxxxx", {11});
    CPPUNIT_ASSERT(overlapping_in_table(net, fresh) == (std::vector<uint64_t>{1}));
  }

  // T §4.10, derived. Table 1 sends [0,127] out of port 11. A new [64,127]
  // rule at higher priority out of port 12 changes the next hop of [64,127];
  // the same rule out of port 11, or at lower priority, changes nothing. The
  // network is left as it was.
  void test_L10_4_10_next_hop_change() {
    Network net = net8();
    tables(net, {{1, {11, 12}}, {2, {21}}, {3, {31}}});
    net.add_link(11, 21);
    net.add_link(12, 31);
    net.add_rule(vftest::rule(1, 1, 1, "0xxxxxxx", {11}));

    std::vector<EC> moved = next_hop_changes(net, vftest::rule(9, 1, 2, "01xxxxxx", {12}));
    CPPUNIT_ASSERT(moved == (std::vector<EC>{{{{64, 127}}}}));
    CPPUNIT_ASSERT(next_hop_changes(net, vftest::rule(9, 1, 2, "01xxxxxx", {11})).empty());
    CPPUNIT_ASSERT(next_hop_changes(net, vftest::rule(9, 1, 0, "01xxxxxx", {12})).empty());
    CPPUNIT_ASSERT(net.overlapping_rules("xxxxxxxx") == (std::vector<uint64_t>{1}));
  }

  // Q21, derived. Two sources: 1 forwards everything to router 3; 2 forwards
  // only [0,127] there. Router 3 delivers [0,127] at probe 4 and [128,255] at
  // probe 5. For the query set "everything", source 1's packets are delivered
  // at 4 and 5, source 2's at 4 only; for [128,255], source 2 reaches none.
  void test_Q21_deliveries_per_start() {
    Network net = net8();
    tables(net, {{1, {11}}, {2, {21}}, {3, {31, 32, 33, 34}}, {4, {41}}, {5, {51}}});
    net.add_link(11, 31);
    net.add_link(21, 32);
    net.add_link(33, 41);
    net.add_link(34, 51);
    net.add_rule(vftest::rule(1, 1, 0, "xxxxxxxx", {11}));
    net.add_rule(vftest::rule(2, 2, 0, "0xxxxxxx", {21}));
    net.add_rule(vftest::rule(3, 3, 0, "0xxxxxxx", {33}));
    net.add_rule(vftest::rule(4, 3, 0, "1xxxxxxx", {34}));
    net.add_rule(consume(5, 4, "xxxxxxxx"));
    net.add_rule(consume(6, 5, "xxxxxxxx"));

    std::vector<std::pair<uint32_t, int64_t>> starts = {{1, ANY_PORT}, {2, ANY_PORT}};
    std::vector<std::set<uint32_t>> all = deliveries(net, "xxxxxxxx", starts);
    CPPUNIT_ASSERT(all[0] == (std::set<uint32_t>{4, 5}));
    CPPUNIT_ASSERT(all[1] == (std::set<uint32_t>{4}));
    std::vector<std::set<uint32_t>> high = deliveries(net, "1xxxxxxx", starts);
    CPPUNIT_ASSERT(high[0] == (std::set<uint32_t>{5}));
    CPPUNIT_ASSERT(high[1].empty());
  }

  // DN §4.3.2 on L4's network, derived. Failing s1 -> s4 (port 14 into 41)
  // hits the three ECs r4 decides, [8,11] [12,13] [14,15]. Failing s1 -> s2
  // (12 into 21) hits only [0,7]: r1 forwards there, but on [8,15] r4 wins.
  void test_link_failure_on_L4() {
    Network net(Layout({{"dst", 4}}));
    for (uint32_t s = 1; s <= 4; ++s) net.add_table(s);
    net.add_port(12, 1); net.add_port(14, 1);
    net.add_port(21, 2); net.add_port(23, 2);
    net.add_port(31, 3); net.add_port(34, 3);
    net.add_port(41, 4); net.add_port(43, 4);
    net.add_link(12, 21); net.add_link(14, 41);
    net.add_link(23, 31); net.add_link(34, 43);
    net.add_rule(vftest::rule(1, 1, 1, "xxxx", {12}));
    net.add_rule(vftest::rule(2, 2, 1, "11xx", {23}));
    net.add_rule(vftest::rule(3, 3, 1, "111x", {34}));
    net.add_rule(vftest::rule(4, 1, 2, "1xxx", {14}));

    size_t graphs = 0;
    std::vector<EC> via_s4 = link_failure(net, 1, ANY_PORT, 41, &graphs);
    CPPUNIT_ASSERT(via_s4 == (std::vector<EC>{{{{8, 11}}}, {{{12, 13}}}, {{{14, 15}}}}));
    CPPUNIT_ASSERT(graphs >= via_s4.size());
    CPPUNIT_ASSERT(link_failure(net, 1, ANY_PORT, 21) == (std::vector<EC>{{{{0, 7}}}}));
    CPPUNIT_ASSERT(link_failure(net, 2, ANY_PORT, 41).empty());  // no such edge
  }

  // A failing edge is a NODE-level edge: at table 1, a rule for arrivals on
  // port 11 uses it, a rule for port 12 does not.
  void test_link_failure_respects_the_ingress_port() {
    Network net = net8();
    tables(net, {{1, {11, 12, 13, 14}}, {2, {21}}, {3, {31}}});
    net.add_link(13, 21);
    net.add_link(14, 31);
    net.add_rule(vftest::rule(1, 1, 0, "0xxxxxxx", {13}, 11));
    net.add_rule(vftest::rule(2, 1, 0, "0xxxxxxx", {14}, 12));
    CPPUNIT_ASSERT(link_failure(net, 1, 11, 21) == (std::vector<EC>{{{{0, 127}}}}));
    CPPUNIT_ASSERT(link_failure(net, 1, 12, 21).empty());
  }

  // L10, V2's share: T §4.3 with a MULTI-FIELD ACL, derived. Fields src, dst,
  // dport, 4 bits each. Router 1 sends everything to ACL 2, which denies
  // src 0xxx to dport 1010 and permits the rest to probe 3. Over the whole
  // space, an EC is black-holed (an explicit drop at 2) exactly when it lies in
  // the deny box, and is delivered otherwise.
  void test_L10_V2_multi_field_acl_black_holes() {
    Network net(Layout({{"src", 4}, {"dst", 4}, {"dport", 4}}));
    tables(net, {{1, {11}}, {2, {21, 22}}, {3, {31}}});
    net.add_link(11, 21);
    net.add_link(22, 31);
    net.add_rule(vftest::rule(1, 1, 0, "xxxxxxxxxxxx", {11}));
    net.add_rule(vftest::rule(2, 2, 1, "0xxx" "xxxx" "1010", {}));   // deny
    net.add_rule(vftest::rule(3, 2, 0, "xxxxxxxxxxxx", {22}));       // permit
    net.add_rule(consume(4, 3, "xxxxxxxxxxxx"));

    std::vector<EC> ecs = net.affected_ecs("xxxxxxxxxxxx");
    // src splits at 8, dport at 10 and 11: 2 x 1 x 3 ECs.
    CPPUNIT_ASSERT_EQUAL((size_t)6, ecs.size());
    size_t dropped = 0;
    for (const EC &ec : ecs) {
      const bool in_deny = ec.ranges[0].hi <= 7 && ec.ranges[2].lo == 10 &&
                           ec.ranges[2].hi == 10;
      std::vector<Outcome> w = walk(net.forwarding_graph(ec), 1, ANY_PORT);
      std::vector<Outcome> bh = black_holes(w);
      if (in_deny) {
        ++dropped;
        CPPUNIT_ASSERT_EQUAL((size_t)1, bh.size());
        CPPUNIT_ASSERT(bh[0].end == End::DROP_RULE);
        CPPUNIT_ASSERT_EQUAL((uint64_t)2, bh[0].rule);
      } else {
        CPPUNIT_ASSERT(bh.empty());
        CPPUNIT_ASSERT(reaches(w, 3));
      }
    }
    CPPUNIT_ASSERT_EQUAL((size_t)1, dropped);
  }

  // L10, V2's share: T §4.9 across fields, derived. A = (src 0xxx, any dst),
  // C = (src 1xxx, dst 0xxx). A new B = (any src, dst 1xxx) overlaps A in
  // the box src 0xxx x dst 1xxx, and misses C, whose dst is disjoint from its.
  void test_L10_V2_multi_field_overlaps() {
    Network net(Layout({{"src", 4}, {"dst", 4}}));
    tables(net, {{1, {11}}});
    net.add_rule(vftest::rule(1, 1, 0, "0xxx" "xxxx", {11}));  // A
    net.add_rule(vftest::rule(2, 1, 0, "1xxx" "0xxx", {11}));  // C
    Rule b = vftest::rule(9, 1, 1, "xxxx" "1xxx", {11});
    CPPUNIT_ASSERT(overlapping_in_table(net, b) == (std::vector<uint64_t>{1}));
  }
};

CPPUNIT_TEST_SUITE_REGISTRATION(QueriesTest);
