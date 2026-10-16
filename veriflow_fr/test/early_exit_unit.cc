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
   Early exit (owner, 2026-10-16; ACCOMMODATIONS.md): a start's walk stops once
   every table it is asked about is delivered. The gate: for every asked table
   the answer equals the full walk's, on random networks with rewrites, under
   both field modes and both revisit rules -- and the walk never slices MORE.
*/

#include <cppunit/TestFixture.h>
#include <cppunit/extensions/HelperMacros.h>

#include <random>

#include "../src/queries.h"
#include "../src/veriflow.h"
#include "test_util.h"

using namespace vf;

class EarlyExitTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(EarlyExitTest);
  CPPUNIT_TEST(test_a_reached_target_stops_the_walk);
  CPPUNIT_TEST(test_answers_equal_the_full_walk_on_random_networks);
  CPPUNIT_TEST_SUITE_END();

 public:
  void test_a_reached_target_stops_the_walk() {
    // table 1 forwards half the space to table 2 (consumes) and half to
    // table 3 (consumes); asking for table 2 stops before table 3 is walked
    Network n(Layout({{"dst", 4}}));
    vftest::one_table(n, 1, {11, 12});
    vftest::one_table(n, 2, {21});
    vftest::one_table(n, 3, {31});
    n.add_link(11, 21);
    n.add_link(12, 31);
    n.load_rule(vftest::rule(1, 1, 1, "0xxx", {11}));
    n.load_rule(vftest::rule(2, 1, 1, "1xxx", {12}));
    Rule c2 = vftest::rule(3, 2, 0, "xxxx", {});
    c2.consume = true;
    n.load_rule(c2);
    Rule c3 = vftest::rule(4, 3, 0, "xxxx", {});
    c3.consume = true;
    n.load_rule(c3);
    LocalResult full = local_deliveries(n, "xxxx", {{1, ANY_PORT}}, 0, Revisit::STATE);
    LocalResult early = local_deliveries(n, "xxxx", {{1, ANY_PORT}}, 0, Revisit::STATE,
                                         {}, false, false, {{2}});
    CPPUNIT_ASSERT_EQUAL((size_t)2, full.delivered[0].size());
    CPPUNIT_ASSERT(early.delivered[0].count(2));
    CPPUNIT_ASSERT(!early.delivered[0].count(3));
    CPPUNIT_ASSERT_EQUAL((uint64_t)1, early.early_exits);
    CPPUNIT_ASSERT(early.hops < full.hops);
  }

  void test_answers_equal_the_full_walk_on_random_networks() {
    std::mt19937 rng(2026);
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
    int stopped = 0;
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
      const std::vector<std::pair<uint32_t, int64_t>> starts = {{1, ANY_PORT}, {2, ANY_PORT}};
      for (int q = 0; q < 3; ++q) {
        const std::string range = prefix(3) + prefix(2) + prefix(2);
        for (const std::vector<bool> &sc : {std::vector<bool>(), scan}) {
          for (Revisit rv : {Revisit::STATE, Revisit::PATH}) {
            LocalResult full = local_deliveries(n, range, starts, 0, rv, sc);
            for (uint32_t a = 1; a <= 4; ++a) {
              for (uint32_t b = a; b <= 4; ++b) {
                std::vector<std::vector<uint32_t>> targets = {{a, b}, {b}};
                LocalResult early = local_deliveries(n, range, starts, 0, rv, sc,
                                                     false, false, targets);
                for (size_t i = 0; i < starts.size(); ++i)
                  for (uint32_t t : targets[i])
                    if (early.delivered[i].count(t) != full.delivered[i].count(t))
                      CPPUNIT_FAIL("trial " + std::to_string(trial) + " range " + range +
                                   ": early exit answers table " + std::to_string(t) +
                                   " differently");
                CPPUNIT_ASSERT(early.local_ecs <= full.local_ecs);
                stopped += (int)early.early_exits;
              }
            }
          }
        }
      }
    }
    CPPUNIT_ASSERT(stopped > 100);   // non-vacuous: walks did stop early
  }
};

CPPUNIT_TEST_SUITE_REGISTRATION(EarlyExitTest);
