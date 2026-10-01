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
   V3b: T §3.2.2's 4 + 10 field optimisation, generalised (VERIFLOW_PLAN.md D6).
   L9 is DERIVED from the thesis's own sentence -- "a subset of a packet set may
   be served by a finer rule having higher priority than a coarser rule that
   serves the rest of that packet set. We handle this by maintaining a set of
   excluded packets for each forwarding action" -- and the gate is VERDICT
   IDENTITY with plain slicing (D6) on random networks with rewrites.

   Two 4-bit fields: dst (a trie field), then dport (a scan field).
*/

#include <cppunit/TestFixture.h>
#include <cppunit/extensions/HelperMacros.h>

#include <random>
#include <stdexcept>

#include "../src/queries.h"
#include "../src/veriflow.h"
#include "test_util.h"

using namespace vf;

namespace {

Network net() { return Network(Layout({{"dst", 4}, {"dport", 4}})); }
const std::vector<bool> SCAN = {false, true};

void tables(Network &n, std::vector<std::pair<uint32_t, std::vector<uint64_t>>> spec) {
  for (auto &t : spec) vftest::one_table(n, t.first, t.second);
}

Rule consume(uint64_t id, uint32_t table, const std::string &match) {
  Rule r = vftest::rule(id, table, 0, match, {});
  r.consume = true;
  return r;
}

typedef std::set<uint32_t> Tables;

Tables got(const Network &n, const std::string &range, const std::vector<bool> &scan,
           Revisit revisit = Revisit::STATE) {
  LocalResult r = local_deliveries(n, range, {{1, ANY_PORT}}, 0, revisit, scan);
  CPPUNIT_ASSERT(r.finished);
  return r.delivered[0];
}

}  // namespace

class Opt46Test : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(Opt46Test);
  CPPUNIT_TEST(test_L9_a_finer_rule_serves_a_subset_the_coarse_one_the_rest);
  CPPUNIT_TEST(test_L9_an_exclusion_survives_a_rewrite_of_its_field);
  CPPUNIT_TEST(test_a_scan_field_must_be_exact_or_any);
  CPPUNIT_TEST(test_scan_fields_slice_less);
  CPPUNIT_TEST(test_verdict_identity_with_plain_on_random_networks);
  CPPUNIT_TEST_SUITE_END();

 public:
  // L9 (T §3.2.2, derived). s1 forwards everything to s2. s2's finer rule
  // (dport 0110, higher priority) serves that subset towards probe 3; the
  // coarser rule (any dport) serves the rest towards probe 4. Any dport: both
  // probes receive packets. dport 0110 alone: the coarse rule's share is the
  // primary set minus the excluded {0110} -- empty -- so only probe 3.
  void test_L9_a_finer_rule_serves_a_subset_the_coarse_one_the_rest() {
    Network n = net();
    tables(n, {{1, {11}}, {2, {21, 22, 23}}, {3, {31}}, {4, {41}}});
    n.add_link(11, 21); n.add_link(22, 31); n.add_link(23, 41);
    n.add_rule(vftest::rule(1, 1, 0, "xxxx" "xxxx", {11}));
    n.add_rule(vftest::rule(2, 2, 2, "xxxx" "0110", {22}));
    n.add_rule(vftest::rule(3, 2, 1, "xxxx" "xxxx", {23}));
    n.add_rule(consume(4, 3, "xxxxxxxx"));
    n.add_rule(consume(5, 4, "xxxxxxxx"));

    CPPUNIT_ASSERT(got(n, "xxxx" "xxxx", SCAN) == (Tables{3, 4}));
    CPPUNIT_ASSERT(got(n, "xxxx" "0110", SCAN) == (Tables{3}));
    CPPUNIT_ASSERT(got(n, "xxxx" "0111", SCAN) == (Tables{4}));
  }

  // The pitfall our design guards (D6). s2's finer rule DROPS dport 0110; the
  // coarse rule rewrites dport := 0101 and forwards to s3, which delivers dport
  // 0101 at probe 3. For any dport the remainder (dport != 0110) is rewritten
  // to 0101 and delivered. Subtracting the exclusion AFTER the rewrite would
  // map it onto 0101 too and wrongly empty the set.
  void test_L9_an_exclusion_survives_a_rewrite_of_its_field() {
    Network n = net();
    tables(n, {{1, {11}}, {2, {21, 22}}, {3, {31, 32}}, {4, {41}}});
    n.add_link(11, 21); n.add_link(22, 31); n.add_link(32, 41);
    n.add_rule(vftest::rule(1, 1, 0, "xxxxxxxx", {11}));
    n.add_rule(vftest::rule(2, 2, 2, "xxxx" "0110", {}));       // drop
    Rule coarse = vftest::rule(3, 2, 1, "xxxx" "xxxx", {22});
    coarse.rewrites.push_back({1, prefix_to_interval("0101")});
    n.add_rule(coarse);
    n.add_rule(vftest::rule(4, 3, 0, "xxxx" "0101", {32}));
    n.add_rule(consume(5, 4, "xxxxxxxx"));

    CPPUNIT_ASSERT(got(n, "xxxx" "xxxx", SCAN) == (Tables{4}));
    CPPUNIT_ASSERT(got(n, "xxxx" "0110", SCAN).empty());
    CPPUNIT_ASSERT(got(n, "xxxx" "0110", {}).empty());       // plain agrees
  }

  // A scan field is one every rule matches exactly or not at all (D6). A
  // prefix there is refused, never mis-sliced.
  void test_a_scan_field_must_be_exact_or_any() {
    Network n = net();
    tables(n, {{1, {11}}});
    n.add_rule(vftest::rule(1, 1, 0, "xxxx" "01xx", {11}));
    CPPUNIT_ASSERT_THROW(local_deliveries(n, "xxxxxxxx", {{1, ANY_PORT}}, 0,
                                          Revisit::STATE, SCAN),
                         std::invalid_argument);
  }

  // What the optimisation is for. Twelve exact-dport rules at one table: plain
  // slicing cuts dport into 25 ranges there; with dport a scan field the trie
  // field dst is not cut at all, so far fewer local ECs are sliced -- and the
  // deliveries are the same.
  void test_scan_fields_slice_less() {
    Network n = net();
    tables(n, {{1, {11, 12}}, {2, {21}}, {3, {31}}});
    n.add_link(11, 21); n.add_link(12, 31);
    for (uint64_t v = 0; v < 12; ++v) {
      std::string dport;
      for (int b = 3; b >= 0; --b) dport += ((v >> b) & 1) ? '1' : '0';
      n.add_rule(vftest::rule(v + 1, 1, 2, "xxxx" + dport, {v % 2 ? 11u : 12u}));
    }
    n.add_rule(vftest::rule(50, 1, 1, "xxxxxxxx", {12}));
    n.add_rule(consume(51, 2, "xxxxxxxx"));
    n.add_rule(consume(52, 3, "xxxxxxxx"));

    LocalResult plain = local_deliveries(n, "xxxxxxxx", {{1, ANY_PORT}}, 0, Revisit::STATE);
    LocalResult opt = local_deliveries(n, "xxxxxxxx", {{1, ANY_PORT}}, 0, Revisit::STATE, SCAN);
    CPPUNIT_ASSERT(plain.delivered == opt.delivered);
    CPPUNIT_ASSERT(opt.local_ecs < plain.local_ecs);
  }

  // D6's gate: verdict identity with plain slicing. Random networks over a
  // prefix field and two scan fields; scan values exact or ANY; rewrites on
  // every field (a prefix on the trie field, exact or ANY on scan fields);
  // ingress-qualified rules; both revisit rules; four query sets per network.
  void test_verdict_identity_with_plain_on_random_networks() {
    std::mt19937 rng(46);
    const Layout layout({{"a", 3}, {"s", 2}, {"t", 2}});
    const std::vector<bool> scan = {false, true, true};
    auto prefix = [&](unsigned w) {
      std::string s(w, 'x');
      unsigned len = rng() % (w + 1);
      for (unsigned i = 0; i < len; ++i) s[i] = (rng() & 1) ? '1' : '0';
      return s;
    };
    auto exact_or_any = [&](unsigned w) {
      if (rng() % 2) return std::string(w, 'x');
      std::string s;
      for (unsigned i = 0; i < w; ++i) s += (rng() & 1) ? '1' : '0';
      return s;
    };
    for (int trial = 0; trial < 120; ++trial) {
      Network n(layout);
      for (uint32_t t = 1; t <= 4; ++t) vftest::one_table(n, t, {t * 10 + 1, t * 10 + 2});
      for (uint32_t t = 1; t <= 4; ++t)
        for (int k = 0; k < 2; ++k)
          if (rng() % 4) n.add_link(t * 10 + 1 + k, (1 + rng() % 4) * 10 + 1 + rng() % 2);
      for (uint64_t id = 1; id <= 16; ++id) {
        uint32_t t = 1 + rng() % 4;
        Rule r = vftest::rule(id, t, rng() % 4, prefix(3) + exact_or_any(2) + exact_or_any(2),
                              {t * 10 + 1 + rng() % 2});
        if (rng() % 4 == 0) r.in_port = (int64_t)(t * 10 + 1 + rng() % 2);
        if (rng() % 6 == 0) { r.out_ports.clear(); r.consume = true; }
        else if (rng() % 7 == 0) r.out_ports.clear();
        else if (rng() % 3 == 0) {
          size_t f = rng() % 3;
          r.rewrites.push_back({f, prefix_to_interval(f == 0 ? prefix(3) : exact_or_any(2))});
        }
        n.load_rule(r);
      }
      for (int q = 0; q < 4; ++q) {
        const std::string range = prefix(3) + prefix(2) + prefix(2);
        for (Revisit rv : {Revisit::STATE, Revisit::PATH}) {
          LocalResult plain = local_deliveries(n, range, {{1, ANY_PORT}, {2, ANY_PORT}}, 0, rv);
          LocalResult opt = local_deliveries(n, range, {{1, ANY_PORT}, {2, ANY_PORT}}, 0, rv, scan);
          if (plain.delivered != opt.delivered)
            CPPUNIT_FAIL("trial " + std::to_string(trial) + " range " + range +
                         (rv == Revisit::STATE ? " state" : " path") +
                         ": 4+10 differs from plain");
        }
      }
    }
  }
};

CPPUNIT_TEST_SUITE_REGISTRATION(Opt46Test);
