/*
  Copyright 2012, Stanford University. This file is licensed under GPL v2 plus
  a special exception, as described in included LICENSE_EXCEPTION.txt.

  Author: mchang@cs.stanford.com (Michael Chang)
          peyman.kazemian@gmail.com (Peyman Kazemian)
          kiekhebe@uni-potsdam.de (Sebastian Kiekheben)
          cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#ifndef _HS_H_
#define _HS_H_

#include "array.h"

#ifdef NEW_HS
struct hs_vec {
  array_t **elems;
  size_t used, alloc;
};

struct hs {
  size_t len;
  struct hs_vec list;
  struct hs_vec diff;
};
#else
struct hs_vec {
  array_t **elems;
  struct hs_vec *diff;
  size_t used, alloc;
};

struct hs {
  size_t len;
  struct hs_vec list;
};
#endif

struct hs *hs_create  (size_t len);
void       hs_destroy (struct hs *hs);
void       hs_free    (struct hs *hs);

void       hs_copy   (struct hs *dst, const struct hs *src);
struct hs *hs_copy_a (const struct hs *src);

size_t   hs_count      (const struct hs *hs);
size_t   hs_count_diff (const struct hs *hs);
void  hs_print      (const struct hs *hs);
char *hs_to_str     (const struct hs *hs);


void hs_add  (struct hs *hs, array_t *a);
void hs_add_hs (struct hs *dst, const struct hs *src);
void hs_diff (struct hs *hs, const array_t *a);

bool hs_compact   (struct hs *hs);
bool hs_compact_m (struct hs *hs, const array_t* mask);
void hs_comp_diff (struct hs *hs);
void hs_cmpl      (struct hs *hs);
bool hs_isect     (struct hs *a, const struct hs *b);
struct hs* hs_isect_a (const struct hs *a, const struct hs *b);
bool hs_isect_arr (struct hs *dst, const struct hs *src, const array_t *arr);
void hs_minus     (struct hs *a, const struct hs *b);
void hs_rewrite   (struct hs *hs, const array_t *mask, const array_t *rewrite);
#ifdef NEW_HS
void hs_unroll_superset(struct hs *hs, const struct hs *influences);
void hs_vec_append (struct hs_vec *v, array_t *a);
#else
void hs_vec_append (struct hs_vec *v, array_t *a, bool diff);
#endif

void hs_enlarge	  (struct hs *hs, size_t length);

/*
 * rewrites diff according to mask/rewrite array and diff it from rw_hs only if
 * the following condition is met: "If diff_hs was diff'ed from orig_hs and then
 * rewritten by mask/rewrite, it appears in final result"
 */
#ifdef USE_DEPRECATED
bool hs_potponed_diff_and_rewrite (const struct hs *orig_hs, struct hs *rw_hs,
    const array_t *diff, const array_t *mask, const array_t *rewrite);
#endif

bool hs_vec_is_empty(const struct hs_vec *vec);
bool hs_is_empty(const struct hs *hs);
bool hs_is_equal(const struct hs *a, const struct hs *b);
bool hs_is_sub(const struct hs *a, const struct hs *b);
bool hs_is_sub_eq(const struct hs *a, const struct hs *b);

void hs_simple_merge(struct hs *a);
#endif

