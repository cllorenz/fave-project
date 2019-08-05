/*
  Copyright 2012, Stanford University. This file is licensed under GPL v2 plus
  a special exception, as described in included LICENSE_EXCEPTION.txt.

  Author: mchang@cs.stanford.com (Michael Chang)
          peyman.kazemian@gmail.com (Peyman Kazemian)
          kiekhebe@uni-potsdam.de (Sebastian Kiekheben)
*/

#include "hs.h"

#define MAX_STR 65536
#define VEC_START_SIZE 1

/* Add A to V. If DIFF, V is a diff list, else V is directly from an hs. */
static void
#ifdef NEW_HS
vec_append (struct hs_vec *v, array_t *a)
#else
vec_append (struct hs_vec *v, array_t *a, bool diff)
#endif
{
  if (v->used == v-> alloc) {
    const size_t alloc = v->alloc ? 2 * v->alloc : VEC_START_SIZE;
    v->elems = xrealloc (v->elems, alloc * sizeof *v->elems);
    v->alloc = alloc;
#ifndef NEW_HS
    if (!diff) v->diff = xrealloc (v->diff, v->alloc * sizeof *v->diff);
#endif
  }
#ifndef NEW_HS
  if (!diff) memset (&v->diff[v->used], 0, sizeof *v->diff);
#endif
  v->elems[v->used++] = a;
}

static bool
vec_is_empty(const struct hs_vec *vec) {
    return !vec || !vec->used;
}

static void
vec_reset (struct hs_vec *v)
{
  v->used = v->alloc = 0;
  v->elems = NULL;
}

#ifdef NEW_HS
static void
vec_clear (struct hs_vec *v)
{
  if (v->elems) free (v->elems);
  vec_reset(v);
}
#endif

static void
vec_destroy (struct hs_vec *v)
{
#ifdef NEW_HS
  if (!v) return;

  for (size_t i = 0; i < v->used; i++) array_free(v->elems[i]);

  vec_clear(v);
#else
  if (!v) return;

  for (size_t i = 0; i < v->used; i++) {
    array_free (v->elems[i]);
    if (v->diff) vec_destroy (&v->diff[i]);
  }
  if (v->elems) free (v->elems);
  if (v->diff) free (v->diff);
#endif
}

/* Copy SRC into DST, with arrays of length LEN. */
static void
vec_copy (struct hs_vec *dst, const struct hs_vec *src, size_t len)
{
#ifdef NEW_HS


  if (!vec_is_empty(dst)) vec_destroy(dst);

  for (size_t i = 0; i < src->used; i++) {
    vec_append(dst, array_copy(src->elems[i], len));
  }
#else
  dst->used = src->used; dst->alloc = src->alloc;
  dst->elems = NULL; dst->diff = NULL;

  size_t alloc = dst->alloc * sizeof *dst->elems;
  if (!alloc) return;

  dst->elems = xmalloc (alloc);
  if (src->diff) dst->diff = xcalloc (dst->alloc, sizeof *dst->diff);
  else dst->diff = NULL;
  for (size_t i = 0; i < src->used; i++) {
    dst->elems[i] = array_copy (src->elems[i], len);
    if (src->diff) vec_copy (&dst->diff[i], &src->diff[i], len);
  }
#endif
}

/*
 * Traverses diff lists of SRC and checks for overlaps with ISECT to be added to
 * the diff list DST.
 */
#ifndef NEW_HS
static void
vec_diff (struct hs_vec *dst, const array_t *isect, const struct hs_vec *src, size_t len)
{
  for (size_t i = 0; i < src->used; i++) {
    array_t *tmp = array_isect_a (isect, src->elems[i], len);
    if (tmp && !array_has_z(tmp, len)) vec_append (dst, tmp, true);
    else if (tmp) array_free(tmp);
  }
}
#endif

static inline void
vec_elem_remove (struct hs_vec *v, size_t i)
{
  if (i >= v->used-1) --v->used;
  else v->elems[i] = v->elems[--v->used];
}

static inline void
vec_diff_remove (struct hs_vec *v, size_t i)
{
#ifdef NEW_HS
  vec_elem_remove (v, i);
#else
  if (v->diff) {
    vec_destroy(&v->diff[i]);
    v->diff[i] = v->diff[v->used];
  }
#endif
}

/* Free elem I of V, replacing it with last elem. */
static void
vec_elem_free (struct hs_vec *v, size_t i)
{
  assert(i < v->used);

  if (v->elems[i]) array_free (v->elems[i]);
  vec_elem_remove(v,i);
#ifndef NEW_HS
  vec_diff_remove(v,i);
#endif
}

static void
vec_elem_replace_and_delete (struct hs_vec *v, size_t i, size_t j)
{
  array_free(v->elems[i]);
  v->elems[i] = v->elems[j];
  vec_elem_remove(v,j);
}

/*
 * Compares all elements of A and B to create a new intersection vector. Also
 * checks a diffs for overlaps and adds them accordingly.
 */
struct hs_vec
vec_isect_a (const struct hs_vec *a, const struct hs_vec *b, size_t len)
{
#ifdef NEW_HS
  struct hs_vec new_list = {0, 0, 0};
#else
  struct hs_vec new_list = {0, 0, 0, 0};
#endif

#ifdef NEW_HS
  for (size_t i = 0; i < a->used; i++) {
    for (size_t j = 0; j < b->used; j++) {
      array_t *isect = array_isect_a (a->elems[i], b->elems[j], len);
      if (!isect) continue;
      else vec_append(&new_list, isect);
    }
  }

#else
  for (size_t i = 0; i < a->used; i++) {
    for (size_t j = 0; j < b->used; j++) {
      array_t *isect = array_isect_a (a->elems[i], b->elems[j], len);
      if (!isect) continue;
      vec_append (&new_list, isect, false);
      size_t idx = new_list.used - 1;
      struct hs_vec *d = &new_list.diff[idx];
      vec_diff (d, isect, &a->diff[i], len);
      vec_diff (d, isect, &b->diff[j], len);
    }
  }
#endif
  return new_list;
}

#ifdef NEW_HS
static void
vec_to_str (const struct hs_vec *v, size_t len, size_t *pos, char *res)
#else
static char *
vec_to_str (const struct hs_vec *v, size_t len, char *res)
#endif
{
#ifdef NEW_HS
  *res++ = '('; *pos += 1;

  if (!v->used) {
    res += sprintf(res, "nil");
    *pos += 3;
  }

  for (size_t i = 0; i < v->used; i++) {
    if (i) {
      res += sprintf (res, " + ");
      *pos += 3;
    }
    char *s = array_to_str (v->elems[i], len, true);
    const size_t offset = sprintf (res, "%s", s);
    res += offset;
    *pos += offset;
    free (s);
  }
  *res++ = ')'; *pos += 1;

#else
  if (!v->diff) *res++ = '(';
  if (!v->used)
        res += sprintf(res, "nil");

  for (size_t i = 0; i < v->used; i++) {
    const bool diff = v->diff && v->diff[i].used;
    if (i) res += sprintf (res, " + ");
    char *s = array_to_str (v->elems[i], len, true);
    if (diff) *res++ = '(';
    res += sprintf (res, "%s", s);
    free (s);
    if (diff) {
      res += sprintf (res, " - ");
      res = vec_to_str (&v->diff[i], len, res);
      *res++ = ')';
    }
  }
  if (!v->diff) *res++ = ')';
#endif
  *res = 0;
#ifndef NEW_HS
  return res;
#endif
}

/* Remove elems of V that are covered by another elem. V must be a diff list.
   LEN is length of each array. */
static void
vec_compact_m (struct hs_vec *v, const array_t* mask, const size_t len)
{
  for (size_t i = 0; i < v->used; i++) {
    for (size_t j = i + 1; j < v->used; j++) {
      array_t *extra = NULL;
      array_combine(&(v->elems[i]), &(v->elems[j]), &extra, mask, len);
      if (extra) {
#ifdef NEW_HS
        vec_append(v, extra);
#else
        vec_append(v,extra,true);
#endif
      }
      if (v->elems[i] == NULL) {
        if (v->elems[j] == NULL) vec_elem_free (v, j);
        vec_elem_free (v, i);
        i--;
        break;
      }
      if (v->elems[j] == NULL) {
        vec_elem_free (v, j);
        j--;
        continue;
      }
    }
  }
}

#ifdef NEW_HS
static void
vec_compact (struct hs_vec *vec, const size_t len)
{
  vec_compact_m (vec, NULL, len);
}
#endif

static void
vec_isect (struct hs_vec *a, const struct hs_vec *b, size_t len)
{
  struct hs_vec v = vec_isect_a (a, b, len);
  vec_destroy (a);
  *a = v;
}

static void
vec_enlarge (struct hs_vec *vec, size_t length_old, size_t length)
{
	if (length <= length_old) {
		return;
	}
	for (size_t i = 0; i < vec->used; i++) {
		vec->elems[i] = array_resize(vec->elems[i],length_old,length);
	}
#ifndef NEW_HS
	if (vec->diff && vec->diff->used != 0) {
		vec_enlarge(vec->diff, length_old, length); //recursive
	}
#endif
}

#ifdef NEW_HS
static bool
vec_is_all(const struct hs_vec *vec, const size_t len) {
    if (vec_is_empty(vec)) return false;

    struct hs_vec tmp = {0, 0, 0};
    vec_copy(&tmp, vec, len);

    vec_compact(&tmp, len);

    if (tmp.used != 1) {
      vec_destroy(&tmp);
      return false;
    }

    array_t *all = array_create(len, BIT_X);
    const bool res = array_is_eq(all, tmp.elems[0], len);

    array_free(all);
    vec_destroy(&tmp);

    return res;
}
#endif

#ifdef NEW_HS
void
vec_cmpl (struct hs_vec *vec, const size_t len)
{
  struct hs_vec tmp = {0, 0, 0};
  if (vec_is_empty(vec))
    vec_append(&tmp, array_create(len, BIT_X));

  for (size_t i = 0; i < vec->used; i++) {
    size_t cnt = 0;
    array_t **cmpl = array_cmpl_a (vec->elems[i], len, &cnt);

    for (size_t j = 0; j < cnt; j++)
      vec_append(&tmp, cmpl[j]);

    free(cmpl);
  }

  vec_destroy(vec);
  *vec = tmp;
}
#endif

#ifdef NEW_HS
void
vec_union (struct hs_vec *a, const struct hs_vec *b, const size_t len)
{
  const size_t used = a->used;
  for (size_t i = 0; i < b->used; i++) {
    bool any = false;
    array_t *elem = b->elems[i];

    for (size_t j = 0; j < used; j++) {
      any |= array_is_eq(elem, a->elems[j], len);

      if (any) break;
    }

    if (!any)
      vec_append(a, array_copy(elem, len));
  }
}
#endif

void
hs_enlarge (struct hs *hs, size_t length)
{
	if (!hs || length <= hs->len) {
		return;
	}
	vec_enlarge(&hs->list, hs->len, length);
#ifdef NEW_HS
	vec_enlarge(&hs->diff, hs->len, length);
#endif
	hs->len = length;
}

struct hs *
hs_create (size_t len)
{
  struct hs *hs = xcalloc (1, sizeof *hs);
  hs->len = len;
  return hs;
}

void
hs_destroy (struct hs *hs)
{
  if (!hs) return;
  vec_destroy (&hs->list);
#ifdef NEW_HS
  vec_destroy (&hs->diff);
#endif
}

void
hs_free (struct hs *hs)
{
  if (!hs) return;
  hs_destroy (hs);
  free (hs);
}

void
hs_copy (struct hs *dst, const struct hs *src)
{
  dst->len = src->len;
  vec_copy (&dst->list, &src->list, dst->len);
#ifdef NEW_HS
  vec_copy (&dst->diff, &src->diff, dst->len);
#endif
}

struct hs *
hs_copy_a (const struct hs *hs)
{
  struct hs *res = hs_create(hs->len);
  hs_copy (res, hs);
  return res;
}

size_t
hs_count (const struct hs *hs)
{ return hs->list.used; }

size_t
hs_count_diff (const struct hs *hs)
{
#ifdef NEW_HS
  return hs->diff.used;
#else
  size_t sum = 0;
  const struct hs_vec *v = &hs->list;
  for (size_t i = 0; i < v->used; i++)
    sum += v->diff[i].used;
  return sum;
#endif
}

void
hs_print (const struct hs *hs)
{
  char *s = hs_to_str(hs);
  fprintf (stdout,"%s\n", s);
  free (s);
}

char *
hs_to_str (const struct hs *hs)
{
  char s[MAX_STR];
#ifdef NEW_HS
  size_t pos = 0;
  vec_to_str (&hs->list, hs->len, &pos, s);
  if (hs->diff.used) {
    pos += sprintf(s + pos, " - ");
    vec_to_str (&hs->diff, hs->len, &pos, s+pos);
  }
#else
  vec_to_str (&hs->list, hs->len, s);
#endif
  return xstrdup (s);
} 

void
hs_add (struct hs *hs, array_t *a)
{
  if (!a) return;
#ifdef NEW_HS
  vec_append (&hs->list, a);
#else
  vec_append (&hs->list, a, false);
#endif
}

void
hs_diff (struct hs *hs, const array_t *a)
{
#ifdef NEW_HS
  if (!a) return;
  vec_append(&hs->diff, array_copy(a, hs->len));
#else
  struct hs_vec *v = &hs->list;
  for (size_t i = 0; i < v->used; i++) {
    array_t *tmp = array_isect_a (v->elems[i], a, hs->len);
    if (tmp) vec_append (&v->diff[i], tmp, true);
  }
#endif
}

void hs_add_hs (struct hs *dst, const struct hs *src) {
  assert (dst->len == src->len);
#ifdef NEW_HS
  const size_t len = src->len;

  for (size_t i = 0; i < src->list.used; i++)
    vec_append(&dst->list, array_copy(src->list.elems[i], len));

  for (size_t i = 0; i < src->diff.used; i++)
    vec_append(&dst->diff, array_copy(src->diff.elems[i], len));

#else
    struct hs_vec list = src->list;
    for (size_t i = 0; i < list.used; i++)
        vec_append(&dst->list,array_copy(list.elems[i],src->len),false);

    if (!list.diff) return;

    for (size_t i = 0; i < list.used; i++)
        for (size_t j = 0; j < list.diff[i].used; j++)
            vec_append(&dst->list,array_copy(list.diff[i].elems[j],src->len),true);
#endif
}

bool
hs_compact (struct hs *hs) {
  return hs_compact_m(hs, NULL);
}

bool
hs_compact_m (struct hs *hs, const array_t *mask)
{
#ifdef NEW_HS
  vec_compact_m (&hs->list, mask, hs->len);

  if (hs_is_empty(hs)) {
    hs_destroy(hs);
    return false;
  }

  vec_compact_m (&hs->list, mask, hs->len);
  vec_compact_m (&hs->diff, mask, hs->len);

  for (size_t i = 0; i < hs->list.used; i++) {
    for (size_t j = 0; j < hs->diff.used; j++) {
      const bool superset = array_is_sub_eq(
        hs->list.elems[i],
        hs->diff.elems[j],
        hs->len
      );

      if (superset) {
        vec_elem_free (&hs->list, i); i--;
        break;
      }
    }
  }

  return hs->list.used;

#else
  struct hs_vec *v = &hs->list;
  for (size_t i = 0; i < v->used; i++) {
    vec_compact_m (&v->diff[i], mask, hs->len);
    for (size_t j = 0; j < v->diff[i].used; j++) {
      // I have no idea why this line was commented out but including it
      // prevents a hs_is_sub() regression
      //if (!array_is_sub (v->diff[i].elems[j], v->elems[i], hs->len)) continue;
      size_t cnt = array_one_bit_subtract (v->diff[i].elems[j], v->elems[i], hs->len);
      if (cnt > 1) continue;
      else if (cnt == 1) {
        vec_elem_free (&(v->diff[i]), j);
        j--;
      }
      else {
        vec_elem_free (v, i);
        i--; break;
      }
    }
  }
  return v->used;
#endif
}

void
vec_move (struct hs_vec *dst, struct hs_vec *src)
{
  *dst = *src;
  vec_reset(src);
}

#ifdef NEW_HS
// XXX: same as hs_comp_diff()?
void
hs_expand_diff(struct hs *h)
{
  struct hs_vec tmp = {0, 0, 0};
  vec_move(&tmp, &h->diff);

  vec_cmpl(&tmp, h->len);
  vec_isect(&h->list, &tmp, h->len);

  vec_clear(&tmp);
}
#endif

void
hs_comp_diff (struct hs *hs)
{
#ifdef NEW_HS
  struct hs_vec new_list = {0, 0, 0};

  struct hs_vec tmp_diff = {0, 0, 0};
  vec_move(&tmp_diff, &hs->diff);
  vec_cmpl(&tmp_diff, hs->len);

  for (size_t i = 0; i < hs->list.used; i++) {
    struct hs_vec tmp_elem = {0, 0, 0};

    vec_append(&tmp_elem, hs->list.elems[i]);
    vec_isect(&tmp_elem, &tmp_diff, hs->len);

    vec_union(&new_list, &tmp_elem, hs->len);

    vec_destroy(&tmp_elem);
  }

  vec_clear(&hs->list);
  vec_destroy(&tmp_diff);
  vec_move(&hs->list, &new_list);

  hs_compact(hs);

#else
  // v -> iterate over elements, new_list -> collect elements
  struct hs_vec *v = &hs->list, new_list = {0, 0, 0, 0};
  for (size_t i = 0; i < v->used; i++) {
    // tmp -> takes ith element, tmp2 -> takes ith diff
    struct hs tmp = {hs->len,{0, 0, 0, 0}}, tmp2 = {hs->len,{0, 0, 0, 0}};
    vec_append (&tmp.list, v->elems[i], false);
    v->elems[i] = NULL; // empties ith entry
    tmp2.list = v->diff[i];
    hs_minus (&tmp, &tmp2); // expands diff list to positive element list

    // collects all positive elements
    if (!new_list.used) new_list = tmp.list;
    else {
      for (size_t j = 0; j < tmp.list.used; j++) {
        vec_append (&new_list, tmp.list.elems[j], false);
        tmp.list.elems[j] = NULL;
      }
      hs_destroy (&tmp);
    }
  }
  vec_destroy (v);
  hs->list = new_list;
#endif
}


/*
 * Complements HS by combining all array complements plus diff arrays.
   If HS is empty then the all set represented as an all X vector is returned.
 */
void
hs_cmpl (struct hs *hs)
{
#ifdef NEW_HS

  vec_cmpl(&hs->diff, hs->len);
  vec_isect(&hs->diff, &hs->list, hs->len);
  vec_destroy(&hs->list);
  vec_compact(&hs->diff, hs->len);
  vec_append(&hs->list, array_create(hs->len, BIT_X));

#else
  if (!hs->list.used) {
    hs_add (hs, array_create (hs->len, BIT_X));
    return;
  }

  struct hs_vec *v = &hs->list;
  struct hs_vec new_list = {0, 0, 0, 0};

  for (size_t i = 0; i < v->used; i++) {
    struct hs_vec tmp = {0, 0, 0, 0};
    tmp.elems = array_cmpl_a (v->elems[i], hs->len, &tmp.used);
    tmp.alloc = tmp.used;

    /* If complement is empty, result will be empty. */
    if (!tmp.elems) {
      vec_destroy (&new_list);
      vec_destroy (&hs->list);
      memset (&hs->list, 0, sizeof hs->list);
      return;
    }

    tmp.diff = xcalloc (tmp.alloc, sizeof *tmp.diff);
    if (v->diff) { /* NULL if called from comp_diff */
      struct hs_vec *d = &v->diff[i];
      for (size_t j = 0; j < d->used; j++)
        vec_append (&tmp, array_copy(d->elems[j],hs->len), false);
    }

    if (!new_list.used) new_list = tmp;
    else {
      vec_isect (&new_list, &tmp, hs->len);
      vec_destroy (&tmp);
    }
  }

  vec_destroy (v);

  hs->list = new_list;
#endif
}

#ifdef NEW_HS
void
hs_union (struct hs *a, const struct hs *b)
{
  assert (a->len == b->len);

  vec_union(&a->list, &b->list, a->len);
  vec_union(&a->diff, &b->diff, a->len);
}
#endif

bool
hs_isect (struct hs *a, const struct hs *b)
{
  assert (a->len == b->len);

  vec_isect (&a->list, &b->list, a->len);
#ifdef NEW_HS
  vec_union(&a->diff, &b->diff, a->len);
#endif
  return a->list.used;
}

struct hs*
hs_isect_a (const struct hs *a, const struct hs *b)
{
  assert (a->len == b->len);

#ifdef NEW_HS
  struct hs h = {a->len, {0, 0, 0}, {0, 0, 0}};
#else
  struct hs h = {a->len, {0, 0, 0, 0}};
#endif  

  hs_copy(&h, a);

  struct hs *res = NULL;
  if (hs_isect(&h, b))
    res = hs_copy_a(&h);

  hs_destroy(&h);
  return res;
}

bool
hs_isect_arr (struct hs *res, const struct hs *hs, const array_t *a)
{
#ifdef NEW_HS
  res->len = hs->len;
  struct hs_vec list = {0, 0, 0};
  res->list = list;
  struct hs_vec diff = {0, 0, 0};
  res->diff = diff;
  for (size_t i = 0; i < hs->list.used; i++) {
    array_t *isect = array_isect_a(hs->list.elems[i], a, hs->len);
    if (!isect) continue;

    vec_append(&res->list, isect);
  }

  for (size_t i = 0; i < hs->diff.used; i++) {
    array_t *isect = array_isect_a(hs->diff.elems[i], a, hs->len);
    if (!isect) continue;

    vec_append(&res->diff, isect);
  }

  return res->list.used;

#else
  const struct hs_vec *v = &hs->list;
  array_t tmp[ARRAY_BYTES (hs->len) / sizeof (array_t)];
  size_t pos = SIZE_MAX;

  for (size_t i = 0; i < v->used; i++) {
    if (!array_isect (v->elems[i], a, hs->len, tmp)) continue;
    pos = i; break;
  }
  if (pos == SIZE_MAX) return false;

  memset (res, 0, sizeof *res);
  res->len = hs->len;
  struct hs_vec *resv = &res->list;
  for (size_t i = pos; i < v->used; i++) {
    if (i == pos) vec_append (resv, xmemdup (tmp, sizeof tmp), false);
    else {
      array_t *isect = array_isect_a (v->elems[i], a, res->len);
      if (!isect) continue;
      vec_append (resv, isect, false);
    }

    struct hs_vec *diff = &v->diff[i], *resd = &resv->diff[resv->used - 1];
    for (size_t j = 0; j < diff->used; j++) {
      array_t *isect = array_isect_a (diff->elems[j], a, res->len);
      if (!isect) continue;
      vec_append (resd, isect, true);
    }
  }
  return true;
#endif
}

void
hs_minus (struct hs *a, const struct hs *b)
{
  assert (a->len == b->len);

#ifdef NEW_HS
  struct hs cmpl = {b->len,{0, 0, 0}, {0, 0, 0}};
#else
  struct hs tmp = {b->len,{0, 0, 0, 0}};
#endif

  hs_copy (&cmpl, b);
  hs_cmpl(&cmpl);
  hs_isect (a, &cmpl);
  hs_destroy (&cmpl);

  hs_compact (a);
}

void
hs_rewrite (struct hs *hs, const array_t *mask, const array_t *rewrite)
{
#ifdef NEW_HS
  struct hs_vec *list = &hs->list;
  for (size_t i = 0; i < list->used; i++)
    array_rewrite(list->elems[i], mask, rewrite, hs->len);

  struct hs_vec *diff = &hs->diff;
  for (size_t i = 0; i < diff->used; i++)
    array_rewrite(diff->elems[i], mask, rewrite, hs->len);
#else
  struct hs_vec *v = &hs->list;
  for (size_t i = 0; i < v->used; i++) {
    size_t n = array_rewrite (v->elems[i], mask, rewrite, hs->len);

    struct hs_vec *diff = &v->diff[i];
    for (size_t j = 0; j < diff->used; j++) {
      if (n == array_rewrite (diff->elems[j], mask, rewrite, hs->len)) continue;
      array_free (diff->elems[j]);
      diff->elems[j] = diff->elems[--diff->used];
      j--;
    }
  }
#endif
}


#ifdef USE_DEPRECATED
bool hs_potponed_diff_and_rewrite (const struct hs *orig_hs, struct hs *rw_hs,
    const array_t *diff, const array_t *mask, const array_t *rewrite) {
  const struct hs_vec *orig_v = &orig_hs->list;
  struct hs_vec *rw_v = &rw_hs->list;
  bool changed = false;

  for (size_t i = 0; i < orig_v->used; i++) {
    array_t *tmp = array_isect_a (orig_v->elems[i], diff, orig_hs->len);
    if (!tmp) continue;
    size_t n = array_x_count (orig_v->elems[i], mask, orig_hs->len);
    size_t m = array_rewrite (tmp, mask, rewrite, orig_hs->len);
    if (n == m) {
      changed = true;
      vec_append (&rw_v->diff[i], tmp, true);
    } else {
      array_free(tmp);
    }
  }
  return changed;
}
#endif


bool hs_vec_is_empty(const struct hs_vec *vec) {
    return vec_is_empty(vec);
}

bool hs_is_empty(const struct hs *hs) {
#ifdef NEW_HS
    return !hs || vec_is_empty(&hs->list) || vec_is_all(&hs->diff, hs->len);
#else
    return !hs || vec_is_empty(&hs->list);
#endif
}

/*
 * A \subset B \eq
 *  (A \isect B \not= emptyset) \land (A - B = \emptyset) \land
 *  ((A \isect B = \emptyset) \lor (A - B \not= \emptyset))
 */
bool hs_is_sub(const struct hs *a, const struct hs *b) {
    assert (a->len == b->len);

    if (hs_is_empty(b)) return false;

    const bool a_is_sub_eq_b = hs_is_sub_eq(a,b);
    const bool b_is_sub_eq_a = hs_is_sub_eq(b,a);

    return a_is_sub_eq_b && !b_is_sub_eq_a;
}

bool hs_is_equal(const struct hs *a, const struct hs *b) {
    assert (a->len == b->len);

    const bool a_empty = hs_is_empty(a);
    const bool b_empty = hs_is_empty(b);

    if (a_empty && b_empty) return true;
    if (a_empty && !b_empty) return false;
    if (!a_empty && b_empty) return false;

    const bool a_is_sub_eq_b = hs_is_sub_eq(a,b);
    const bool b_is_sub_eq_a = hs_is_sub_eq(b,a);

    return a_is_sub_eq_b && b_is_sub_eq_a;
}

void hs_simple_merge(struct hs *a) {
    struct hs_vec *v = &a->list;

    size_t len = a->len;

    size_t i = 0;
    while (i<v->used) {
        size_t j = i+1;

        while (j<v->used) {
            // v[i] is a superset of v[j] -> delete v[j]
            if (array_is_sub_eq(v->elems[j],v->elems[i],len)) {
                vec_elem_free(v,j);
                continue;
            }
            // v[i] is a subset of v[j] -> replace v[i] with v[j] and delete v[j]
            if (array_is_sub_eq(v->elems[i],v->elems[j],len)) {
                vec_elem_replace_and_delete(v,i,j);
                continue;
            }
            // v[i] and v[j] can be merged -> replace v[i] with v_merge and delete v[j]
            array_t *v_merge = array_merge(v->elems[i],v->elems[j],len);
            if (v_merge) {
                vec_elem_free(v,j);

                array_free(v->elems[i]);
                v->elems[i] = v_merge;
                continue;
            }
            j++;
        }
        i++;
    }
}

bool hs_has_diff(const struct hs *a) {
#ifdef NEW_HS
    return a->diff.used;
#else
    return (a->list.diff && a->list.diff->used);
#endif
}

/*
 * A \subseteq B \eq (A \isect B \not= emptyset) \land (A - B = \emptyset)
 */
bool hs_is_sub_eq(const struct hs *a, const struct hs *b) {
    assert (a->len == b->len);

#ifdef NEW_HS

    // A \isect B \not= emptyset
    struct hs isect = {a->len, {0, 0, 0}, {0, 0, 0}};
    hs_copy(&isect, b);

    hs_isect(&isect, a);

    const bool empty_isect = hs_is_empty(&isect);

    hs_destroy(&isect);

    if (empty_isect) return false;

    // A - B = \emptyset
    struct hs minus = {a->len, {0, 0, 0}, {0, 0, 0}};
    hs_copy(&minus, a);

    hs_minus(&minus, b);
    const bool empty_minus = hs_is_empty(&minus);

    hs_destroy(&minus);

    return empty_minus;


/* -------------------------------------------------------------------------- */
#else

    // trivial case (A is empty)
    const bool a_empty = hs_is_empty(a);

    if (a_empty) return true;

    // trivial case (B is empty but A is not as checked earlier)
    const bool b_empty = hs_is_empty(b);
    if (b_empty && !a_empty) return false;

    // trivial case (B is All set)
    if (b->list.used == 1 && array_all_x(b->list.elems[0], b->len)) return true;

    // simple case (no diffs)
    if (!hs_has_diff(a) && !hs_has_diff(b)) {

        struct hs tmp_b = {b->len, {0, 0, 0, 0}};
        hs_copy(&tmp_b,b);
        hs_simple_merge(&tmp_b);

        struct hs_vec v_a = a->list;
        struct hs_vec v_b = tmp_b.list;
        size_t len = a->len;

        for (size_t i = 0; i < v_a.used; i++) {
            bool any = false;
            for (size_t j = 0; j < v_b.used; j++) {

                any |= array_is_sub_eq(v_a.elems[i],v_b.elems[j],len);

                if (any) break;
            }
            if (!any) { hs_destroy(&tmp_b); return false; }
        }
        hs_destroy(&tmp_b);
        return true;
    }

    struct hs tmp_a = {a->len, {0, 0, 0, 0}};

    hs_copy(&tmp_a,a);
    hs_compact(&tmp_a);

    struct hs tmp_b = {b->len, {0, 0, 0, 0}};
    hs_copy(&tmp_b,b);
    hs_compact(&tmp_b);

    // A == B == emptyset
    const bool empty_a = hs_is_empty(&tmp_a);
    const bool empty_b = hs_is_empty(&tmp_b);

    if ((empty_a || empty_b)) {
        hs_destroy(&tmp_a);
        hs_destroy(&tmp_b);
        return (empty_a && !empty_b) || (empty_a && empty_b) || !(!empty_a && empty_b);
    }

    // A \isect B == emptyset
    struct hs tmp_isect = {tmp_a.len,{0, 0, 0, 0}};
    hs_copy(&tmp_isect,&tmp_a);
    hs_isect(&tmp_isect,&tmp_b);
    if (hs_is_empty(&tmp_isect)) {

        hs_destroy(&tmp_isect);
        hs_destroy(&tmp_a);
        hs_destroy(&tmp_b);
        return false;
    }
    hs_destroy(&tmp_isect);

    // A - B != emptyset
    hs_minus(&tmp_a, &tmp_b);

    const bool empty = hs_is_empty(&tmp_a);

    hs_destroy(&tmp_a);
    hs_destroy(&tmp_b);

    return empty;
#endif
}

void
#ifdef NEW_HS
hs_vec_append (struct hs_vec *v, array_t *a)
{ vec_append (v, a); }
#else
hs_vec_append (struct hs_vec *v, array_t *a, bool diff)
{ vec_append (v, a, diff); }
#endif
