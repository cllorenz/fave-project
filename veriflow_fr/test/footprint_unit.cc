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
   The finer footprints of VERIFLOW_FOOTPRINT_SCOPE.md §4: a witness per
   delivered table (one path, one concrete packet per hop), and the fate of
   the packets a rule takes or a deleted rule hands on (dead ends). Each test
   runs both walks (plain and V3b) and both revisit rules where a walk is
   involved.
*/

#include <cppunit/TestFixture.h>
#include <cppunit/extensions/HelperMacros.h>

#include "../src/queries.h"
#include "../src/veriflow.h"
#include "test_util.h"

using namespace vf;

namespace {

Network net() { return Network(Layout({{"dst", 4}, {"dport", 4}})); }

Rule consume(uint64_t id, uint32_t table, const std::string &match) {
  Rule r = vftest::rule(id, table, 0, match, {});
  r.consume = true;
  return r;
}

// Two paths from table 1 to table 2: dst 0xxx directly (port 11 -> 21), and
// dst 1xxx through table 3 (port 12 -> 31, port 32 -> 22).
Network two_paths() {
  Network n = net();
  vftest::one_table(n, 1, {11, 12});
  vftest::one_table(n, 2, {21, 22});
  vftest::one_table(n, 3, {31, 32});
  n.add_link(11, 21);
  n.add_link(12, 31);
  n.add_link(32, 22);
  n.load_rule(vftest::rule(1, 1, 10, "0xxxxxxx", {11}));
  n.load_rule(vftest::rule(2, 1, 10, "1xxxxxxx", {12}));
  n.load_rule(vftest::rule(3, 3, 10, "xxxxxxxx", {32}));
  n.load_rule(consume(4, 2, "xxxxxxxx"));
  return n;
}

const std::vector<std::vector<bool>> WALKS = {{}, {false, true}};   // plain, V3b
const std::vector<Revisit> REVISITS = {Revisit::STATE, Revisit::PATH};

LocalResult walked(const Network &n, const std::vector<bool> &scan, Revisit rv) {
  LocalResult r = local_deliveries(n, "xxxxxxxx", {{1, ANY_PORT}}, 0, rv, scan,
                                   true, true);
  CPPUNIT_ASSERT(r.finished);
  return r;
}

}  // namespace

class FootprintTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(FootprintTest);
  CPPUNIT_TEST(test_a_witness_is_one_path_with_one_packet);
  CPPUNIT_TEST(test_only_a_rule_meeting_the_witness_packet_hits_it);
  CPPUNIT_TEST(test_the_packet_is_carried_back_through_a_rewrite);
  CPPUNIT_TEST(test_the_carried_packet_keeps_the_unrewritten_fields);
  CPPUNIT_TEST(test_a_witness_watches_the_ports_it_left_by);
  CPPUNIT_TEST(test_rule_fates);
  CPPUNIT_TEST(test_a_deleted_rule_hands_its_packets_to_the_rules_below);
  CPPUNIT_TEST(test_no_witness_without_asking);
  CPPUNIT_TEST_SUITE_END();

 public:
  void test_a_witness_is_one_path_with_one_packet() {
    Network n = two_paths();
    for (const auto &scan : WALKS)
      for (Revisit rv : REVISITS) {
        LocalResult r = walked(n, scan, rv);
        CPPUNIT_ASSERT_EQUAL((size_t)1, r.witnesses.size());
        CPPUNIT_ASSERT_EQUAL((size_t)1, r.witnesses[0].count(2));
        const Witness &w = r.witnesses[0].at(2);
        CPPUNIT_ASSERT(w.has_point);
        // the first path found: dst 0xxx, directly -- two hops, ending consumed
        CPPUNIT_ASSERT_EQUAL((size_t)2, w.hops.size());
        CPPUNIT_ASSERT_EQUAL((uint32_t)1, w.hops[0].table);
        CPPUNIT_ASSERT_EQUAL((uint64_t)1, w.hops[0].rule);
        CPPUNIT_ASSERT_EQUAL((int64_t)11, w.hops[0].port);
        CPPUNIT_ASSERT_EQUAL((uint32_t)2, w.hops[1].table);
        CPPUNIT_ASSERT_EQUAL((int64_t)-1, w.hops[1].port);
        // the packet is the lowest corner, the same on both hops (no rewrite)
        for (const Hop &h : w.hops) {
          CPPUNIT_ASSERT(h.point[0].lo == 0 && h.point[0].hi == 0);
          CPPUNIT_ASSERT(h.point[1].lo == 0 && h.point[1].hi == 0);
        }
      }
  }

  void test_only_a_rule_meeting_the_witness_packet_hits_it() {
    Network n = two_paths();
    for (const auto &scan : WALKS)
      for (Revisit rv : REVISITS) {
        LocalResult r = walked(n, scan, rv);
        const Witness &w = r.witnesses[0].at(2);
        // the other path's table: the explored footprint meets it, the witness not
        CPPUNIT_ASSERT(footprint_hits_rule(n, r.footprint, 3, ANY_PORT, "1xxxxxxx"));
        CPPUNIT_ASSERT(!witness_hits_rule(n, w, 3, ANY_PORT, "1xxxxxxx", true));
        CPPUNIT_ASSERT(!witness_hits_rule(n, w, 3, ANY_PORT, "1xxxxxxx", false));
        // dst 0100 meets the hop's set (0xxx) but not its packet (dst 0)
        CPPUNIT_ASSERT(!witness_hits_rule(n, w, 1, ANY_PORT, "0100xxxx", true));
        CPPUNIT_ASSERT(witness_hits_rule(n, w, 1, ANY_PORT, "0100xxxx", false));
        // dst 0000 meets the packet; so does the consuming table's own rule
        CPPUNIT_ASSERT(witness_hits_rule(n, w, 1, ANY_PORT, "0000xxxx", true));
        CPPUNIT_ASSERT(witness_hits_rule(n, w, 2, ANY_PORT, "xxxxxxxx", true));
        // a rule for another arrival port is no candidate at the hop... but the
        // start arrives on ANY_PORT, and the walk's own test admits no in-port
        // rule there either
        CPPUNIT_ASSERT(!witness_hits_rule(n, w, 1, 12, "0000xxxx", true));
        // arriving at table 2 on port 21: a rule for port 22 is no candidate
        CPPUNIT_ASSERT(!witness_hits_rule(n, w, 2, 22, "xxxxxxxx", true));
        CPPUNIT_ASSERT(witness_hits_rule(n, w, 2, 21, "xxxxxxxx", true));
      }
  }

  void test_the_packet_is_carried_back_through_a_rewrite() {
    // table 1 rewrites dport := 0101 and forwards to table 2, which consumes
    // only dport 0101
    for (const auto &scan : WALKS)
      for (Revisit rv : REVISITS) {
        Network n = net();
        vftest::one_table(n, 1, {11});
        vftest::one_table(n, 2, {21});
        n.add_link(11, 21);
        Rule rw = vftest::rule(1, 1, 10, "xxxxxxxx", {11});
        rw.rewrites.push_back({1, {5, 5}});
        n.load_rule(rw);
        n.load_rule(consume(2, 2, "xxxx0101"));
        LocalResult r = walked(n, scan, rv);
        const Witness &w = r.witnesses[0].at(2);
        CPPUNIT_ASSERT(w.has_point);
        // after the rewrite dport is 5; before it, any value of the set: 0
        CPPUNIT_ASSERT(w.hops[1].point[1].lo == 5);
        CPPUNIT_ASSERT(w.hops[0].point[1].lo == 0);
        CPPUNIT_ASSERT(w.hops[0].point[0].lo == w.hops[1].point[0].lo);
        // a rule at table 1 for pre-rewrite dport 5 does not take the witness
        // packet (dport 0) -- the path survives it
        CPPUNIT_ASSERT(!witness_hits_rule(n, w, 1, ANY_PORT, "xxxx0101", true));
        CPPUNIT_ASSERT(witness_hits_rule(n, w, 1, ANY_PORT, "xxxx0000", true));
      }
  }

  void test_the_carried_packet_keeps_the_unrewritten_fields() {
    // table 1 forwards everything (rewriting dport) to table 2, which
    // consumes only dst 0101: the delivered packet has dst 5, not the lowest
    // corner of table 1's set, and so must it have on table 1's hop
    for (const auto &scan : WALKS)
      for (Revisit rv : REVISITS) {
        Network n = net();
        vftest::one_table(n, 1, {11});
        vftest::one_table(n, 2, {21});
        n.add_link(11, 21);
        Rule rw = vftest::rule(1, 1, 10, "xxxxxxxx", {11});
        rw.rewrites.push_back({1, {3, 3}});
        n.load_rule(rw);
        n.load_rule(consume(2, 2, "0101xxxx"));
        LocalResult r = walked(n, scan, rv);
        const Witness &w = r.witnesses[0].at(2);
        CPPUNIT_ASSERT(w.has_point);
        CPPUNIT_ASSERT(w.hops[0].point[0].lo == 5);
        CPPUNIT_ASSERT(w.hops[1].point[0].lo == 5);
        // so a rule at table 1 for dst 0101 moves the path, one for dst 0000 not
        CPPUNIT_ASSERT(witness_hits_rule(n, w, 1, ANY_PORT, "0101xxxx", true));
        CPPUNIT_ASSERT(!witness_hits_rule(n, w, 1, ANY_PORT, "0000xxxx", true));
      }
  }

  void test_a_witness_watches_the_ports_it_left_by() {
    Network n = two_paths();
    for (const auto &scan : WALKS)
      for (Revisit rv : REVISITS) {
        LocalResult r = walked(n, scan, rv);
        const Witness &w = r.witnesses[0].at(2);
        CPPUNIT_ASSERT(w.hits_port(11));
        CPPUNIT_ASSERT(!w.hits_port(12));   // the other path's egress
        CPPUNIT_ASSERT(!w.hits_port(32));
        CPPUNIT_ASSERT(r.footprint.hits_port(12));
      }
  }

  void test_rule_fates() {
    Network n = net();
    vftest::one_table(n, 1, {11, 12, 13});
    vftest::one_table(n, 2, {21});
    n.add_link(11, 21);
    n.load_rule(vftest::rule(1, 1, 10, "0xxxxxxx", {11}));        // linked
    n.load_rule(vftest::rule(2, 1, 10, "10xxxxxx", {12}));        // unlinked
    n.load_rule(vftest::rule(3, 1, 10, "110xxxxx", {}));          // drop
    n.load_rule(consume(4, 1, "111xxxxx"));                       // consume
    n.load_rule(vftest::rule(5, 1, 10, "xxxxxxxx", {11, 13}));    // both
    Fate f = rule_fate(n, 1);
    CPPUNIT_ASSERT(f.opens && f.consumed_at.empty() && f.unlinked.empty());
    f = rule_fate(n, 2);
    CPPUNIT_ASSERT(!f.opens && f.consumed_at.empty() && f.unlinked == std::set<uint64_t>{12});
    f = rule_fate(n, 3);
    CPPUNIT_ASSERT(!f.opens && f.consumed_at.empty() && f.unlinked.empty());
    f = rule_fate(n, 4);
    CPPUNIT_ASSERT(!f.opens && f.consumed_at == std::set<uint32_t>{1});
    f = rule_fate(n, 5);
    CPPUNIT_ASSERT(f.opens && f.unlinked == std::set<uint64_t>{13});
  }

  void test_a_deleted_rule_hands_its_packets_to_the_rules_below() {
    // table 1: a high rule forwards dst 0xxx to table 2; below it a drop for
    // dst 00xx and a forward of everything to an unlinked port 12; above it a
    // rule that would forward to table 2 but is above, so takes nothing freed
    Network n = net();
    vftest::one_table(n, 1, {11, 12});
    vftest::one_table(n, 2, {21});
    n.add_link(11, 21);
    n.load_rule(vftest::rule(1, 1, 20, "0xxxxxxx", {11}));
    n.load_rule(vftest::rule(2, 1, 10, "00xxxxxx", {}));
    n.load_rule(vftest::rule(3, 1, 5, "xxxxxxxx", {12}));
    n.load_rule(vftest::rule(4, 1, 30, "1xxxxxxx", {11}));
    n.load_rule(consume(5, 2, "xxxxxxxx"));
    for (const auto &scan : WALKS)
      for (Revisit rv : REVISITS) {
        LocalResult r = walked(n, scan, rv);
        Fate f = delete_fate(n, r.footprint, 1);
        // freed: dst 0xxx -> the drop and the unlinked forward; no rule above
        CPPUNIT_ASSERT(!f.opens);
        CPPUNIT_ASSERT(f.consumed_at.empty());
        CPPUNIT_ASSERT(f.unlinked == std::set<uint64_t>{12});
        // the lowest rule hands on to nothing: its packets end there
        f = delete_fate(n, r.footprint, 3);
        CPPUNIT_ASSERT(!f.opens && f.unlinked.empty() && f.consumed_at.empty());
      }
    // once port 12 is linked, deleting rule 1 opens a path
    vftest::one_table(n, 3, {31});
    n.add_link(12, 31);
    LocalResult r = walked(n, {}, Revisit::STATE);
    CPPUNIT_ASSERT(delete_fate(n, r.footprint, 1).opens);
  }

  void test_no_witness_without_asking() {
    Network n = two_paths();
    LocalResult r = local_deliveries(n, "xxxxxxxx", {{1, ANY_PORT}}, 0,
                                     Revisit::STATE, {}, true);
    CPPUNIT_ASSERT(r.witnesses.empty());
  }
};

CPPUNIT_TEST_SUITE_REGISTRATION(FootprintTest);
