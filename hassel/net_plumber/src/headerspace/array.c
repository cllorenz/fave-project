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

#define SIZE(L) ( DIV_ROUND_UP (2 * (L), sizeof (array_t)) )

/* If using anything larger than 64-bit, these need to be changed. */
#define EVEN_MASK ( (array_t) 0xaaaaaaaaaaaaaaaaull )
#define ODD_MASK  ( (array_t) 0x5555555555555555ull )

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
  array_t tmp = a & (a >> 1) & mask & ODD_MASK;
  return __builtin_popcountll (tmp);
}

array_t *
array_create (size_t len, enum bit_val val)
{
  size_t alen = SIZE (len);
  /* TODO: Alignment */
  array_t *res = xmalloc (alen * sizeof *res);
  if (val != BIT_UNDEF) memset (res, val * 0x55, 2 * len);
  memset ((uint8_t *) res + 2 * len, 0xff, alen * sizeof *res - 2 * len);
  return res;
}

array_t *
array_resize (array_t* ptr, size_t oldlen, size_t newlen)
{
  if (oldlen >= newlen)
    return ptr;

  if (!ptr)
    exit(EXIT_FAILURE);

  size_t oldalen = SIZE (oldlen);
  size_t newalen = SIZE (newlen);

  array_t* res = realloc (ptr, newalen*8);
  if (!res)
    exit(EXIT_FAILURE);

  memset ((uint8_t *)res + oldalen*8, 0xff, (newalen - oldalen)*8);
  return res;
}

void
array_free (array_t *a)
{ if (!a) return; free (a); }

array_t *
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
  if (!a) return NULL;

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

bool
array_has_x (const array_t *a, size_t len)
{
  for (size_t i = 0; i < SIZE (len); i++) {
    array_t tmp = a[i];
    // for the last round mask incomplete bits in array_t
    if (i == SIZE (len) - 1) tmp &= (-1ull >> ((len % (sizeof *a / 2)*16)));
    if (has_x (tmp)) return true;
  }
  return false;
}

bool
array_has_z (const array_t *a, size_t len)
{
  for (size_t i = 0; i < SIZE (len); i++) {
    array_t tmp = a[i];
    // for the last round mask incomplete bits in array_t
    //if (i == SIZE (len) - 1) tmp &= (-1ull >> ((len % (sizeof *a / 2)*16)));
    if (has_z (tmp)) return true;
  }
  return false;
}

bool
array_is_eq (const array_t *a, const array_t *b, size_t len)
{
    // trivial case where both operands are NULL
    if (!a && !b) return true;
    // trivial case where one operand is NULL
    else if (!a || !b) return false;

    return !memcmp (a, b, SIZE (len) * sizeof *a);
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
        array_t diff = a[i] ^ b[i];

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
array_one_bit_subtract (array_t *a, array_t *b, size_t len ) {
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

  bool a_z = array_has_z(a, len);
  bool b_z = array_has_z(b, len);

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

  bool b1 = array_is_sub(a, tmp, len);
  bool b2 = array_is_sub(b, tmp, len);
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


#ifdef USE_DEPRECATED
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


void
array_and (const array_t *a, const array_t *b, size_t len, array_t *res)
{
  for (size_t i = 0; i < SIZE (len); i++)
    res[i] = ((a[i] | b[i]) & ODD_MASK) | (a[i] & b[i] & EVEN_MASK);
}


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


bool
array_isect (const array_t *a, const array_t *b, size_t len, array_t *res)
{
  for (size_t i = 0; i < SIZE (len); i++) {
    res[i] = a[i] & b[i];
    if (has_z (res[i])) return false;
  }
  return true;
}

void
array_not (const array_t *a, size_t len, array_t *res)
{
  for (size_t i = 0; i < SIZE (len); i++)
    res[i] = ((a[i] >> 1) & ODD_MASK) | ((a[i] << 1) & EVEN_MASK);
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
array_rewrite (array_t *a, const array_t *mask, const array_t *rewrite, size_t len)
{
  size_t n = 0;
  for (size_t i = 0; i < SIZE (len); i++) {
    n += x_count (a[i], mask[i]);
    a[i] = (((a[i] | mask[i]) & rewrite[i]) & ODD_MASK) |
           (((a[i] & mask[i]) | rewrite[i]) & EVEN_MASK);
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

  array_t *res = array_create (len, BIT_UNDEF);
  if (!array_isect (a, b, len, res)) {
    array_free (res);
    return NULL;
  }
  return res;
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
        array_t diff = a[i] ^ b[i];
        // if x or z differ (indicated by 0 or 1) abort merge
        if (has_zero(diff) || has_one(diff)) return NULL;

        // e.g., 1001 & 1000 -> 100z
        array_t isect = a[i] & b[i];

        // e.g., zzzx | 100z -> 100x
        res[i] = isect | diff;
        // count the number of different 0 and 1
        // e.g., 1001 ^ 1000 -> zzzx -> 1
        cnt += x_count(diff, -1);
        // XXX: shortcut possibly leads to jump based on unitialized value
        //      in array_has_z()
        //if (cnt > 1) break;
    }

    if (array_has_z(res, len)) return NULL;
    if (cnt <= 1) return array_copy(res, len);

    return NULL;
}
