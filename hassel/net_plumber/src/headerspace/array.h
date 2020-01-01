/*
  Copyright 2012, Stanford University. This file is licensed under GPL v2 plus
  a special exception, as described in included LICENSE_EXCEPTION.txt.

  Author: mchang@cs.stanford.com (Michael Chang)
          peyman.kazemian@gmail.com (Peyman Kazemian)
          kiekhebe@uni-potsdam.de (Sebastian Kiekheben)
*/

#ifndef _ARRAY_H_
#define _ARRAY_H_

#include "util.h"

#if __x86_64 || __amd64 || _M_X64
typedef uint64_t array_t;
#else
typedef uint32_t array_t;
#endif

#include "bitval.h"

#define ARRAY_BITS(L) ( DIV_ROUND_UP (2 * (L), sizeof (array_t)) )
#define ARRAY_BYTES(L) ( ROUND_UP (2 * (L), sizeof (array_t)) )

array_t *array_create   (size_t len, enum bit_val val);
array_t *array_resize   (array_t* ptr, size_t oldlen, size_t newlen);
void     array_free     (array_t *a);

array_t *array_copy     (const array_t *a, size_t len);
array_t *array_from_str (const char *s);
char    *array_to_str   (const array_t *a, size_t len, bool decimal);
void     array_print    (const array_t *a, size_t len, bool decimal);

bool array_all_x  (const array_t *a, size_t len);

bool array_has_x  (const array_t *a, size_t len);
bool array_has_z  (const array_t *a, size_t len);
bool array_has_isect    (const array_t *a, const array_t *b, size_t len);
bool array_is_empty (const array_t *a, size_t len);
bool array_is_eq  (const array_t *a, const array_t *b, size_t len);
/* True if B is a subset of A. */
bool array_is_sub (const array_t *a, const array_t *b, size_t len);
bool array_is_sub_eq(const array_t *a, const array_t *b, size_t len);

#ifdef USE_DEPRECATED
enum bit_val array_get_bit  (const array_t *a, size_t byte, size_t bit);
uint16_t     array_get_byte (const array_t *a, size_t byte);
void         array_set_bit  (array_t *a, enum bit_val val, size_t byte, size_t bit);
void         array_set_byte (array_t *a, uint16_t val, size_t byte);
#endif

void array_and     (const array_t *a, const array_t *b, size_t len, array_t *res);
bool array_cmpl    (const array_t *a, size_t len, size_t *n, array_t **res);
#ifdef USE_DEPRECATED
bool array_diff    (const array_t *a, const array_t *b, size_t len, size_t *n, array_t **res);
#endif
bool array_isect   (const array_t *a, const array_t *b, size_t len, array_t *res);
void array_not     (const array_t *a, size_t len, array_t *res);
#ifdef USE_DEPRECATED
void array_or      (const array_t *a, const array_t *b, size_t len, array_t *res);
#endif
size_t  array_rewrite (array_t *a, const array_t *mask, const array_t *rewrite, const size_t len);
size_t  array_x_count (const array_t *a, const array_t *mask, size_t len);  // counts number of X bits in positions masked by a 0

#ifdef USE_DEPRECATED
array_t  *array_and_a   (const array_t *a, const array_t *b, size_t len);
#endif
array_t **array_cmpl_a  (const array_t *a, size_t len, size_t *n);
#ifdef USE_DEPRECATED
array_t **array_diff_a  (const array_t *a, const array_t *b, size_t len, size_t *n);
#endif
array_t  *array_isect_a (const array_t *a, const array_t *b, size_t len);
array_t  *array_not_a   (const array_t *a, size_t len);
#ifdef USE_DEPRECATED
array_t  *array_or_a    (const array_t *a, const array_t *b, size_t len);
#endif

#ifdef USE_DEPRECATED
void array_shift_left  (array_t *a, size_t len, size_t start, size_t shift, enum bit_val val);
void array_shift_right (array_t *a, size_t len, size_t start, size_t shift, enum bit_val val);
#endif

/*
 * combines a and b into 1, 2 or 3 wc expressions.
 * the results will be save in place in a, b or extra.
 * The goal is to generate all wc expressions that are covering a U b. The
 * result will be non-redundant in the sense that the expressions are not subset
 * of each other.
 */
void array_combine(array_t **_a, array_t **_b, array_t **extra,
                   const array_t* mask, size_t len);
size_t
array_one_bit_subtract (const array_t *a, array_t *b, size_t len );

array_t *array_merge(const array_t *a, const array_t *b, size_t len);

#ifdef NEW_HS
array_t **array_unroll_superset(const array_t *a, array_t *b, size_t len, size_t *count);
#endif

#endif

