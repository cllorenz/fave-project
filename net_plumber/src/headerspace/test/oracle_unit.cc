/*
  Copyright 2026, Claas Lorenz. This file is licensed under GPL v2 plus
  a special exception, as described in included LICENSE_EXCEPTION.txt.

  Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#include "oracle_unit.h"
#include "oracle_util.h"

using namespace hs_oracle;

namespace {
  // The two header lengths exercised: 1 byte (8 bits, universe 256) and 2 bytes
  // (16 bits, universe 65536). Both fit in a single array_t word.
  const size_t LENS[] = {1, 2};

  // Trial counts per length; len=2 has a 65536-packet universe so fewer trials.
  size_t trials_for(size_t len) { return len == 1 ? 128 : 48; }

  // A reproducible RNG (fixed seed) so failures are deterministic in CI.
  std::mt19937 make_rng() { return std::mt19937(0xC1AA5EEDu); }
}

// ---------------------------------------------------------------------------
// Anchor: validate the oracle decoder against an independent membership notion.
//
// For random cubes we cross-check cube_to_set() against the implementation's
// own subset test: a singleton packet {p} is in the cube iff p is a subset of
// the cube. (array_is_sub_eq(a,b) is true iff b is a subset of a.) If the
// decoder and the subset test ever disagree, that is itself a finding. We also
// assert the order-independent cardinality law |set| == 2^(#x) for x-only cubes.
// ---------------------------------------------------------------------------
void OracleTest::test_oracle_self_consistency() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    const size_t U = universe_size(len);

    // |set| == 2^(number of x bits) for an x/0/1 cube (no z).
    for (size_t t = 0; t < trials_for(len); t++) {
      const std::string s = rand_cube_str(rng, len, false);
      array_t *a = array_from_str(s.c_str());
      size_t xs = 0;
      for (char c : s) if (c == 'x') xs++;
      CPPUNIT_ASSERT(set_count(cube_to_set(a, len)) == ((size_t)1 << xs));
      array_free(a);
    }

    // Decoder membership agrees with array_is_sub_eq for every packet.
    for (size_t t = 0; t < trials_for(len); t++) {
      array_t *a = rand_cube(rng, len, /*allow_z=*/(t % 5 == 0));
      const PktSet s = cube_to_set(a, len);
      for (uint32_t p = 0; p < U; p++) {
        array_t *sg = oracle_make_singleton(p, len);
        // array_is_sub_eq(x,y) is true iff x is a subset of y (FIRST arg is the
        // subset -- the header's "B subset of A" comment is misleading; verified
        // empirically). So "{p} subset of a" is array_is_sub_eq(sg, a).
        const bool in_impl = array_is_sub_eq(sg, a, len);
        CPPUNIT_ASSERT((bool)s[p] == in_impl);
        array_free(sg);
      }
      array_free(a);
    }
  }
}

// array_isect(a,b) -> res, returns false iff the intersection is empty.
void OracleTest::test_array_isect_oracle() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    for (size_t t = 0; t < trials_for(len); t++) {
      array_t *a = rand_cube(rng, len, t % 7 == 0);
      array_t *b = rand_cube(rng, len, t % 11 == 0);
      const PktSet expected = set_intersect(cube_to_set(a, len), cube_to_set(b, len));

      array_t *res = array_create(len, BIT_X);
      const bool nonempty = array_isect(a, b, len, res);

      CPPUNIT_ASSERT(nonempty == !set_is_empty(expected));
      if (nonempty)
        CPPUNIT_ASSERT(set_equal(cube_to_set(res, len), expected));

      array_free(res);
      array_free(a);
      array_free(b);
    }
  }
}

// array_cmpl(a) yields cubes whose union is the set complement of a.
void OracleTest::test_array_cmpl_oracle() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    const size_t U = universe_size(len);
    for (size_t t = 0; t < trials_for(len); t++) {
      array_t *a = rand_cube(rng, len, t % 4 == 0);
      const PktSet expected = set_complement(cube_to_set(a, len));

      array_t *res[64];
      size_t n = 0;
      array_cmpl(a, len, &n, res);

      PktSet got(U, 0);
      for (size_t k = 0; k < n; k++) got = set_union(got, cube_to_set(res[k], len));

      CPPUNIT_ASSERT(set_equal(got, expected));
      // and the defining laws: a u ~a == universe, a n ~a == empty
      const PktSet sa = cube_to_set(a, len);
      CPPUNIT_ASSERT(set_count(set_union(sa, got)) == U);
      CPPUNIT_ASSERT(set_is_empty(set_intersect(sa, got)));

      for (size_t k = 0; k < n; k++) array_free(res[k]);
      array_free(a);
    }
  }
}

// Rewrite identities: a zero mask is the identity; a full mask makes the cube
// equal to the (concrete) rewrite value.
void OracleTest::test_array_rewrite_identities() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];

    // zero mask -> identity
    for (size_t t = 0; t < trials_for(len); t++) {
      array_t *a = rand_cube(rng, len, false);
      const PktSet before = cube_to_set(a, len);
      array_t *mask = array_create(len, BIT_0);     // all 0 -> rewrite nothing
      array_t *rw   = rand_cube(rng, len, false);
      array_rewrite(a, mask, rw, len);
      CPPUNIT_ASSERT(set_equal(cube_to_set(a, len), before));
      array_free(a); array_free(mask); array_free(rw);
    }

    // full mask + concrete rewrite -> constant
    for (size_t t = 0; t < trials_for(len); t++) {
      array_t *a = rand_cube(rng, len, false);
      array_t *mask = array_create(len, BIT_1);     // all 1 -> rewrite everything
      array_t *rw = oracle_make_singleton((uint32_t)(rng() % universe_size(len)), len);
      const PktSet rw_set = cube_to_set(rw, len);
      array_rewrite(a, mask, rw, len);
      CPPUNIT_ASSERT(set_equal(cube_to_set(a, len), rw_set));
      array_free(a); array_free(mask); array_free(rw);
    }
  }
}

// Predicate functions must agree with the oracle: is_eq, is_sub_eq, has_isect,
// plus commutativity of intersection. NOTE: these are bitwise/structural
// predicates over NORMALISED cubes -- they do not treat a z-bit cube as the
// empty set (cube emptiness is detected via array_has_z / array_isect returning
// false, not via these). So we generate only non-z cubes here; the z/empty
// contract is covered by test_array_isect_oracle and array_has_z.
void OracleTest::test_array_predicate_laws() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    for (size_t t = 0; t < trials_for(len); t++) {
      array_t *a = rand_cube(rng, len, /*allow_z=*/false);
      array_t *b = rand_cube(rng, len, /*allow_z=*/false);
      const PktSet sa = cube_to_set(a, len);
      const PktSet sb = cube_to_set(b, len);

      CPPUNIT_ASSERT(array_is_eq(a, b, len) == set_equal(sa, sb));
      // array_is_sub_eq(a,b) is true iff a is a subset of b (first arg subset).
      CPPUNIT_ASSERT(array_is_sub_eq(a, b, len) == set_subset_eq(sa, sb));
      CPPUNIT_ASSERT(array_has_isect(a, b, len) == !set_is_empty(set_intersect(sa, sb)));

      // commutativity of intersection (set level)
      array_t *ab = array_create(len, BIT_X);
      array_t *ba = array_create(len, BIT_X);
      const bool nab = array_isect(a, b, len, ab);
      const bool nba = array_isect(b, a, len, ba);
      CPPUNIT_ASSERT(nab == nba);
      if (nab) CPPUNIT_ASSERT(set_equal(cube_to_set(ab, len), cube_to_set(ba, len)));
      array_free(ab); array_free(ba);

      array_free(a); array_free(b);
    }
  }
}

// hs_isect(a,b) mutates a into a n b.
void OracleTest::test_hs_isect_oracle() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    for (size_t t = 0; t < trials_for(len); t++) {
      struct hs *a = rand_hs(rng, len, true);
      struct hs *b = rand_hs(rng, len, true);
      const PktSet expected = set_intersect(hs_to_set(a, len), hs_to_set(b, len));
      hs_isect(a, b);
      CPPUNIT_ASSERT(set_equal(hs_to_set(a, len), expected));
      hs_free(a); hs_free(b);
    }
  }
}

// hs_minus(a,b) mutates a into a \ b.
void OracleTest::test_hs_minus_oracle() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    for (size_t t = 0; t < trials_for(len); t++) {
      struct hs *a = rand_hs(rng, len, true);
      struct hs *b = rand_hs(rng, len, true);
      const PktSet expected = set_minus(hs_to_set(a, len), hs_to_set(b, len));
      hs_minus(a, b);
      CPPUNIT_ASSERT(set_equal(hs_to_set(a, len), expected));
      hs_free(a); hs_free(b);
    }
  }
}

// hs_cmpl(h) mutates h into its set complement.
void OracleTest::test_hs_cmpl_oracle() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    for (size_t t = 0; t < trials_for(len); t++) {
      struct hs *a = rand_hs(rng, len, true);
      const PktSet expected = set_complement(hs_to_set(a, len));
      hs_cmpl(a);
      CPPUNIT_ASSERT(set_equal(hs_to_set(a, len), expected));
      hs_free(a);
    }
  }
}

// hs_add_hs(dst,src) unions src into dst.
void OracleTest::test_hs_add_oracle() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    for (size_t t = 0; t < trials_for(len); t++) {
      struct hs *a = rand_hs(rng, len, true);
      struct hs *b = rand_hs(rng, len, true);
      const PktSet expected = set_union(hs_to_set(a, len), hs_to_set(b, len));
      hs_add_hs(a, b);
      CPPUNIT_ASSERT(set_equal(hs_to_set(a, len), expected));
      hs_free(a); hs_free(b);
    }
  }
}

// hs_compact(h) must not change the represented packet set (membership
// invariance). This directly guards the over-merge regression class (item 1h).
void OracleTest::test_hs_compact_invariance() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    for (size_t t = 0; t < trials_for(len); t++) {
      struct hs *a = rand_hs(rng, len, true);
      const PktSet before = hs_to_set(a, len);
      hs_compact(a);
      CPPUNIT_ASSERT(set_equal(hs_to_set(a, len), before));
      hs_free(a);
    }
  }
}

// De Morgan: ~(a n b) == ~a u ~b, compared in the concrete domain.
void OracleTest::test_hs_demorgan() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    for (size_t t = 0; t < trials_for(len); t++) {
      struct hs *a = rand_hs(rng, len, true);
      struct hs *b = rand_hs(rng, len, true);

      // lhs = ~(a n b)
      struct hs *lhs = hs_copy_a(a);
      hs_isect(lhs, b);
      hs_cmpl(lhs);

      // rhs = ~a u ~b
      struct hs *na = hs_copy_a(a); hs_cmpl(na);
      struct hs *nb = hs_copy_a(b); hs_cmpl(nb);
      hs_add_hs(na, nb);

      CPPUNIT_ASSERT(set_equal(hs_to_set(lhs, len), hs_to_set(na, len)));

      hs_free(lhs); hs_free(na); hs_free(nb);
      hs_free(a); hs_free(b);
    }
  }
}

// a \ b == a n ~b, compared in the concrete domain.
void OracleTest::test_hs_minus_eq_isect_cmpl() {
  printf("\n");
  std::mt19937 rng = make_rng();
  for (size_t li = 0; li < 2; li++) {
    const size_t len = LENS[li];
    for (size_t t = 0; t < trials_for(len); t++) {
      struct hs *a = rand_hs(rng, len, true);
      struct hs *b = rand_hs(rng, len, true);

      struct hs *lhs = hs_copy_a(a);
      hs_minus(lhs, b);

      struct hs *rhs = hs_copy_a(a);
      struct hs *nb = hs_copy_a(b); hs_cmpl(nb);
      hs_isect(rhs, nb);

      CPPUNIT_ASSERT(set_equal(hs_to_set(lhs, len), hs_to_set(rhs, len)));

      hs_free(lhs); hs_free(rhs); hs_free(nb);
      hs_free(a); hs_free(b);
    }
  }
}

// Regression (bug #C4): an explicit universe (xxxxxxxx) cube among other
// positive cubes must make the complement empty. The old hs_cmpl `continue`d
// past it, yielding ~c1 & ~c3 (236 packets) instead of empty. hs_compact does
// not remove the redundant universe cube, so this is reachable on compacted hs.
void OracleTest::test_hs_cmpl_universe_regression() {
  printf("\n");
  struct hs *h = hs_create(1);
  hs_add(h, array_from_str("xx10x10x"));
  hs_add(h, array_from_str("xxxxxxxx"));
  hs_add(h, array_from_str("00011x0x"));
  CPPUNIT_ASSERT(set_count(hs_to_set(h, 1)) == 256);  // the list covers everything
  hs_cmpl(h);
  CPPUNIT_ASSERT(set_is_empty(hs_to_set(h, 1)));
  hs_free(h);
}

// Regression (bug #C5): hs_add_hs must handle a source carrying diff lists.
// The old code appended the diff cubes via vec_append(...,true), desynchronising
// the elems/diff arrays and crashing. Result must be the set union.
void OracleTest::test_hs_add_hs_diff_source_regression() {
  printf("\n");
  struct hs *a = hs_create(1);
  hs_add(a, array_from_str("0xxxxxxx"));          // {0..127}
  struct hs *b = hs_create(1);
  hs_add(b, array_from_str("1xxxxxxx"));          // {128..255}
  array_t *d = array_from_str("10000000");
  hs_diff(b, d); array_free(d);                   // b = {129..255}
  const PktSet expected = set_union(hs_to_set(a, 1), hs_to_set(b, 1));
  hs_add_hs(a, b);                                // must not crash
  CPPUNIT_ASSERT(set_equal(hs_to_set(a, 1), expected));
  CPPUNIT_ASSERT(set_count(hs_to_set(a, 1)) == 255);  // everything but 128
  hs_free(a); hs_free(b);
}
