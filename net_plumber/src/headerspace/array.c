/*
  Copyright 2012, Stanford University. This file is licensed under GPL v2 plus
  a special exception, as described in included LICENSE_EXCEPTION.txt.

  Author: mchang@cs.stanford.com (Michael Chang)
          peyman.kazemian@gmail.com (Peyman Kazemian)
          kiekhebe@uni-potsdam.de (Sebastian Kiekheben)
          cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#include "array.h"
#include <limits.h>

#define SIZE(L) ARRAY_BITS(L)

/* If using anything larger than 64-bit, these need to be changed. */
#define EVEN_MASK ( (array_t) 0xaaaaaaaaaaaaaaaaull )
#define ODD_MASK  ( (array_t) 0x5555555555555555ull )

#define ALL_X ((array_t) 0xffffffffffffffffull)

static inline bool
has_x (array_t x)
{ return x & (x >> 1) & ODD_MASK; }

static inline bool
has_z (array_t x)
{ return has_x (~x); }

static inline bool
has_zero (array_t x)
{
    // 11100100 x10z
    // 01000100 0z0z <- x & ODD_MASK

    // 01110010 0xz1 <- x >> 1
    // 01010000 00zz <- (x >> 1) & ODD_MASK
    // 10101111 11xx <- ~((x >> 1) & ODD_MASK)

    // 00000100 zz0z  <- (x & ODD_MASK) & ~((x >> 1) & ODD_MASK)
    return (x & ODD_MASK) & ~((x >> 1) & ODD_MASK);
}

static inline bool
has_one (array_t x)
{ return has_zero (~x); }

/* Convert X from two-bit representation to integer and writes string to OUT.
   X must contain only 0s and 1s (no x or z) or be all x. OUT must have space
   for 5 chars. Returns number of chars written. */
static size_t
int_str (uint16_t x, char *out)
{
  if (x == UINT16_MAX) return sprintf (out, "DX,");
  x = (x >> 1) & 0x5555;
  x = (x | (x >> 1)) & 0x3333;
  x = (x | (x >> 2)) & 0x0f0f;
  x = (x | (x >> 4)) & 0x00ff;
  return sprintf (out, "D%d,", x);
}

static inline size_t
x_count (array_t a, array_t mask)
{
#ifdef STRICT_RW
/*
 b00011011 <- a = z01x
 b00110110 <- (a << 1) = zx01
 b10101010 <- m = 1111
 b10101010 <- EVEN_MASK
 b00000010 <- zzz1

 b00011011 <- a = z01x
 b00110110 <- (a << 1) = zx01
 b01010101 <- m = 0000
 b10101010 <- EVEN_MASK
 b00000000 <- zzzz
 */

  const array_t tmp = a & (a << 1) & mask & EVEN_MASK;
#else
/*
 b00011011 <- a = z01x
 b00001101 <- (a >> 1) = zzx0
 b10101010 <- m = 1111
 b01010101 <- ODD_MASK
 b00000000 <- zzzz

 b00011011 <- a = z01x
 b00001101 <- (a >> 1) = zzx0
 b01010101 <- m = 0000
 b01010101 <- ODD_MASK
 b00000001 <- zzz0
 */
  array_t tmp = a & (a >> 1) & mask & ODD_MASK;
#endif
  return __builtin_popcountll (tmp);
}

inline void
array_init (array_t *a, size_t len, enum bit_val val) {
  size_t alen = SIZE (len);
  if (val != BIT_UNDEF) memset (a, val * 0x55, 2 * len);
  memset ((uint8_t *) a + 2 * len, 0xff, alen * sizeof *a - 2 * len);
}

array_t *
array_create (size_t len, enum bit_val val)
{
  size_t alen = SIZE (len);
  /* TODO: Alignment */
  array_t *res = xmalloc (alen * sizeof *res);
  array_init(res, len, val);
  return res;
}

array_t *
array_resize (array_t* ptr, size_t oldlen, size_t newlen)
{
    return array_generic_resize (ptr, oldlen, newlen, BIT_X);
}


inline array_t *
array_generic_resize (array_t* ptr, size_t oldlen, size_t newlen, enum bit_val val)
{
  if (oldlen >= newlen)
    return ptr;

  if (!ptr)
    exit(EXIT_FAILURE);

  const size_t newalen = SIZE (newlen);

  array_t* res = realloc (ptr, newalen*8);
  if (!res)
    exit(EXIT_FAILURE);

  static const uint8_t val_bytes[4] = { 0x00, 0x55, 0xaa, 0xff };
  memset ((uint8_t *)res + oldlen*2, val_bytes[val], (newalen*8 - oldlen*2));

  return res;
}


void
array_free (array_t *a)
{ if (a) free (a); }

inline array_t *
array_copy (const array_t *a, size_t len)
{
  array_t *res = array_create (len, BIT_UNDEF);
  memcpy (res, a, 2 * len);
  return res;
}

array_t *
array_from_str (const char *s)
{
  bool commas = strchr (s, ',');
  size_t div = CHAR_BIT + commas;
  size_t len = strlen (s) + commas;
  assert (len % div == 0);
  len /= div;

  const char *cur = s;
  array_t *res = array_create (len, BIT_UNDEF);
  uint8_t *rcur = (uint8_t *) res;
  for (size_t i = 0; i < 2 * len; i++) {
    uint8_t tmp = 0;
    for (size_t j = 0; j < CHAR_BIT / 2; j++, cur++) {
      enum bit_val val;
      switch (*cur) {
        case 'z': case 'Z': val = BIT_Z; break;
        case '0': val = BIT_0; break;
        case '1': val = BIT_1; break;
        case 'x': case 'X': val = BIT_X; break;
        default: errx (1, "Invalid character '%c' in \"%s\".", *cur, s);
      }
      tmp <<= 2;
      tmp |= val;
    }
    *rcur++ = tmp;
    if (commas && (i % 2)) { assert (!*cur || *cur == ','); cur++; }
  }
  return res;
}

char *
array_to_str (const array_t *a, size_t len, bool decimal)
{
  if (!a) return xstrdup("nil");

  size_t slen = len * (CHAR_BIT + 1);
  char buf[slen];
  char *cur = buf;
  const uint8_t *acur = (const uint8_t *) a;
  for (size_t i = 0; i < len; i++, acur += 2) {
    uint8_t tmp[] = {acur[0], acur[1]};
    uint16_t byte = tmp[0] << CHAR_BIT | tmp[1];
    if (decimal && (!has_x (byte) || byte == UINT16_MAX)) {
      cur += int_str (byte, cur);
      continue;
    }

    for (size_t j = 0; j < 2; j++) {
      char *next = cur + CHAR_BIT / 2 - 1;
      for (size_t k = 0; k < CHAR_BIT / 2; k++) {
        static char chars[] = "z01x";
        *next-- = chars[tmp[j] & BIT_X];
        tmp[j] >>= 2;
      }
      cur += CHAR_BIT / 2;
    }
    *cur++ = ',';
  }
  cur[-1] = 0;
  return xstrdup (buf);
}

void array_print(const array_t *a, size_t len, bool decimal) {
    char *a_s = array_to_str(a,len,decimal);
    fprintf(stdout,"%s\n",a_s);
    free(a_s);
}

bool array_all_x  (const array_t *a, size_t len)
{
  for (size_t i = 0; i < SIZE (len); i++)
    if (a[i] != ALL_X) return false;
  return true;
}

bool
array_has_x (const array_t *a, size_t len)
{
  for (size_t i = 0; i < SIZE (len); i++) {
    array_t tmp = a[i];
    // for the last round mask incomplete bits in array_t
    if (i == SIZE (len) - 1) {
      const size_t set_bits = (len % (sizeof *a / 2)) * 16;
      // unset leading bits while keeping originally set bits
      tmp &= (-1ull >> ((sizeof *a * 8) - set_bits));
    }
    if (has_x (tmp)) return true;
  }
  return false;
}

inline bool
array_has_z (const array_t *a, size_t len)
{
  for (size_t i = 0; i < SIZE (len); i++) {
    array_t tmp = a[i];
    // for the last round mask incomplete bits in array_t
    if (i == SIZE (len) - 1) {
      const size_t set_bits = (len % (sizeof *a / 2)) * 16;
      // set leading bits while keeping originally set bits
      tmp |= ((-1ull >> set_bits) << set_bits);
    }
    if (has_z (tmp)) return true;
  }
  return false;
}

bool
array_has_isect(const array_t *a, const array_t *b, size_t len) {
    array_t tmp[SIZE(len)];
    return array_isect(a, b, len, &tmp);
}

inline bool
array_is_empty (const array_t *a, size_t len)
{
    return !a;
}

bool
array_is_eq (const array_t *a, const array_t *b, size_t len)
{
    // trivial case where both operands are NULL
    if (!a && !b) return true;
    // trivial case where one operand is NULL
    else if (!a || !b) return false;

#ifdef STRICT_RW
    return !memcmp (a, b, len * 2);
#else
    return !memcmp (a, b, SIZE (len) * sizeof *a);
#endif
}

bool
array_is_sub (const array_t *a, const array_t *b, size_t len)
{
    bool a_z = !a;
    bool b_z = !b;

    // trivial case where both operands are NULL (fast check)
    if (a_z && b_z) return false;

    if (a) a_z |= array_has_z(a, len);
    if (b) b_z |= array_has_z(b, len);

    // trivial case where both operands are empty (slower check)
    if (a_z && b_z) return false;

    // trivial case where only the second operand is empty
    else if (!a_z && b_z) return false;
    // trivial case where only the first operand is empty
    else if (a_z && !b_z) return true;

    return !array_is_eq(a,b,len) && array_is_sub_eq(a,b,len);
}

bool
array_is_sub_eq (const array_t *a, const array_t *b, size_t len)
{
    // trivial case where both operands are NULL
    if (!a && !b) return true;
    // trivial case where only the second operand is NULL
    else if (a && !b) return false;
    // trivial case where only the first operand is NULL
    else if (!a && b) return true;

    for (size_t i = 0; i < SIZE(len); i++) {
        // a^b -> shows differences between a and b
        // if no bit is set a and b are equal
        const array_t diff = a[i] ^ b[i];;

        if (!diff) continue;

        // f = (b << 1) & EVEN_MASK -> indicates first bit of an x in b
        // s = (b >> 1) & ODD_MASK -> indicates second bit of an x in b
        array_t f_b = b[i] & (b[i] << 1) & EVEN_MASK;
        array_t s_b = b[i] & (b[i] >> 1) & ODD_MASK;

        // f | g -> vector of all x in b
        array_t set_x = f_b | s_b;

        // shows if all differing bits between a and b are covered by x in b
        array_t res = diff & ~set_x;

        if (res) return false;
    }
    return true;
}

size_t
array_one_bit_subtract (const array_t *a, array_t *b, size_t len ) {
  size_t total_diff = 0;
  array_t diffs[len];
  for (size_t i = 0; i < SIZE (len); i++) {
    // store bitwise difference into temporary array
    // (trinary: z -> z, x -> z, 0 -> 1, 1 -> 0)
    array_t c = b[i] & ~a[i];
    diffs[i] = c;
    // count set bits (from trinary zeroes and ones)
    total_diff += __builtin_popcountll(c);
    if (total_diff > 1) return total_diff;
  }
  // if only one bit differs -> subtract one from b
  if (total_diff == 1) {
    for (size_t i = 0; i < SIZE (len); i++) {
      if (diffs[i]) {
        // if bit is in array segment and one or x -> bit is set to one
        // else bit is set to zero
        if (diffs[i] & EVEN_MASK)
          b[i] = b[i] & ~(diffs[i] >> 1);
        else
          b[i] = b[i] & ~(diffs[i] << 1);
      }
    }
  }
  return total_diff;
}

#ifdef WITH_EXTRA_NEW
#define UNUSED(x) (void)(x)

void
array_combine(array_t **_a, array_t **_b, array_t **extra,
              const array_t* mask, size_t len) {
  UNUSED(mask);

  array_t *a = *_a;
  array_t *b = *_b;

  const bool a_z = array_has_z(a, len);
  const bool b_z = array_has_z(b, len);

  if (a_z && b_z) {
    array_free(a); array_free(b);
    *_a = NULL; *_b = NULL; *extra = NULL;
    return;
  } else if (a_z) {
    array_free(a);
    *_a = NULL; *extra = NULL;
    return;
  } else if (b_z) {
    array_free(b);
    *_b = NULL; *extra = NULL;
    return;
  }

  if (array_is_eq(a, b, len) || array_is_sub(b, a, len)) {
    array_free(b);
    *_b = NULL; *extra = NULL;
    return;
  } else if (array_is_sub(a, b, len)) {
    array_free(a);
    *_a = NULL; *extra = NULL;
    return;
  }

  array_t *tmp = array_merge(a, b, len);
  if (!tmp) { *extra = NULL; return; }

  const bool b1 = array_is_sub(a, tmp, len);
  const bool b2 = array_is_sub(b, tmp, len);
  // e.g. 10x0 U 10x1 --> 10xx
  if (b1 && b2) {
    array_free(a);
    array_free(b);
    *_a = NULL; *_b = NULL;
    *extra = tmp;
  }
  // e.g. 1001 U 1xx0 --> 100x U 1xx0
  else if (b1) { array_free(a); *_a = NULL; *extra = tmp; }
    // e.g. 1xx0 U 1001 --> 1xx0 U 100x
  else if (b2) { array_free(b); *_b = NULL; *extra = tmp; }
    // e.g. 10x1 U 1x00 --> 10x1 U 1x00 U 100X
  else {*extra = tmp;}
}

#else

void
array_combine(array_t **_a, array_t **_b, array_t **extra,
              const array_t *mask, size_t len) {
  array_t *a = *_a;
  array_t *b = *_b;
  bool equal = true;
  bool aSubb = true;
  bool bSuba = true;
  size_t diff_count = 0;
  array_t tmp[SIZE (len)];
  for (size_t i = 0; i < SIZE (len); i++) {
    if (equal && a[i] != b[i]) equal = false;
    if (!equal && bSuba && (b[i] & ~a[i])) bSuba = false;
    if (!equal && aSubb && (a[i] & ~b[i])) aSubb = false;
    if (mask && diff_count <= 1) {
      if (bSuba) tmp[i] = b[i];
      else if (aSubb) tmp[i] = a[i];
      else {
        array_t isect = a[i] & b[i];
        array_t diffs = ((isect | (isect >> 1)) & ODD_MASK) |
            ((isect | (isect << 1)) & EVEN_MASK);
        diffs = ~diffs;
        if (diffs & mask[i] & EVEN_MASK) {*extra = NULL; return;}
        size_t count = __builtin_popcountll(diffs) / 2;
        if (count == 0) tmp[i] = isect;
        else {
          diff_count += count;
          if (diff_count == 1) tmp[i] = isect | diffs;
        }
      }
    // in case of no combine, if no subset detected, return.
    } else if (!mask && !bSuba && !aSubb) {*extra = NULL; return;}
    // more than one non-intersecting bits - no combine.
    if (diff_count > 1) {*extra = NULL; return;}
  }
  // keep a if equal or b is subset of a
  if (equal || bSuba) { array_free(b); *_b = NULL; *extra = NULL;}
  // keep b if a is subset of b
  else if (aSubb) { array_free(a); *_a = NULL; *extra = NULL; }
  // keep b and a untouched if there is no merge. e.g. 100x u 1xx0
  else if (diff_count == 0) {*extra = NULL;}
  // or we will have a combine:
  else {
    bool b1 = array_is_sub(tmp,a,len);
    bool b2 = array_is_sub(tmp,b,len);
    // e.g. 10x0 U 10x1 --> 10xx
    if (b1 && b2) { array_free(a); array_free(b); *_a = NULL; *_b = NULL;
      *extra = array_copy(tmp,len); }
    // e.g. 1001 U 1xx0 --> 100x U 1xx0
    else if (b1) { array_free(a); *_a = NULL; *extra = array_copy(tmp,len);}
    // e.g. 1xx0 U 1001 --> 1xx0 U 100x
    else if (b2) { array_free(b); *_b = NULL; *extra = array_copy(tmp,len);}
    // e.g. 10x1 U 1x00 --> 10x1 U 1x00 U 100X
    else {*extra = array_copy(tmp,len);}
  }
}

#endif

#ifdef USE_DEPRECATED
enum bit_val
array_get_bit (const array_t *a, size_t byte, size_t bit)
{
  const uint8_t *p = (const uint8_t *) a;
  uint8_t x = p[2 * byte + bit / (CHAR_BIT / 2)];
  size_t shift = 2 * (CHAR_BIT / 2 - (bit % (CHAR_BIT / 2)) - 1);
  return x >> shift;
}
#endif


#ifdef USE_DEPRECATED
uint16_t
array_get_byte (const array_t *a, size_t byte)
{
  const uint8_t *p = (const uint8_t *) a;
  return (p[2 * byte] << CHAR_BIT) | p[2 * byte + 1];
}
#endif


#if defined(USE_DEPRECATED) || defined(NEW_HS)
void
array_set_bit (array_t *a, enum bit_val val, size_t byte, size_t bit)
{
  uint8_t *p = (uint8_t *) a;
  size_t idx = 2 * byte + bit / (CHAR_BIT / 2);
  size_t shift = 2 * (CHAR_BIT / 2 - (bit % (CHAR_BIT / 2)) - 1);
  uint8_t mask = BIT_X >> shift;
  p[idx] = (p[idx] & ~mask) | (val << shift);
}
#endif


#ifdef USE_DEPRECATED
void
array_set_byte (array_t *a, uint16_t val, size_t byte)
{
  uint8_t *p = (uint8_t *) a;
  p[2 * byte] = val >> CHAR_BIT;
  a[2 * byte + 1] = val & 0xff;
}
#endif

#if defined(USE_INV) || defined(USE_DEPRECATED)
void
array_and (const array_t *a, const array_t *b, size_t len, array_t *res)
{
/*
 00,00 -> 00  z,z -> z
 00,01 -> 00  z,0 -> z
 00,10 -> 10  z,1 -> 1
 00,11 -> 10  z,x -> 1
 01,00 -> 00  0,z -> z
 01,01 -> 01  0,0 -> 0
 01,10 -> 10  0,1 -> 1
 01,11 -> 11  0,x -> x
 10,00 -> 10  1,z -> 1
 10,01 -> 10  1,0 -> 1
 10,10 -> 10  1,1 -> 1
 10,11 -> 10  1,x -> 1
 11,00 -> 10  x,z -> 1
 11,01 -> 11  x,0 -> x
 11,10 -> 10  x,1 -> 1
 11,11 -> 11  x,x -> x

 z,z -> z

 0,* -> *
 *,0 -> *

 1,* -> 1
 *,1 -> 1

 z,x -> 1
 x,z -> 1

 x,x -> x
*/
  for (size_t i = 0; i < SIZE (len); i++)
    // first bit for either, second bit for both
    res[i] = ((a[i] | b[i]) & ODD_MASK) | (a[i] & b[i] & EVEN_MASK);
}
#endif//USE_INV


bool
array_cmpl (const array_t *a, size_t len, size_t *n, array_t **res)
{
  if (!a || array_has_z(a, len)) {
    res[0] = array_create(len, BIT_X);
    *n = 1;
    return *n;
  }

  *n = 0;
  for (size_t i = 0; i < SIZE (len); i++) {
    array_t cur = ~a[i];
    while (cur) {
      array_t next = cur & (cur - 1);
      array_t bit = cur & ~next;

      bit = ((bit >> 1) & ODD_MASK) | ((bit << 1) & EVEN_MASK);
      res[*n] = array_create (len, BIT_X);
      res[*n][i] &= ~bit;
      ++*n;
      cur = next;
    }
  }
  return *n;
}


#ifdef USE_DEPRECATED
bool
array_diff (const array_t *a, const array_t *b, size_t len, size_t *n, array_t **res)
{
  size_t n_cmpl;
  if (!array_cmpl (b, len, &n_cmpl, res)) return false;

  *n = 0;
  for (size_t i = 0; i < n_cmpl; i++)
    if (array_isect (a, res[i], len, res[*n])) ++*n;
  for (size_t i = *n; i < n_cmpl; i++)
    array_free (res[i]);
  return *n;
}
#endif


inline bool
array_isect (const array_t *a, const array_t *b, size_t len, array_t *res)
{
  if (!a || !b) return false;

  for (size_t i = 0; i < SIZE (len); i++) {
    res[i] = a[i] & b[i];
    if (has_z (res[i])) return false;
  }
  return true;
}

inline bool
array_isect_arr_i (array_t *a, const array_t *b, size_t len) {
  if (!a || !b) return false;

  for (size_t i = 0; i < SIZE (len); i++) {
    a[i] &= b[i];
    if (has_z (a[i])) return false;
  }

  return true;
}

void
array_not (const array_t *a, size_t len, array_t *res)
{
/*
 a  = z01x

b00011011
b00001101 -> zzx0

 a >> 1    = zzx0
 OM        = 1111
 first_bit = zz1z

b00011011
b00110110 -> zx01

 a << 1     = zx01
 EM         = 0000
 second_bit = z00z

 first_bit | second_bit = z0xz XXX: wtf!!!
 */

  for (size_t i = 0; i < SIZE (len); i++) {
#ifdef STRICT_RW
    res[i] = ~a[i];

    //const array_t equals   = (a[i] ^ (a[i] >> 1)) & EVEN_MASK;
    //const array_t differs  = ~(a[i] ^ (a[i] >> 1)) & EVEN_MASK;
    //res[i] = (equals | a[i]) | (differs | ~a[i]);
#else
    res[i] = ((a[i] >> 1) & ODD_MASK) | ((a[i] << 1) & EVEN_MASK);
#endif
  }
}


#ifdef USE_DEPRECATED
void
array_or (const array_t *a, const array_t *b, size_t len, array_t *res)
{
  for (size_t i = 0; i < SIZE (len); i++)
    res[i] = (a[i] & b[i] & ODD_MASK) | ((a[i] | b[i]) & EVEN_MASK);
}
#endif


/* Rewrite A using MASK and REWRITE. Returns number of x's in result. */
size_t
array_rewrite (array_t *a, const array_t *mask, const array_t *rewrite, const size_t len)
{
#ifdef STRICT_RW
  ;//assert (!array_has_x(mask, len) && !array_has_z(mask, len));
#endif

  size_t n = 0; // counts the number of overwritten wildcards
  for (size_t i = 0; i < SIZE (len); i++) {
    n += x_count (a[i], mask[i]);
#ifdef STRICT_RW

/*
 A 0 in the mask means that the bit should be kept whereas a 1 means it should
 be rewritten.

 Example:

 OM = 1111
 EM = 0000

 a      = z01x
 m      = 1100
 rw     = x1z0

 result = x11x

 a &             = z01x
 m << 1 &        = 0z11
 OM              = 1111
 -> first_bit_a  = zz11


 a &             = z01x
 m &             = 1100
 EM              = 0000
 -> second_bit_a = zzz0

 -> masked_a     = zz1x


 rw &             = x1z0
 m &              = 1100
 OM               = 1111
 -> first_bit_rw  = 11zz

 rw &             = x1z0
 m >> 1 &         = 00z1
 EM               = 0000
 -> second_bit_rw = 0zzz

 -> masked_rw     = x1zz

 -> masked_a | masked_rw = x11x
 */
    const array_t first_bit_a  = a[i] & mask[i] & ODD_MASK;
    const array_t second_bit_a = a[i] & (mask[i] << 1) & EVEN_MASK;
    const array_t masked_a = first_bit_a | second_bit_a;

    const array_t first_bit_rw  = rewrite[i] & (mask[i] >> 1) & ODD_MASK;
    const array_t second_bit_rw = rewrite[i] & mask[i] & EVEN_MASK;
    const array_t masked_rw = first_bit_rw | second_bit_rw;

    a[i] = masked_a | masked_rw;
#else
/*
 a1 = 101011xx
 a2 = 101011x1
 m  = 11111000
 rw = 00000111

 a1 | m = 1x1x1xxx
 (a1 | m) & rw = z0z0z111
 ((a1 | m) & rw) & OM = zzzzz111

 a1 & m = 1z1z1z00
 (a1 & m) | rw = x0x0x1xx
 ((a1 & m) | rw) & EM = 00000100

 zzzzz111 | 00000100 = 000001xx

 a2 | m = 1x1x1xxx
 (a2 | m) & rw = z0z0z111
 ((a2 | m) & rw) & OM = zzzzz111

 a2 & m = 1z1z1z0z
 (a2 & m) | rw = x0x0x1x1
 ((a2 & m) | rw) & EM = 00000z0z

 zzzzz111 | 00000z0z = 000001x1
 */
    const array_t first_bit  = (((a[i] | mask[i]) & rewrite[i]) & ODD_MASK);
    const array_t second_bit = (((a[i] & mask[i]) | rewrite[i]) & EVEN_MASK);

    a[i] = first_bit | second_bit;
#endif
  }
  return n;
}


#ifdef USE_DEPRECATED
size_t
array_x_count (const array_t *a, const array_t *mask, size_t len)
{
  size_t n = 0;
  for (size_t i = 0; i < SIZE (len); i++)
    n += x_count (a[i], mask[i]);
  return n;
}
#endif


#ifdef USE_DEPRECATED
array_t *
array_and_a (const array_t *a, const array_t *b, size_t len)
{
  array_t *res = array_create (len, BIT_UNDEF);
  array_and (a, b, len, res);
  return res;
}
#endif


array_t **
array_cmpl_a (const array_t *a, size_t len, size_t *n)
{
  array_t *tmp[len * CHAR_BIT];
  if (!array_cmpl (a, len, n, tmp)) return NULL;
  array_t **res = xmemdup (tmp, *n * sizeof *res);
  return res;
}


#ifdef USE_DEPRECATED
array_t **
array_diff_a (const array_t *a, const array_t *b, size_t len, size_t *n)
{
  array_t *tmp[len * CHAR_BIT];
  if (!array_diff (a, b, len, n, tmp)) return NULL;
  array_t **res = xmemdup (tmp, *n * sizeof *res);
  return res;
}
#endif


//TODO: Move HS optimization here
array_t *
array_isect_a (const array_t *a, const array_t *b, size_t len)
{
  if (!a || !b) return NULL;

  array_t tmp[ARRAY_BYTES (len) / sizeof (array_t)];
  if (!array_isect (a, b, len, &tmp)) return NULL;
  return xmemdup(tmp, sizeof(tmp));
}

array_t *
array_not_a (const array_t *a, size_t len)
{
  array_t *res = array_create (len, BIT_UNDEF);
  array_not (a, len, res);
  return res;
}


#ifdef USE_DEPRECATED
array_t *
array_or_a (const array_t *a, const array_t *b, size_t len)
{
  array_t *res = array_create (len, BIT_UNDEF);
  array_or (a, b, len, res);
  return res;
}
#endif


#ifdef USE_DEPRECATED
void
array_shift_left (array_t *a, size_t len, size_t start, size_t shift, enum bit_val val)
{
  assert (start % 4 == 0 && shift % 4 == 0);
  assert (start / 4 + shift / 4 <= len * 2);
  uint8_t *p = (uint8_t *) a;
  size_t bytes = 2 * len - start / 4 - shift / 4;
  memmove (p + start / 4, p + start / 4 + shift / 4, bytes);
  memset (p + 2 * len - shift / 4, 0x55 * val, shift / 4);
}
#endif


#ifdef USE_DEPRECATED
void
array_shift_right (array_t *a, size_t len, size_t start, size_t shift, enum bit_val val)
{
  assert (start % 4 == 0 && shift % 4 == 0);
  assert (start / 4 + shift / 4 <= len * 2);
  uint8_t *p = (uint8_t *) a;
  size_t bytes = 2 * len - start / 4 - shift / 4;
  memmove (p + start / 4 + shift / 4, p + start / 4, bytes);
  memset (p + start / 4, 0x55 * val, shift / 4);
}
#endif


array_t *
array_merge(const array_t *a, const array_t *b, size_t len) {
    if (!a || !b || array_has_z(a,len) || array_has_z(b,len)) return NULL;

    array_t res[SIZE(len)];
    size_t cnt = 0;
    for (size_t i = 0; i < SIZE(len); i++) {
        // e.g., 1001 ^ 1000 -> zzzx
        const array_t diff = a[i] ^ b[i];
        // if x or z differ (indicated by 0 or 1) abort merge
        if (has_zero(diff) || has_one(diff)) return NULL;

        // e.g., 1001 & 1000 -> 100z
        const array_t isect = a[i] & b[i];

        // e.g., zzzx | 100z -> 100x
        res[i] = isect | diff;
        // count the number of different 0 and 1
        // e.g., 1001 ^ 1000 -> zzzx -> 1
#ifdef STRICT_RW
        cnt += x_count(diff, EVEN_MASK);
#else
        cnt += x_count(diff, ODD_MASK);
#endif
    }

    if (array_has_z(res, len)) return NULL;
    if (cnt <= 1) return array_copy(res, len);

    return NULL;
}

#ifdef NEW_HS
void
array_set_bitmask(array_t *res, uint64_t bitmask, const array_t *positions, size_t len)
{

  for (size_t i = SIZE(len); i > 0; i--) {
    size_t one_cnt = __builtin_popcountll(positions[i]); // fetch amount of bits to set in this segment
    for (size_t j = one_cnt; j > 0; j--) {
      const size_t pos = __builtin_ctz(positions[i-1]) / 2; // get position of last set bit in position array

      const size_t byte = (i*8 + pos) / 8; // get byte position within the array
      const size_t bit = pos % 8;

      array_set_bit (res, (bitmask & 0x1) ? BIT_1 : BIT_0, byte, bit);

      bitmask >>= 1;
    }
  }
}
#endif


#ifdef NEW_HS
array_t **
array_unroll_superset(const array_t *subset, array_t *superset, size_t len, size_t *count)
{

  /*
    empty sub set -> ignore
    empty super set -> impossible, would not be super set then

    subset   = 0b011011 <- 01x
    superset = 0b111111 <- xxx
    result   = 0b011011 ^ 0b111111 = 0b100100 <- 10z
     -> one_count = 2

    0b011011
    0b111111
    -> (11x + 01x + 10x + 11x)
   */

  *count = 1;
  array_t **res;

  if (array_has_z(subset, len)) {
    res = (array_t **)malloc(sizeof(array_t **));
    *count = 1;
    res[0] = superset;
    return res;
  }

  size_t exp = 0;
  array_t tmp[SIZE(len)];
  for (size_t i = 0; i < SIZE(len); i++) {
    const array_t superpositions = subset[i] ^ superset[i];
    tmp[i] = superpositions;
    exp += __builtin_popcountll(superpositions);
  }

  res = (array_t **)malloc(sizeof(array_t **) * (1 << exp));

  for (size_t i = 0; i < (1 << exp); i++) {
    array_t *r = array_copy (subset, len);
    // set bits at superset positions using current counter as bitmask
    array_set_bitmask(r, i, &tmp, len);
    res[i] = r;
  }

  *count = 1 << exp;
  return res;
}
#endif
