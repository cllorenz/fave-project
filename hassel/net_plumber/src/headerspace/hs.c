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
vec_append (struct hs_vec *v, array_t *a, bool diff)
{
  if (v->used == v->alloc) {
    v->alloc = v->alloc ? 2 * v->alloc : VEC_START_SIZE;
    v->elems = xrealloc (v->elems, v->alloc * sizeof *v->elems);
    if (!diff) v->diff = xrealloc (v->diff, v->alloc * sizeof *v->diff);
  }
  if (!diff) memset (&v->diff[v->used], 0, sizeof *v->diff);
  v->elems[v->used++] = a;
}

/* Copy SRC into DST, with arrays of length LEN. */
static void
vec_copy (struct hs_vec *dst, const struct hs_vec *src, size_t len)
{
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
}

static void
vec_destroy (struct hs_vec *v)
{
  if (!v) return;

  for (size_t i = 0; i < v->used; i++) {
    array_free (v->elems[i]);
    if (v->diff) vec_destroy (&v->diff[i]);
  }
  if (v->elems) free (v->elems);
  if (v->diff) free (v->diff);
}

static void
vec_diff (struct hs_vec *dst, const array_t *isect, const struct hs_vec *src, size_t len)
{
  for (size_t i = 0; i < src->used; i++) {
    array_t *tmp = array_isect_a (isect, src->elems[i], len);
    if (tmp) vec_append (dst, tmp, true);
  }
}

static inline void
vec_elem_remove (struct hs_vec *v, size_t i)
{
  if (i >= v->used-1) --v->used;
  else v->elems[i] = v->elems[--v->used];
}

/* Free elem I of V, replacing it with last elem. */
static void
vec_elem_free (struct hs_vec *v, size_t i)
{
  assert(i < v->used);

  if (v->elems[i]) array_free (v->elems[i]);
  vec_elem_remove(v,i);
  if (v->diff && i < v->diff->used) {
    vec_destroy (&v->diff[i]);
    v->diff[i] = v->diff[v->used];
  }
}

static void
vec_elem_replace_and_delete (struct hs_vec *v, size_t i, size_t j)
{
  array_free(v->elems[i]);
  v->elems[i] = v->elems[j];
  vec_elem_remove(v,j);
}

struct hs_vec
vec_isect_a (const struct hs_vec *a, const struct hs_vec *b, size_t len)
{
  struct hs_vec new_list = {0};
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
  return new_list;
}

static char *
vec_to_str (const struct hs_vec *v, size_t len, char *res)
{
  if (!v->diff) *res++ = '(';
  for (size_t i = 0; i < v->used; i++) {
    bool diff = v->diff && v->diff[i].used;
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
  *res = 0;
  return res;
}

/* Remove elems of V that are covered by another elem. V must be a diff list.
   LEN is length of each array. */
static void
vec_compact (struct hs_vec *v, const array_t* mask, size_t len)
{
  for (size_t i = 0; i < v->used; i++) {
    for (size_t j = i + 1; j < v->used; j++) {
      array_t *extra = NULL;
      array_combine(&(v->elems[i]), &(v->elems[j]), &extra, mask, len);
      if (extra) {
        vec_append(v,extra,true);
      }
      if (v->elems[i] == NULL) {
        vec_elem_free (v, i);
        if (v->elems[j] == NULL) vec_elem_free (v, j);
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
	if (vec->diff && vec->diff->used != 0) {
		vec_enlarge(vec->diff, length_old, length); //recursive
	}
}

void
hs_enlarge (struct hs *hs, size_t length)
{
	if (!hs || length <= hs->len) {
		return;
	}
	vec_enlarge(&hs->list,hs->len,length);
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
}

struct hs *
hs_copy_a (const struct hs *hs)
{
  struct hs *res = xmalloc (sizeof *res);
  hs_copy (res, hs);
  return res;
}

size_t
hs_count (const struct hs *hs)
{ return hs->list.used; }

size_t
hs_count_diff (const struct hs *hs)
{
  size_t sum = 0;
  const struct hs_vec *v = &hs->list;
  for (size_t i = 0; i < v->used; i++)
    sum += v->diff[i].used;
  return sum;
}

void
hs_print (const struct hs *hs)
{
  char s[MAX_STR];
  vec_to_str (&hs->list, hs->len, s);
  fprintf (stdout,"%s\n", s);
}

char *
hs_to_str (const struct hs *hs)
{
  char s[MAX_STR];
  vec_to_str (&hs->list, hs->len, s);
  return xstrdup (s);
} 

void
hs_add (struct hs *hs, array_t *a)
{
  if (!a) return;
  vec_append (&hs->list, a, false);
}

void
hs_diff (struct hs *hs, const array_t *a)
{
  struct hs_vec *v = &hs->list;
  for (size_t i = 0; i < v->used; i++) {
    array_t *tmp = array_isect_a (v->elems[i], a, hs->len);
    if (tmp) vec_append (&v->diff[i], tmp, true);
  }
}

void hs_add_hs (struct hs *dst, const struct hs *src) {
    struct hs_vec list = src->list;
    for (size_t i = 0; i < list.used; i++)
        vec_append(&dst->list,array_copy(list.elems[i],src->len),false);

    if (!list.diff) return;

    for (size_t i = 0; i < list.used; i++)
        for (size_t j = 0; j < list.diff[i].used; j++)
            vec_append(&dst->list,array_copy(list.diff[i].elems[j],src->len),true);
}

bool
hs_compact (struct hs *hs) {
  return hs_compact_m(hs,NULL);
}

bool
hs_compact_m (struct hs *hs, const array_t *mask)
{
  struct hs_vec *v = &hs->list;
  for (size_t i = 0; i < v->used; i++) {
    vec_compact (&v->diff[i], mask, hs->len);
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
}

void
hs_comp_diff (struct hs *hs)
{
  struct hs_vec *v = &hs->list, new_list = {0};
  for (size_t i = 0; i < v->used; i++) {
    struct hs tmp = {hs->len,{0}}, tmp2 = {hs->len,{0}};
    vec_append (&tmp.list, v->elems[i], false);
    v->elems[i] = NULL;
    tmp2.list = v->diff[i];
    hs_minus (&tmp, &tmp2);

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
}

void
hs_cmpl (struct hs *hs)
{
  if (!hs->list.used) {
    hs_add (hs, array_create (hs->len, BIT_X));
    return;
  }

  struct hs_vec *v = &hs->list, new_list = {0};

  for (size_t i = 0; i < v->used; i++) {
    struct hs_vec tmp = {0};
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
}

bool
hs_isect (struct hs *a, const struct hs *b)
{
  assert (a->len == b->len);
  vec_isect (&a->list, &b->list, a->len);
  return a->list.used;
}

struct hs*
hs_isect_a (const struct hs *a, const struct hs *b)
{
  assert (a->len == b->len);
  struct hs_vec r = vec_isect_a (&a->list, &b->list, a->len);
  if (r.used > 0) {
    struct hs *h = malloc(sizeof *h);
    h->list = r;
    h->len = a->len;
    return h;
  } else {
    return NULL;
  }
}

bool
hs_isect_arr (struct hs *res, const struct hs *hs, const array_t *a)
{
  const struct hs_vec *v = &hs->list;
  array_t tmp[ARRAY_BYTES (hs->len) / sizeof (array_t)];
  size_t pos = -1;

  for (size_t i = 0; i < v->used; i++) {
    if (!array_isect (v->elems[i], a, hs->len, tmp)) continue;
    pos = i; break;
  }
  if (pos == -1) return false;

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
}

void
hs_minus (struct hs *a, const struct hs *b)
{
  assert (a->len == b->len);
  struct hs tmp = {b->len,{0}};
  hs_copy (&tmp, b);
  hs_cmpl (&tmp);
  hs_isect (a, &tmp);
  hs_destroy (&tmp);
  hs_compact (a);
}

void
hs_rewrite (struct hs *hs, const array_t *mask, const array_t *rewrite)
{
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
}

// XXX: deprecated
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

bool hs_is_empty(const struct hs *hs) {
    return !hs || !hs->list.used;
}

/*
 * A \subset B \eq
 *  (A \isect B \not= emptyset) \land (A - B = \emptyset) \land
 *  ((A \isect B = \emptyset) \lor (A - B \not= \emptyset))
 */
bool hs_is_sub(const struct hs *a, const struct hs *b) {
    assert (a->len == b->len);

    return hs_is_sub_eq(a,b) && !hs_is_equal(a,b);

    if (hs_is_empty(b)) return false;
}

bool hs_is_equal(const struct hs *a, const struct hs *b) {
    assert (a->len == b->len);

    return hs_is_sub_eq(a,b) && hs_is_sub_eq(b,a);
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
    return (a->list.diff && a->list.diff->used);
}

/*
 * A \subseteq B \eq (A \isect B \not= emptyset) \land (A - B = \emptyset)
 */
bool hs_is_sub_eq(const struct hs *a, const struct hs *b) {
    assert (a->len == b->len);

    // simple case (no diffs)
    if (!hs_has_diff(a) && !hs_has_diff(b)) {

        struct hs tmp_b = {b->len,{0}};
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

    struct hs tmp_a = {a->len,{0}};
    hs_copy(&tmp_a,a);
    hs_compact(&tmp_a);

    struct hs tmp_b = {b->len,{0}};
    hs_copy(&tmp_b,b);
    hs_compact(&tmp_b);

    // A == B == emptyset
    bool empty_a = hs_is_empty(&tmp_a);
    bool empty_b = hs_is_empty(&tmp_b);

    if ((empty_a || empty_b)) {
        hs_destroy(&tmp_a);
        hs_destroy(&tmp_b);
        return (empty_a && !empty_b) || (empty_a && empty_b) || !(!empty_a && empty_b);
    }

    // A \isect B == emptyset
    struct hs tmp_isect = {tmp_a.len,{0}};
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
    struct hs tmp_minus = {tmp_a.len,{0}};
    hs_copy(&tmp_minus,&tmp_a);
    hs_minus(&tmp_minus,&tmp_b);
    if (!hs_is_empty(&tmp_minus)) {
        hs_destroy(&tmp_minus);
        hs_destroy(&tmp_a);
        hs_destroy(&tmp_b);
        return false;
    }
    hs_destroy(&tmp_minus);
    hs_destroy(&tmp_a);
    hs_destroy(&tmp_b);

    return true;
}

void
hs_vec_append (struct hs_vec *v, array_t *a, bool diff)
{ vec_append (v, a, diff); }
