/*
   Copyright 2018 Claas Lorenz

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#include "hs_unit.h"

void HeaderspaceTest::setUp() {
    h = hs_create(HS_TEST_LEN);
}

void HeaderspaceTest::tearDown() {
    hs_free(h);
}

void HeaderspaceTest::test_copy() {
    test_add();

    hs a;
    hs_copy(&a,h);

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_copy_a() {
    test_add();

    hs *a = hs_copy_a(h);

    CPPUNIT_ASSERT(hs_is_equal(h,a));

    hs_free(a);
}

void HeaderspaceTest::test_add() {
    printf("\n");

    hs_add(h,array_from_str("1xxxxxxx"));

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_add(&a,array_from_str("1xxxxxxx"));

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_add_hs() {
    test_add();

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_add(&a,array_from_str("0xxxxxxx"));

    struct hs b = {h->len, {0, 0, 0, 0}};
    hs_add(&b,array_from_str("0xxxxxxx"));
    hs_add(&b,array_from_str("1xxxxxxx"));

    hs *c = hs_copy_a(&a);
    hs_add_hs(h,c);
    hs_free(c);

    CPPUNIT_ASSERT(hs_is_equal(h,&b));

    hs_destroy(&b);
    hs_destroy(&a);
}

void HeaderspaceTest::test_diff() {
    test_add();

    hs *a = hs_copy_a(h);

    for (size_t i = 0; i < a->list.used; i++)
        hs_vec_append(&a->list.diff[i], array_from_str("1xxxxxx1"), true);

    array_t *b = array_from_str("1xxxxxx1");
    hs_diff(h,b);
    array_free(b);

    CPPUNIT_ASSERT(hs_is_equal(h,a));

    hs_free(a);
}

void HeaderspaceTest::test_compact() {
    test_add();

    hs *a = hs_copy_a(h);
    hs_vec_append(a->list.diff,array_from_str("11xxxxx1"),true);
    hs_vec_append(a->list.diff,array_from_str("10xxxxx1"),true);
    hs_vec_append(a->list.diff,array_from_str("10xxxxx1"),true);
    hs_vec_append(a->list.diff,array_from_str("11xxxxx1"),true);

    hs_vec_append(h->list.diff,array_from_str("11xxxxx1"),true);
    hs_vec_append(h->list.diff,array_from_str("10xxxxx1"),true);

    hs_compact(a);

    CPPUNIT_ASSERT(hs_is_equal(h,a));

    hs_free(a);
}

void HeaderspaceTest::test_compact_m() {
    test_add();

    hs *a = hs_copy_a(h);

    hs_vec_append(a->list.diff,array_from_str("11xxxxx1"),true);
    hs_vec_append(a->list.diff,array_from_str("10xxxxx1"),true);
    hs_vec_append(a->list.diff,array_from_str("10xx1xx1"),true);
    hs_vec_append(a->list.diff,array_from_str("111xxxx1"),true);

    hs_vec_append(h->list.diff,array_from_str("11xxxxx1"),true);
    hs_vec_append(h->list.diff,array_from_str("10xxxxx1"),true);

    array_t *b = array_from_str("11100001");
    hs_compact_m(a,b);
    array_free(b);

    CPPUNIT_ASSERT(hs_is_equal(h,a));

    hs_free(a);
}

void HeaderspaceTest::test_comp_diff() {
    test_add();

    struct hs a = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&h->list,array_from_str("01xxxxxx"),false);
    hs_vec_append(&h->list.diff[0],array_from_str("11xxxxx1"),true);
    hs_vec_append(&h->list.diff[0],array_from_str("10xxxxx1"),true);

    hs_vec_append(&a.list,array_from_str("01xxxxxx"),false);
    hs_vec_append(&a.list,array_from_str("10xxxxx0"),false);
    hs_vec_append(&a.list,array_from_str("11xxxxx0"),false);
    hs_vec_append(&a.list,array_from_str("1xxxxxx0"),false);

    hs_comp_diff(h);

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_cmpl() {
    test_add();

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("0xxxxxxx"),false);

    hs_cmpl(h);

    CPPUNIT_ASSERT(hs_is_equal(h,&a));
    hs_destroy(&a);

    hs_vec_append(&h->list.diff[0],array_from_str("0xxxxxx1"),true);
    hs_vec_append(&h->list,array_from_str("11xxxxxx"),false);

    struct hs b = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&b.list,array_from_str("10xxxxxx"),false);
    hs_vec_append(&b.list,array_from_str("00xxxxx1"),false);
    hs_vec_append(&b.list,array_from_str("0xxxxxx1"),false);

    hs_cmpl(h);

    CPPUNIT_ASSERT(hs_is_equal(h,&b));
    hs_destroy(&b);
}

void HeaderspaceTest::test_isect() {
    test_add();
    hs_vec_append(&h->list,array_from_str("01xxxxx0"),false);

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("0xxxxxx0"),false);
    hs_vec_append(&a.list,array_from_str("0xxxxxx1"),false);

    struct hs b = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&b.list,array_from_str("01xxxxx0"),false);

    hs_isect(h,&a);

    CPPUNIT_ASSERT(hs_is_equal(h,&b));
    hs_destroy(&a);
    hs_destroy(&b);

    struct hs c = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&c.list,array_from_str("10xxxxxx"),false);

    hs_isect(h,&c);

    CPPUNIT_ASSERT(hs_is_empty(h));
    hs_destroy(&c);
}

void HeaderspaceTest::test_isect_a() {
    test_add();
    hs_vec_append(&h->list,array_from_str("01xxxxx0"),false);

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("0xxxxxx0"),false);
    hs_vec_append(&a.list,array_from_str("0xxxxxx1"),false);

    struct hs b = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&b.list,array_from_str("01xxxxx0"),false);

    struct hs *c = hs_isect_a(h,&a);

    CPPUNIT_ASSERT(hs_is_equal(c,&b));
    hs_destroy(&a);
    hs_destroy(&b);

    struct hs d = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&d.list,array_from_str("10xxxxxx"),false);

    struct hs *e = hs_isect_a(c,&d);

    CPPUNIT_ASSERT(hs_is_empty(e));

    hs_destroy(&d);
    hs_free(c);
    hs_free(e);
}

void HeaderspaceTest::test_isect_arr() {
    test_add();

    struct hs a = {h->len, {0, 0, 0, 0}};

    array_t *v1 = array_from_str("1xxxxxx1");

    struct hs b = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&b.list,array_from_str("1xxxxxx1"),false);

    bool res = hs_isect_arr(&a,h,v1);

    CPPUNIT_ASSERT(res);
    CPPUNIT_ASSERT(hs_is_equal(&a,&b));

    hs_destroy(&a);
    hs_destroy(&b);
    array_free(v1);

    struct hs c = {h->len, {0, 0, 0, 0}};

    array_t *v2 = array_from_str("0xxxxxxx");

    res = hs_isect_arr(&c,h,v2);

    CPPUNIT_ASSERT(!res);
    CPPUNIT_ASSERT(hs_is_empty(&c));

    hs_destroy(&c);
    array_free(v2);
}

void HeaderspaceTest::test_minus() {
    test_add();
    hs_vec_append(&h->list,array_from_str("01xxxxxx"),false);
    hs_vec_append(h->list.diff,array_from_str("1xxxxxx1"),true);
    hs_vec_append(h->list.diff,array_from_str("01xxxxx1"),true);

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("01xxxxxx"),false);
    hs_vec_append(a.list.diff,array_from_str("01xxxxx1"),true);

    struct hs b = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&b.list,array_from_str("10xxxxx0"),false);
    hs_vec_append(&b.list,array_from_str("1xxxxxx0"),false);
    hs_vec_append(&b.list,array_from_str("01xxxxx1"),false);

    hs_minus(h,&a);

    CPPUNIT_ASSERT(hs_is_equal(h,&b));

    hs_destroy(&a);
    hs_destroy(&b);
}

void HeaderspaceTest::test_rewrite() {
    test_add();

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xx110x1"),false); // XXX: why not 0xx1xxx1?

    array_t *m  = array_from_str("11110011");
    array_t *rw = array_from_str("0xx110x1");

    hs_rewrite(h,m,rw);
    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
    array_free(m);
    array_free(rw);
}

void HeaderspaceTest::test_vec_append() {
    printf("\n");

    hs_vec_append(&h->list,array_from_str("1xxxxxxx"),false);
    hs_vec_append(&h->list.diff[0],array_from_str("1xxxxxx1"),true);

    struct hs a = {h->len, {0, 0, 0, 0}};
    array_t *b = array_from_str("1xxxxxxx");
    array_t *c = array_from_str("1xxxxxx1");

    struct hs_vec d = {0, 0, 0, 0};

    a.list.elems = (array_t **)xcalloc(1,sizeof *a.list.elems);
    a.list.alloc = 1;
    a.list.elems[0] = b;
    a.list.used = 1;

    a.list.diff = &d;
    d.elems = (array_t **)xcalloc(1,sizeof *d.elems);
    d.alloc = 1;
    d.elems[0] = c;
    d.used = 1;

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    d.elems[0] = NULL;
    array_free(c);
    a.list.diff = NULL;
    free(d.elems);

    a.list.elems[0] = NULL;
    array_free(b);
    free(a.list.elems);
}

void HeaderspaceTest::test_enlarge() {
    test_vec_append();

    struct hs a = {2, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xxxxxxxxxxxxxxx"),false);
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxxx1xxxxxxxx"),true);

    hs_enlarge(h,2);
    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}


#ifdef USE_DEPRECATED
void HeaderspaceTest::test_potponed_diff_and_rewrite() {
    printf("\n -> No tests implemented since this function is never used by \
net_plumber.\n");
}
#endif


void HeaderspaceTest::test_is_empty() {
    printf("\n");

    struct hs a = {1, {0, 0, 0, 0}};

    CPPUNIT_ASSERT(hs_is_empty(&a));

    hs_destroy(&a);

    hs *b = NULL;
    CPPUNIT_ASSERT(hs_is_empty(b));
}

void HeaderspaceTest::test_is_equal() {
    printf("\n");

    hs_vec_append(&h->list,array_from_str("10xxxxxx"),false);
    hs_vec_append(&h->list,array_from_str("11xxxxxx"),false);

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xxxxxxx"),false);

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_vec_append(h->list.diff,array_from_str("1xxxxxx1"),true);
    hs_vec_append(h->list.diff,array_from_str("1xxxxxx1"),true);

    hs_vec_append(a.list.diff,array_from_str("10xxxxx1"),true);
    hs_vec_append(a.list.diff,array_from_str("11xxxxx1"),true);

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_is_equal_regression() {
    printf("\n");

    struct hs a = {47, {0, 0, 0, 0}};
    hs_vec_append(
        &a.list,array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    struct hs b = {47, {0, 0, 0, 0}};
    hs_vec_append(
        &b.list,
        array_from_str("\
00000000,00000000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,00000001,00001101,10111000,\
00001010,10111100,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );
    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000001,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );
    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000010,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );
    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,10000000,xxxxxxxx,00000010,00000000,00000000,\
11010010,11110000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );
    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,10000001,xxxxxxxx,00000010,00000000,00000000,\
11010010,11110000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    CPPUNIT_ASSERT(!hs_is_equal(&a,&b));
    hs_destroy(&a);
    hs_destroy(&b);
}

void HeaderspaceTest::test_is_equal_and_is_sub_eq_regression() {

    struct hs a = {47, {0, 0, 0, 0}};

    hs_vec_append(
        &a.list,
        array_from_str("\
00000000,00000000,00000110,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,00000000,00010110,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000000,00000000,\
00000000,00000000,00000000,00000000,00000000,00000000,00000001\
"),
        false
    );

    struct hs b = {47, {0, 0, 0, 0}};

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000001,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000010,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,10000000,xxxxxxxx,00000010,00000000,00000000,\
11010010,11110000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,10000001,xxxxxxxx,00000010,00000000,00000000,\
11010010,11110000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000011,00000000,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000100,00000001,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000100,00000010,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00000100,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00101011,00000000,00000000,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00000100,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00101011,00000010,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00000100,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00101011,00000000,00000000,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00000100,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00101011,00000010,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00000100,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00101011,xxxxxxxx,00000000,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00000110,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,00000000,00010101,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000000,00000000,\
00000000,00000000,00000000,00000000,00000000,00000000,00000001\
"),
        false
    );

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00000110,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,00000000,01110011,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000000,00000000,\
00000000,00000000,00000000,00000000,00000000,00000000,00000001\
"),
        false
    );

    struct hs c = {47, {0, 0, 0, 0}};

    hs_vec_append(
        &c.list,
        array_create(47,BIT_X),
        false
    );

    CPPUNIT_ASSERT(!hs_is_equal(&c,&b));
    CPPUNIT_ASSERT(!hs_is_sub_eq(&a,&b));

    hs_destroy(&a);
    hs_destroy(&b);
    hs_destroy(&c);
}

void HeaderspaceTest::test_is_sub_regression() {
    struct hs a = {47, {0, 0, 0, 0}};

    hs_vec_append(
        &a.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        a.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000001,xxxxxxxx,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        a.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000010,xxxxxxxx,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        a.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000100,00000010,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        a.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000100,00000001,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        a.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000011,00000000,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    struct hs b = {47, {0, 0, 0, 0}};

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        false
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,00000001,00001101,10111000,\
00001010,10111100,00000000,00000001,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
00000000,00000000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,00000001,00001101,10111000,\
00001010,10111100,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00000100,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,00101011,xxxxxxxx,00000000,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00000100,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,00101011,00000010,00000001,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000001,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,10000000,xxxxxxxx,00000010,00000000,00000000,\
11010010,11110000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000010,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000100,00000010,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000100,00000001,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000011,00000000,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    hs_vec_append(
        b.list.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,10000001,xxxxxxxx,00000010,00000000,00000000,\
11010010,11110000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
"),
        true
    );

    CPPUNIT_ASSERT(hs_is_sub(&a,&b));

    hs_destroy(&a);
    hs_destroy(&b);
}


void HeaderspaceTest::test_is_sub() {
    test_add();

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xxxxxx1"),false);
    CPPUNIT_ASSERT(hs_is_sub(&a,h));

    hs_vec_append(&a.list,array_from_str("1xxxxxx0"),false);

    CPPUNIT_ASSERT(!hs_is_sub(&a,h));

    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxx11"),true);

    CPPUNIT_ASSERT(hs_is_sub(&a,h));

    hs_vec_append(&h->list.diff[0],array_from_str("1xxxxx11"),true);
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxx1x"),true);

    CPPUNIT_ASSERT(!hs_is_sub(&a,h));
    CPPUNIT_ASSERT(!hs_is_sub(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_is_sub_eq() {
    test_add();

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xxxxxx1"),false);
    CPPUNIT_ASSERT(hs_is_sub_eq(&a,h));

    hs_vec_append(&a.list,array_from_str("1xxxxxx0"),false);
    CPPUNIT_ASSERT(hs_is_sub_eq(&a,h));

    // h = 1xxxxxxx - 1xxxxx1x
    hs_vec_append(&h->list.diff[0],array_from_str("1xxxxx1x"),true);

    // a = (1xxxxxx1 - (1xxxxxx1 + 1xxxxxx0)) + (1xxxxxx0 - (1xxxxxx1 + 1xxxxxx0))
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxxx1"),true);
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxxx0"),true);
    hs_vec_append(&a.list.diff[1],array_from_str("1xxxxxx1"),true);
    hs_vec_append(&a.list.diff[1],array_from_str("1xxxxxx0"),true);

    CPPUNIT_ASSERT(hs_is_sub(&a,h));

    // a = (1xxxxxx1 - (1xxxxxx1 + 1xxxxxx0 + 1xxxxx1x)) +
    //     (1xxxxxx0 - (1xxxxxx1 + 1xxxxxx0))
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxx1x"),true);

    CPPUNIT_ASSERT(hs_is_sub_eq(&a,h));
    CPPUNIT_ASSERT(!hs_is_sub_eq(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_merge() {
    test_add();

    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xxxxxx1"),false);
    CPPUNIT_ASSERT(hs_is_sub(&a,h));

    hs_vec_append(&a.list,array_from_str("1xxxxxx0"),false);

    hs_simple_merge(&a);
    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}
