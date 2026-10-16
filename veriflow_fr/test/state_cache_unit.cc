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
   TODO item 59, option c (owner, 2026-10-16): under the STATE rule a walk
   ends at a state on its current path, or at one it explored and still
   remembers -- at most `state_cache` of them. The gate: on random networks
   with rewrites (loops included), both field modes, every small cache gives
   the delivered tables, the footprint's answers and the witness paths of the
   unbounded one; it never does less work, and on some trials more.
*/

#include <cppunit/TestFixture.h>
#include <cppunit/extensions/HelperMacros.h>

#include <random>

#include "../src/queries.h"
#include "../src/veriflow.h"
#include "test_util.h"

using namespace vf;

namespace {

bool same_hops(const Witness &a, const Witness &b) {
  if (a.hops.size() != b.hops.size() || a.has_point != b.has_point) return false;
  for (size_t i = 0; i < a.hops.size(); ++i) {
    const Hop &x = a.hops[i], &y = b.hops[i];
    if (x.table != y.table || x.arrival != y.arrival || x.rule != y.rule || x.port != y.port ||
        !(x.set == y.set) || x.excl != y.excl || !(x.point == y.point))
      return false;
  }
  return true;
}

}  // namespace

class StateCacheTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(StateCacheTest);
  CPPUNIT_TEST(test_a_bounded_cache_answers_as_the_unbounded_one);
  CPPUNIT_TEST_SUITE_END();

 public:
  void test_a_bounded_cache_answers_as_the_unbounded_one() {
    std::mt19937 rng(5959);
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
    int more_work = 0;
    for (int trial = 0; trial < 150; ++trial) {
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
          LocalResult all = local_deliveries(n, range, starts, 0, Revisit::STATE, sc,
                                             true, true, {}, 0);
          for (uint64_t cap : {1, 2, 5}) {
            LocalResult some = local_deliveries(n, range, starts, 0, Revisit::STATE, sc,
                                                true, true, {}, cap);
            const std::string where = "trial " + std::to_string(trial) + " range " + range +
                                      " cache " + std::to_string(cap);
            if (some.delivered != all.delivered) CPPUNIT_FAIL(where + ": delivered differs");
            if (some.footprint.ports != all.footprint.ports ||
                some.footprint.states != all.footprint.states)
              CPPUNIT_FAIL(where + ": footprint differs");
            for (size_t i = 0; i < starts.size(); ++i) {
              if (some.witnesses[i].size() != all.witnesses[i].size())
                CPPUNIT_FAIL(where + ": witnessed tables differ");
              for (const auto &w : all.witnesses[i])
                if (!same_hops(some.witnesses[i].at(w.first), w.second))
                  CPPUNIT_FAIL(where + ": witness differs at table " + std::to_string(w.first));
            }
            CPPUNIT_ASSERT(some.hops >= all.hops);
            if (some.hops > all.hops) ++more_work;
          }
        }
      }
    }
    CPPUNIT_ASSERT(more_work > 20);   // non-vacuous: the bound did re-explore
  }
};

CPPUNIT_TEST_SUITE_REGISTRATION(StateCacheTest);
