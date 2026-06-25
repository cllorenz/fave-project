/*
  Copyright 2026, Claas Lorenz. This file is licensed under GPL v2 plus
  a special exception, as described in included LICENSE_EXCEPTION.txt.

  Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

/*
 * Independent "ground-truth" oracle for the headerspace primitives
 * (array_t cubes and hs header spaces).
 *
 * The point of an oracle is to be INDEPENDENT of the code under test: it must
 * not reuse the very set-algebra functions (array_isect/array_cmpl/hs_minus/
 * hs_cmpl/array_is_sub_eq/...) whose correctness it is meant to certify. So
 * this oracle works entirely in the CONCRETE packet domain:
 *
 *   - a cube (array_t) or header space (hs) over `len` bytes is decoded into a
 *     characteristic vector over all 2^(8*len) concrete packets, using only the
 *     documented 2-bit-per-logical-bit memory layout (verified against array.c:
 *     logical bit i lives at physical bits 2i/2i+1 of the array_t word stream,
 *     and its value equals the bit_val enum: Z=00, 0=01, 1=10, X=11);
 *   - set operations (union/intersect/minus/complement/subset/equality) are
 *     computed directly on those characteristic vectors.
 *
 * Tests then run the real API operation, decode its RESULT the same way, and
 * compare against the concrete operation. A bug in e.g. array_isect cannot be
 * masked, because the oracle never calls array_isect.
 *
 * The decoder relies only on the bit layout and on the pure (de)serialization
 * helpers array_create/array_from_str. To keep len*8 <= 32 (a single array_t
 * word) and the universe small, only len in {1,2} is used.
 */

#ifndef HEADERSPACE_TEST_ORACLE_UTIL_H_
#define HEADERSPACE_TEST_ORACLE_UTIL_H_

#include <cstdint>
#include <cstddef>
#include <vector>
#include <string>
#include <random>

extern "C" {
#include "../array.h"
#include "../hs.h"
}

namespace hs_oracle {

// Characteristic vector over [0, 2^(8*len)) packets; s[p] != 0 iff p is in set.
typedef std::vector<char> PktSet;

inline size_t universe_size(size_t len) { return (size_t)1 << (len * 8); }

// Number of logical bits packed into one array_t word (2 physical bits each).
inline size_t logbits_per_word() { return (sizeof(array_t) * 8) / 2; }

// Decode logical bit `i` of cube `a` into the bit_val enum (Z/0/1/X), reading
// the raw 2-bit slot directly -- independent of any array.c function.
inline int oracle_get_bit(const array_t *a, size_t i) {
  const size_t word = i / logbits_per_word();
  const size_t off  = (i % logbits_per_word()) * 2;
  const array_t w = a[word];
  const int lo = (int)((w >> off) & 1u);
  const int hi = (int)((w >> (off + 1)) & 1u);
  return lo | (hi << 1);  // BIT_Z=0, BIT_0=1, BIT_1=2, BIT_X=3
}

// Construct the cube for a single concrete packet `p` (all bits fixed to 0/1),
// using only array_create + the raw layout. By construction this decodes back
// to exactly {p}, which gives the self-consistency tests a fixed reference.
inline array_t *oracle_make_singleton(uint32_t p, size_t len) {
  array_t *a = array_create(len, BIT_X);
  const size_t nbits = len * 8;
  for (size_t i = 0; i < nbits; i++) {
    const int val = ((p >> i) & 1u) ? BIT_1 : BIT_0;
    const size_t word = i / logbits_per_word();
    const size_t off  = (i % logbits_per_word()) * 2;
    a[word] &= ~((array_t)3 << off);
    a[word] |= ((array_t)val << off);
  }
  return a;
}

// Decode a cube into the set of concrete packets it matches. A Z bit makes the
// cube empty; an X bit is a free variable; 0/1 are fixed.
inline PktSet cube_to_set(const array_t *a, size_t len) {
  const size_t U = universe_size(len);
  PktSet s(U, 0);
  if (!a) return s;  // a NULL array is the empty set by convention
  const size_t nbits = len * 8;
  uint32_t fixed_mask = 0, fixed_val = 0;
  for (size_t i = 0; i < nbits; i++) {
    const int b = oracle_get_bit(a, i);
    if (b == BIT_Z) return s;  // contradiction -> empty
    if (b == BIT_0) { fixed_mask |= (1u << i); }
    else if (b == BIT_1) { fixed_mask |= (1u << i); fixed_val |= (1u << i); }
    // BIT_X -> unconstrained
  }
  for (uint32_t p = 0; p < U; p++)
    if ((p & fixed_mask) == fixed_val) s[p] = 1;
  return s;
}

// Decode an hs into a concrete set:
//   non-NEW_HS: union_i ( elems[i] \ union_j diff[i][j] )
//   NEW_HS:     ( union_i elems[i] ) \ ( union_j diff[j] )
inline PktSet hs_to_set(const struct hs *h, size_t len) {
  const size_t U = universe_size(len);
  PktSet s(U, 0);
  if (!h) return s;
  const struct hs_vec *v = &h->list;
#ifdef NEW_HS
  for (size_t i = 0; i < v->used; i++) {
    PktSet c = cube_to_set(v->elems[i], len);
    for (size_t p = 0; p < U; p++) if (c[p]) s[p] = 1;
  }
  const struct hs_vec *d = &h->diff;
  for (size_t j = 0; j < d->used; j++) {
    PktSet dc = cube_to_set(d->elems[j], len);
    for (size_t p = 0; p < U; p++) if (dc[p]) s[p] = 0;
  }
#else
  for (size_t i = 0; i < v->used; i++) {
    PktSet c = cube_to_set(v->elems[i], len);
    if (v->diff) {
      const struct hs_vec *d = &v->diff[i];
      for (size_t j = 0; j < d->used; j++) {
        PktSet dc = cube_to_set(d->elems[j], len);
        for (size_t p = 0; p < U; p++) if (dc[p]) c[p] = 0;
      }
    }
    for (size_t p = 0; p < U; p++) if (c[p]) s[p] = 1;
  }
#endif
  return s;
}

// --- concrete set algebra (the reference implementation) --------------------

inline PktSet set_complement(const PktSet &a) {
  PktSet r(a.size());
  for (size_t i = 0; i < a.size(); i++) r[i] = a[i] ? 0 : 1;
  return r;
}
inline PktSet set_intersect(const PktSet &a, const PktSet &b) {
  PktSet r(a.size());
  for (size_t i = 0; i < a.size(); i++) r[i] = (a[i] && b[i]) ? 1 : 0;
  return r;
}
inline PktSet set_union(const PktSet &a, const PktSet &b) {
  PktSet r(a.size());
  for (size_t i = 0; i < a.size(); i++) r[i] = (a[i] || b[i]) ? 1 : 0;
  return r;
}
inline PktSet set_minus(const PktSet &a, const PktSet &b) {
  PktSet r(a.size());
  for (size_t i = 0; i < a.size(); i++) r[i] = (a[i] && !b[i]) ? 1 : 0;
  return r;
}
inline bool set_is_empty(const PktSet &a) {
  for (size_t i = 0; i < a.size(); i++) if (a[i]) return false;
  return true;
}
inline bool set_equal(const PktSet &a, const PktSet &b) { return a == b; }
// True iff a is a subset of (or equal to) b.
inline bool set_subset_eq(const PktSet &a, const PktSet &b) {
  for (size_t i = 0; i < a.size(); i++) if (a[i] && !b[i]) return false;
  return true;
}
inline size_t set_count(const PktSet &a) {
  size_t n = 0;
  for (size_t i = 0; i < a.size(); i++) if (a[i]) n++;
  return n;
}

// --- random generators ------------------------------------------------------

inline std::string rand_cube_str(std::mt19937 &rng, size_t len, bool allow_z) {
  static const char *alpha_z = "01xz";
  static const char *alpha   = "01x";
  const char *al = allow_z ? alpha_z : alpha;
  const int n = allow_z ? 4 : 3;
  std::string s;
  for (size_t b = 0; b < len; b++) {
    if (b) s += ',';
    for (int k = 0; k < 8; k++) s += al[rng() % n];
  }
  return s;
}

inline array_t *rand_cube(std::mt19937 &rng, size_t len, bool allow_z) {
  const std::string s = rand_cube_str(rng, len, allow_z);
  return array_from_str(s.c_str());
}

// A random hs: 1..3 positive cubes, optionally with 1..2 subtracted cubes.
// Positive cubes are non-empty (no z) so the list elements are meaningful.
inline struct hs *rand_hs(std::mt19937 &rng, size_t len, bool allow_diff) {
  struct hs *h = hs_create(len);
  const int k = 1 + (int)(rng() % 3);
  for (int i = 0; i < k; i++) hs_add(h, rand_cube(rng, len, false));  // hs takes ownership
  if (allow_diff && (rng() % 2)) {
    const int d = 1 + (int)(rng() % 2);
    for (int i = 0; i < d; i++) {
      array_t *dc = rand_cube(rng, len, false);
      hs_diff(h, dc);   // copies dc
      array_free(dc);
    }
  }
  return h;
}

} // namespace hs_oracle

#endif // HEADERSPACE_TEST_ORACLE_UTIL_H_
