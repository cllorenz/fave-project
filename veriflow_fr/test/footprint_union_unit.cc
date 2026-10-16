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
   TODO item 59: a footprint keeps, per table and arrival, boxes whose union
   is the union of the states reached there (adjacent boxes merged). The
   gate: on random networks with rewrites, under both field modes and both
   revisit rules, `footprint_hits_rule` for random rules and `delete_fate`
   for every loaded rule answer as the per-state footprint does, the ports
   are equal -- and the merged footprint holds no more boxes than states.
*/

#include <cppunit/TestFixture.h>
#include <cppunit/extensions/HelperMacros.h>

#include <random>

#include "../src/queries.h"
#include "../src/veriflow.h"
#include "test_util.h"

using namespace vf;

class FootprintUnionTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(FootprintUnionTest);
  CPPUNIT_TEST(test_a_grid_merges_back_into_one_box);
  CPPUNIT_TEST(test_answers_equal_the_per_state_footprint_on_random_networks);
  CPPUNIT_TEST_SUITE_END();

 public:
  void tearDown() override { Footprint::merging = true; }

  void test_a_grid_merges_back_into_one_box() {
    Footprint fp;
    for (u128 a = 0; a < 4; ++a)
      for (u128 b = 0; b < 4; ++b)
        fp.add(7, ANY_PORT, Box{{a, a}, {b * 2, b * 2 + 1}});
    fp.compact();
    CPPUNIT_ASSERT_EQUAL((size_t)1, fp.boxes());
    const Box &one = fp.states.at(7).begin()->second;
    CPPUNIT_ASSERT(one[0] == (Interval{0, 3}) && one[1] == (Interval{0, 7}));
    // a different arrival never merges
    fp.add(7, 5, Box{{4, 4}, {0, 7}});
    fp.compact();
    CPPUNIT_ASSERT_EQUAL((size_t)2, fp.boxes());
  }

  void test_answers_equal_the_per_state_footprint_on_random_networks() {
    std::mt19937 rng(59);
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
    size_t states = 0, boxes = 0;
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
            Footprint::merging = false;
            LocalResult ref = local_deliveries(n, range, starts, 0, rv, sc, true, false);
            Footprint::merging = true;
            LocalResult got = local_deliveries(n, range, starts, 0, rv, sc, true, false);
            const std::string where = "trial " + std::to_string(trial) + " range " + range;
            CPPUNIT_ASSERT_MESSAGE(where, got.footprint.ports == ref.footprint.ports);
            CPPUNIT_ASSERT_MESSAGE(where, got.footprint.boxes() <= ref.footprint.boxes());
            states += ref.footprint.boxes();
            boxes += got.footprint.boxes();
            for (int k = 0; k < 24; ++k) {
              const uint32_t table = 1 + rng() % 4;
              const int64_t in_port = rng() % 3 ? ANY_PORT : (int64_t)(table * 10 + 1 + rng() % 2);
              const std::string match = prefix(3) + prefix(2) + prefix(2);
              if (footprint_hits_rule(n, got.footprint, table, in_port, match) !=
                  footprint_hits_rule(n, ref.footprint, table, in_port, match))
                CPPUNIT_FAIL(where + ": footprint_hits_rule differs for " + match);
            }
            for (uint64_t id = 1; id <= 16; ++id) {
              const Fate a = delete_fate(n, got.footprint, id);
              const Fate b = delete_fate(n, ref.footprint, id);
              if (a.opens != b.opens || a.consumed_at != b.consumed_at || a.unlinked != b.unlinked)
                CPPUNIT_FAIL(where + ": delete_fate differs for rule " + std::to_string(id));
            }
          }
        }
      }
    }
    CPPUNIT_ASSERT(boxes < states);   // non-vacuous: something merged
  }
};

CPPUNIT_TEST_SUITE_REGISTRATION(FootprintUnionTest);
