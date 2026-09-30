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
   V3: packet transformations and device-local slicing (VERIFLOW_PLAN.md
   §4.5, T §3.1.3; Q3, Q4, Q19, Q22). L8 is DERIVED -- the thesis gives the
   four steps without an example -- and so is the rest of L10 (VLAN isolation,
   T §4.5). The oracle simulates concrete packets through rewrites and checks
   the engine's deliveries against it on random networks.

   Two 4-bit fields throughout the hand tests: vlan, then dst. Port TP is
   port P of table T.
*/

#include <cppunit/TestFixture.h>
#include <cppunit/extensions/HelperMacros.h>

#include <functional>
#include <random>
#include <sstream>

#include "../src/queries.h"
#include "../src/veriflow.h"
#include "test_util.h"

using namespace vf;

namespace {

Network net44() { return Network(Layout({{"vlan", 4}, {"dst", 4}})); }

void tables(Network &net, std::vector<std::pair<uint32_t, std::vector<uint64_t>>> spec) {
  for (auto &t : spec) vftest::one_table(net, t.first, t.second);
}

Rule consume(uint64_t id, uint32_t table, const std::string &match) {
  Rule r = vftest::rule(id, table, 0, match, {});
  r.consume = true;
  return r;
}

Rule with_rewrite(Rule r, size_t field, const std::string &bits) {
  r.rewrites.push_back({field, prefix_to_interval(bits)});
  return r;
}

typedef std::set<uint32_t> Tables;

Tables delivered(const Network &net, const std::string &range, uint32_t from) {
  LocalResult res = local_deliveries(net, range, {{from, ANY_PORT}});
  CPPUNIT_ASSERT(res.finished);
  return res.delivered[0];
}

}  // namespace

class RewriteTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(RewriteTest);
  CPPUNIT_TEST(test_L8_a_rewrite_transforms_the_ec);
  CPPUNIT_TEST(test_L8_Q3_the_transformed_set_is_resliced_and_forks);
  CPPUNIT_TEST(test_L8_Q19_clear_to_any);
  CPPUNIT_TEST(test_L8_Q4_a_revisit_ends_the_path_whatever_the_header);
  CPPUNIT_TEST(test_local_equals_network_without_rewrites);
  CPPUNIT_TEST(test_network_slicing_refuses_rewrites);
  CPPUNIT_TEST(test_L10_4_5_vlan_isolation);
  CPPUNIT_TEST(test_Q22_budget_stops_unfinished_and_names_the_table);
  CPPUNIT_TEST(test_oracle_random_rewrites);
  CPPUNIT_TEST_SUITE_END();

 public:
  // L8 (T §3.1.3, steps 1-3), derived. s1 sets vlan := 0101 on dst 0xxx and
  // forwards to s2. s2 sends vlan 0101 to probe 3, anything else (lower
  // priority) to probe 4. A packet with ANY vlan and dst 0xxx arrives at s2
  // transformed -- vlan exactly 5 -- so only probe 3 receives it. dst 1xxx
  // matches nothing at s1.
  void test_L8_a_rewrite_transforms_the_ec() {
    Network net = net44();
    tables(net, {{1, {11}}, {2, {21, 22, 23}}, {3, {31}}, {4, {41}}});
    net.add_link(11, 21); net.add_link(22, 31); net.add_link(23, 41);
    net.add_rule(with_rewrite(vftest::rule(1, 1, 0, "xxxx" "0xxx", {11}), 0, "0101"));
    net.add_rule(vftest::rule(2, 2, 1, "0101" "xxxx", {22}));
    net.add_rule(vftest::rule(3, 2, 0, "xxxx" "xxxx", {23}));
    net.add_rule(consume(4, 3, "xxxxxxxx"));
    net.add_rule(consume(5, 4, "xxxxxxxx"));

    CPPUNIT_ASSERT(delivered(net, "xxxx" "0xxx", 1) == (Tables{3}));
    CPPUNIT_ASSERT(delivered(net, "xxxx" "1xxx", 1).empty());
  }

  // Q3, derived: after a rewrite the next device's rules may split the
  // transformed set, and the walk forks per local EC. s1 sets vlan := 01xx
  // (a masked set: {4,5,6,7}, as a NAT to a subnet does). s2 sends 4 to probe
  // 3, 5 to probe 4, anything else to probe 5 -- all three receive packets.
  void test_L8_Q3_the_transformed_set_is_resliced_and_forks() {
    Network net = net44();
    tables(net, {{1, {11}}, {2, {21, 22, 23, 24}}, {3, {31}}, {4, {41}}, {5, {51}}});
    net.add_link(11, 21); net.add_link(22, 31); net.add_link(23, 41); net.add_link(24, 51);
    net.add_rule(with_rewrite(vftest::rule(1, 1, 0, "xxxxxxxx", {11}), 0, "01xx"));
    net.add_rule(vftest::rule(2, 2, 2, "0100" "xxxx", {22}));
    net.add_rule(vftest::rule(3, 2, 2, "0101" "xxxx", {23}));
    net.add_rule(vftest::rule(4, 2, 0, "xxxxxxxx", {24}));
    net.add_rule(consume(5, 3, "xxxxxxxx"));
    net.add_rule(consume(6, 4, "xxxxxxxx"));
    net.add_rule(consume(7, 5, "xxxxxxxx"));

    CPPUNIT_ASSERT(delivered(net, "0000" "xxxx", 1) == (Tables{3, 4, 5}));
  }

  // Q19, derived: FaVe clears its metadata by rewriting a field to ANY. A
  // packet with vlan exactly 0000 leaves s1 with any vlan; s2 splits it and
  // both of its probes receive packets.
  void test_L8_Q19_clear_to_any() {
    Network net = net44();
    tables(net, {{1, {11}}, {2, {21, 22, 23}}, {3, {31}}, {4, {41}}});
    net.add_link(11, 21); net.add_link(22, 31); net.add_link(23, 41);
    net.add_rule(with_rewrite(vftest::rule(1, 1, 0, "xxxxxxxx", {11}), 0, "xxxx"));
    net.add_rule(vftest::rule(2, 2, 1, "1xxx" "xxxx", {22}));
    net.add_rule(vftest::rule(3, 2, 0, "xxxxxxxx", {23}));
    net.add_rule(consume(4, 3, "xxxxxxxx"));
    net.add_rule(consume(5, 4, "xxxxxxxx"));

    CPPUNIT_ASSERT(delivered(net, "0000" "xxxx", 1) == (Tables{3, 4}));
  }

  // L8 step 4 and Q4, derived. s1 sends vlan 0000 to s2, which rewrites it to
  // 1111 and sends it back; s1 would deliver vlan 1111 to probe 3. The path
  // 1, 2, 1 revisits table 1 with a DIFFERENT header -- not a forwarding loop
  // in the strict sense (Q4). FaVe's semantics decide: NetPlumber stops a flow
  // that revisits a table (net_plumber/FAVE_CHANGES.md §6), so VeriFlow-FR
  // does too, and nothing is delivered. A DEVIATION TEST against the thesis's
  // "already visited for a previously encountered packet set", recorded as such.
  void test_L8_Q4_a_revisit_ends_the_path_whatever_the_header() {
    Network net = net44();
    tables(net, {{1, {11, 12, 13}}, {2, {21, 22}}, {3, {31}}});
    net.add_link(11, 21); net.add_link(22, 12); net.add_link(13, 31);
    net.add_rule(vftest::rule(1, 1, 1, "0000" "xxxx", {11}));
    net.add_rule(vftest::rule(2, 1, 1, "1111" "xxxx", {13}));
    net.add_rule(with_rewrite(vftest::rule(3, 2, 0, "xxxxxxxx", {22}), 0, "1111"));
    net.add_rule(consume(4, 3, "xxxxxxxx"));

    CPPUNIT_ASSERT(delivered(net, "0000" "xxxx", 1).empty());
    // ... while a packet that STARTS with vlan 1111 is delivered directly.
    CPPUNIT_ASSERT(delivered(net, "1111" "xxxx", 1) == (Tables{3}));
  }

  // Without rewrites the two slicings answer alike: local slicing is a finer
  // way to the same deliveries (T §3.1.3 replaces the network-wide pass).
  void test_local_equals_network_without_rewrites() {
    std::mt19937 rng(11);
    for (int trial = 0; trial < 30; ++trial) {
      Network net = net44();
      for (uint32_t t = 1; t <= 4; ++t) vftest::one_table(net, t, {t * 10 + 1, t * 10 + 2});
      for (uint32_t t = 1; t <= 4; ++t)
        for (int k = 0; k < 2; ++k)
          net.add_link(t * 10 + 1 + k, (1 + rng() % 4) * 10 + 1 + rng() % 2);
      for (uint64_t id = 1; id <= 16; ++id) {
        uint32_t t = 1 + rng() % 4;
        // Per field a prefix: the engine refuses any other ternary value.
        std::string m;
        for (int f = 0; f < 2; ++f) {
          unsigned len = rng() % 5;
          for (unsigned i = 0; i < 4; ++i) m += i < len ? ((rng() & 1) ? '1' : '0') : 'x';
        }
        Rule r = vftest::rule(id, t, rng() % 3, m, {t * 10 + 1 + rng() % 2});
        if (rng() % 5 == 0) { r.out_ports.clear(); r.consume = true; }
        net.load_rule(r);
      }
      const std::vector<std::pair<uint32_t, int64_t>> starts = {{1, ANY_PORT}, {2, ANY_PORT}};
      std::vector<std::set<uint32_t>> nw = deliveries(net, "xxxxxxxx", starts);
      LocalResult lc = local_deliveries(net, "xxxxxxxx", starts);
      CPPUNIT_ASSERT(lc.finished);
      CPPUNIT_ASSERT(nw == lc.delivered);
    }
  }

  // "We can no longer compute network-wide equivalence classes" with
  // rewrites (T §3.1.3): the network-wide slicing refuses them.
  void test_network_slicing_refuses_rewrites() {
    Network net = net44();
    tables(net, {{1, {11}}});
    net.add_rule(with_rewrite(vftest::rule(1, 1, 0, "xxxxxxxx", {11}), 0, "0101"));
    CPPUNIT_ASSERT_THROW(deliveries(net, "xxxxxxxx", {{1, ANY_PORT}}), std::logic_error);
  }

  // T §4.5, derived. VLAN 10 (1010) enters router 1. A layer-3 rule routes
  // dst 1xxx into VLAN 12 (1100) by a rewrite: packets of VLAN 10 reach VLAN
  // 12, a leak unless intended. dst 0xxx stays in VLAN 10.
  void test_L10_4_5_vlan_isolation() {
    Network net = net44();
    tables(net, {{1, {11, 12}}, {2, {21}}, {3, {31}}});
    net.add_link(11, 21); net.add_link(12, 31);
    net.add_rule(with_rewrite(vftest::rule(1, 1, 1, "1010" "1xxx", {11}), 0, "1100"));
    net.add_rule(vftest::rule(2, 1, 0, "1010" "0xxx", {12}));
    net.add_rule(consume(3, 2, "xxxxxxxx"));
    net.add_rule(consume(4, 3, "xxxxxxxx"));

    CPPUNIT_ASSERT(may_carry(net, "1010" "1xxx", {1, ANY_PORT}, 0, 12));
    CPPUNIT_ASSERT(!may_carry(net, "1010" "0xxx", {1, ANY_PORT}, 0, 12));
  }

  // Q22: the budget. s1 holds 15 rules cutting dst into 16 ranges; with a
  // budget of 10 local ECs the query stops before slicing there, unfinished,
  // naming table 1 and its predicted 16.
  void test_Q22_budget_stops_unfinished_and_names_the_table() {
    Network net = net44();
    tables(net, {{1, {11}}, {2, {21}}});
    net.add_link(11, 21);
    for (uint64_t v = 0; v < 15; ++v) {
      std::string dst;
      for (int b = 3; b >= 0; --b) dst += ((v >> b) & 1) ? '1' : '0';
      net.add_rule(vftest::rule(v + 1, 1, 1, "xxxx" + dst, {11}));
    }
    net.add_rule(consume(100, 2, "xxxxxxxx"));
    LocalResult small = local_deliveries(net, "xxxxxxxx", {{1, ANY_PORT}}, 10);
    CPPUNIT_ASSERT(!small.finished);
    CPPUNIT_ASSERT_EQUAL((uint32_t)1, small.stopped_at);
    CPPUNIT_ASSERT_DOUBLES_EQUAL(16.0, small.predicted, 1e-9);
    LocalResult enough = local_deliveries(net, "xxxxxxxx", {{1, ANY_PORT}}, 100);
    CPPUNIT_ASSERT(enough.finished);
    CPPUNIT_ASSERT(enough.delivered[0] == (Tables{2}));
  }

  // The oracle, with rewrites. Concrete packets on 2 x 3 bits, simulated hop
  // by hop by a linear scan -- a rewrite to a SET branches over every value in
  // it -- with the same path rule (a revisited table ends the path). The
  // deliveries must equal the engine's, from every table, for random query sets.
  void test_oracle_random_rewrites() {
    std::mt19937 rng(20260930);
    const Layout layout({{"a", 3}, {"b", 3}});
    for (int trial = 0; trial < 60; ++trial) {
      Network net(layout);
      std::vector<Rule> rules;
      for (uint32_t t = 1; t <= 4; ++t) vftest::one_table(net, t, {t * 10 + 1, t * 10 + 2});
      std::map<uint64_t, std::vector<uint64_t>> links;
      for (uint32_t t = 1; t <= 4; ++t)
        for (int k = 0; k < 2; ++k)
          if (rng() % 4) {
            uint64_t to = (1 + rng() % 4) * 10 + 1 + rng() % 2;
            net.add_link(t * 10 + 1 + k, to);
            links[t * 10 + 1 + k].push_back(to);
          }
      auto prefix = [&](unsigned w) {
        std::string s(w, 'x');
        unsigned len = rng() % (w + 1);
        for (unsigned i = 0; i < len; ++i) s[i] = (rng() & 1) ? '1' : '0';
        return s;
      };
      for (uint64_t id = 1; id <= 14; ++id) {
        uint32_t t = 1 + rng() % 4;
        Rule r = vftest::rule(id, t, rng() % 3, prefix(3) + prefix(3), {t * 10 + 1 + rng() % 2});
        int64_t arrival = rng() % 4 == 0 ? (int64_t)(t * 10 + 1 + rng() % 2) : ANY_PORT;
        r.in_port = arrival;
        if (rng() % 5 == 0) { r.out_ports.clear(); r.consume = true; }
        else if (rng() % 3 == 0) r.rewrites.push_back({rng() % 2, prefix_to_interval(prefix(3))});
        net.load_rule(r);
        rules.push_back(r);
      }

      // The oracle's simulation of one concrete packet.
      std::function<void(uint32_t, int64_t, unsigned, std::vector<uint32_t> &, std::set<uint32_t> &)> sim;
      sim = [&](uint32_t t, int64_t arr, unsigned pkt, std::vector<uint32_t> &path,
                std::set<uint32_t> &out) {
        if (std::find(path.begin(), path.end(), t) != path.end()) return;
        const Rule *best = nullptr;
        const unsigned a = pkt >> 3, b = pkt & 7;
        for (const Rule &r : rules) {
          if (r.table != t) continue;
          if (r.in_port != ANY_PORT && r.in_port != arr) continue;
          Interval ia = prefix_to_interval(r.match.substr(0, 3));
          Interval ib = prefix_to_interval(r.match.substr(3, 3));
          if (a < ia.lo || a > ia.hi || b < ib.lo || b > ib.hi) continue;
          if (!best || r.priority > best->priority) best = &r;
        }
        if (!best) return;
        if (best->consume) { out.insert(t); return; }
        std::vector<unsigned> next = {pkt};
        for (const auto &rw : best->rewrites) {
          std::vector<unsigned> grown;
          for (unsigned p : next)
            for (u128 v = rw.second.lo; v <= rw.second.hi; ++v)
              grown.push_back(rw.first == 0 ? (((unsigned)v << 3) | (p & 7))
                                            : ((p & 0x38) | (unsigned)v));
          next = grown;
        }
        path.push_back(t);
        for (uint64_t op : best->out_ports)
          for (uint64_t to : links[op])
            for (unsigned p : next) sim(net.port_table(to), (int64_t)to, p, path, out);
        path.pop_back();
      };

      for (int q = 0; q < 4; ++q) {
        std::string range = prefix(3) + prefix(3);
        Interval qa = prefix_to_interval(range.substr(0, 3));
        Interval qb = prefix_to_interval(range.substr(3, 3));
        for (uint32_t start = 1; start <= 4; ++start) {
          std::set<uint32_t> want;
          for (unsigned p = 0; p < 64; ++p) {
            unsigned a = p >> 3, b = p & 7;
            if (a < qa.lo || a > qa.hi || b < qb.lo || b > qb.hi) continue;
            std::vector<uint32_t> path;
            sim(start, ANY_PORT, p, path, want);
          }
          LocalResult got = local_deliveries(net, range, {{start, ANY_PORT}});
          CPPUNIT_ASSERT(got.finished);
          if (got.delivered[0] != want) {
            std::ostringstream msg;
            msg << "trial " << trial << " range " << range << " start " << start
                << ": engine " << got.delivered[0].size() << " tables, oracle "
                << want.size();
            CPPUNIT_FAIL(msg.str());
          }
        }
      }
    }
  }
};

CPPUNIT_TEST_SUITE_REGISTRATION(RewriteTest);
