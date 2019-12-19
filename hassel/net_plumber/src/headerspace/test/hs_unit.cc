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

using namespace log4cxx;

LoggerPtr HeaderspaceTest::logger(
    Logger::getLogger("NetPlumber-HeaderspaceUnitTest"));

void HeaderspaceTest::setUp() {
    h = hs_create(HS_TEST_LEN);
}

void HeaderspaceTest::tearDown() {
    hs_free(h);
}

void HeaderspaceTest::test_copy() {
    test_add();

#ifdef NEW_HS
    struct hs a = {0, {0, 0, 0}, {0, 0, 0}};
#else
    struct hs a = {0, {0, 0, 0, 0}};
#endif

    hs_copy(&a,h);

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_copy_a() {
    test_add();

    struct hs *a = hs_copy_a(h);

    CPPUNIT_ASSERT(hs_is_equal(h,a));

    hs_free(a);
}


void HeaderspaceTest::test_from_str() {
    hs_enlarge(h, 2);
    hs_vec_append(&h->list, array_from_str("xx10xx10,xxxxxxxx"), false);
    hs_vec_append(&h->list, array_from_str("11xx110x,xxxxxxxx"), false);
    hs_vec_append(&h->list.diff[1], array_from_str("1100110x,00000000"), true);
    hs_vec_append(&h->list.diff[1], array_from_str("11xx1x00,xxxxxxxx"), true);
    hs_vec_append(&h->list, array_from_str("010xxx10,10101010"), false);

    hs_print(h);

    struct hs *a = hs_from_str(
        "(xx10xx10,xxxxxxxx + (11xx110x,xxxxxxxx - ( 1100110x,00000000 + 11xx1x00,xxxxxxxx))+010xxx10,10101010)"
    );

    hs_print(a);

    CPPUNIT_ASSERT(hs_is_equal(h, a));

    hs_free(a);
}


void HeaderspaceTest::test_add() {
    printf("\n");

    hs_add(h,array_from_str("1xxxxxxx"));

#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};
#else
    struct hs a = {h->len, {0, 0, 0, 0}};
#endif
    hs_add(&a, array_from_str("1xxxxxxx"));

    debug("test_add(): h = ", h);
    debug("test_add(): a = ", &a);

    CPPUNIT_ASSERT(hs_is_equal(h, &a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_add_hs() {
    test_add();


#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};
#else
    struct hs a = {h->len, {0, 0, 0, 0}};
#endif
    hs_add(&a,array_from_str("0xxxxxxx"));

#ifdef NEW_HS
    struct hs b = {h->len, {0, 0, 0}, {0, 0, 0}};
#else
    struct hs b = {h->len, {0, 0, 0, 0}};
#endif
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

#ifdef NEW_HS
    hs_vec_append(&a->diff, array_from_str("1xxxxxx1"));
#else
    for (size_t i = 0; i < a->list.used; i++)
        hs_vec_append(&a->list.diff[i], array_from_str("1xxxxxx1"), true);
#endif

    array_t *b = array_from_str("1xxxxxx1");
    hs_diff(h,b);
    array_free(b);

    CPPUNIT_ASSERT(hs_is_equal(h,a));

    hs_free(a);
}

void HeaderspaceTest::test_compact() {
    test_add();

    hs *a = hs_copy_a(h);
#ifdef NEW_HS
    hs_vec_append(&a->diff,array_from_str("11xxxxx1"));
    hs_vec_append(&a->diff,array_from_str("10xxxxx1"));
    hs_vec_append(&a->diff,array_from_str("10xxxxx1"));
    hs_vec_append(&a->diff,array_from_str("11xxxxx1"));

    hs_vec_append(&h->diff,array_from_str("11xxxxx1"));
    hs_vec_append(&h->diff,array_from_str("10xxxxx1"));
#else
    hs_vec_append(a->list.diff,array_from_str("11xxxxx1"),true);
    hs_vec_append(a->list.diff,array_from_str("10xxxxx1"),true);
    hs_vec_append(a->list.diff,array_from_str("10xxxxx1"),true);
    hs_vec_append(a->list.diff,array_from_str("11xxxxx1"),true);

    hs_vec_append(h->list.diff,array_from_str("11xxxxx1"),true);
    hs_vec_append(h->list.diff,array_from_str("10xxxxx1"),true);
#endif

    hs_compact(a);

    CPPUNIT_ASSERT(hs_is_equal(h,a));

    hs_free(a);
}

void HeaderspaceTest::test_compact_m() {
    test_add();

    hs *a = hs_copy_a(h);

#ifdef NEW_HS
    hs_vec_append(&a->diff,array_from_str("11xxxxx1"));
    hs_vec_append(&a->diff,array_from_str("10xxxxx1"));
    hs_vec_append(&a->diff,array_from_str("10xx1xx1"));
    hs_vec_append(&a->diff,array_from_str("111xxxx1"));

    hs_vec_append(&h->diff,array_from_str("11xxxxx1"));
    hs_vec_append(&h->diff,array_from_str("10xxxxx1"));
#else
    hs_vec_append(a->list.diff,array_from_str("11xxxxx1"),true);
    hs_vec_append(a->list.diff,array_from_str("10xxxxx1"),true);
    hs_vec_append(a->list.diff,array_from_str("10xx1xx1"),true);
    hs_vec_append(a->list.diff,array_from_str("111xxxx1"),true);

    hs_vec_append(h->list.diff,array_from_str("11xxxxx1"),true);
    hs_vec_append(h->list.diff,array_from_str("10xxxxx1"),true);
#endif

    array_t *b = array_from_str("11100001");
    hs_compact_m(a,b);
    array_free(b);

    CPPUNIT_ASSERT(hs_is_equal(h,a));

    hs_free(a);
}

void HeaderspaceTest::test_comp_diff() {
    test_add();

#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(&h->list,array_from_str("01xxxxxx"));
    hs_vec_append(&h->diff,array_from_str("11xxxxx1"));
    hs_vec_append(&h->diff,array_from_str("10xxxxx1"));

    // XXX: old test broken? wtf?
    hs_vec_append(&a.list,array_from_str("01xxxxxx"));
//    hs_vec_append(&a.list,array_from_str("10xxxxx0"));
//    hs_vec_append(&a.list,array_from_str("11xxxxx0"));
//    hs_vec_append(&a.list,array_from_str("1xxxxxx0"));
    hs_vec_append(&a.list,array_from_str("1xxxxxxx"));
#else
    struct hs a = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&h->list,array_from_str("01xxxxxx"),false);
    hs_vec_append(&h->list.diff[0],array_from_str("11xxxxx1"),true);
    hs_vec_append(&h->list.diff[0],array_from_str("10xxxxx1"),true);

    hs_vec_append(&a.list,array_from_str("01xxxxxx"),false);
    hs_vec_append(&a.list,array_from_str("10xxxxx0"),false);
    hs_vec_append(&a.list,array_from_str("11xxxxx0"),false);
    hs_vec_append(&a.list,array_from_str("1xxxxxx0"),false);
#endif

    debug("test_comp_diff(): h  = ", h);

    hs_comp_diff(h);

    debug("test_comp_diff(): h' = ", h);
    debug("test_comp_diff(): a  = ", &a);

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_cmpl() {
    test_add();

    debug("test_cmpl(): ========== First test ==========", NULL);

#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("0xxxxxxx"));
#else
    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("0xxxxxxx"),false);
#endif

    debug("test_cmpl(): h = ", h);

    hs_cmpl(h);

    debug("test_cmpl(): ~h = ", h);
    debug("test_cmpl(): ~a = ", &a);

    CPPUNIT_ASSERT(hs_is_equal(h,&a));
    hs_destroy(&a);

    debug("test_cmpl(): ========== Second test ==========", NULL);

#ifdef NEW_HS
    hs_vec_append(&h->diff,array_from_str("0xxxxxx1"));
    hs_vec_append(&h->list,array_from_str("11xxxxxx"));
#else
    hs_vec_append(&h->list.diff[0],array_from_str("0xxxxxx1"),true);
    hs_vec_append(&h->list,array_from_str("11xxxxxx"),false);
#endif

#ifdef NEW_HS
    struct hs b = {h->len, {0, 0, 0}, {0, 0, 0}};

    // XXX: old test broken? wtf?
    //hs_vec_append(&b.list,array_from_str("10xxxxxx"));
    //hs_vec_append(&b.list,array_from_str("00xxxxx1"));
    //hs_vec_append(&b.list,array_from_str("0xxxxxx1"));
#else
    struct hs b = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&b.list,array_from_str("10xxxxxx"),false);
    hs_vec_append(&b.list,array_from_str("00xxxxx1"),false);
    hs_vec_append(&b.list,array_from_str("0xxxxxx1"),false);
#endif

    debug("test_cmpl(): h = ", h);

    hs_cmpl(h);

    debug("test_cmpl(): ~h = ", h);
    debug("test_cmpl(): b = ", &b);


    CPPUNIT_ASSERT(hs_is_equal(h,&b));
    hs_destroy(&b);

    debug("test_cmpl(): ========== Done ==========", NULL);
}

void HeaderspaceTest::test_isect() {
    test_add();

#ifdef NEW_HS
    hs_vec_append(&h->list,array_from_str("01xxxxx0"));

    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(&a.list,array_from_str("0xxxxxx0"));
    hs_vec_append(&a.list,array_from_str("0xxxxxx1"));

#else
    hs_vec_append(&h->list,array_from_str("01xxxxx0"),false);

    struct hs a = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&a.list,array_from_str("0xxxxxx0"),false);
    hs_vec_append(&a.list,array_from_str("0xxxxxx1"),false);
#endif

#ifdef NEW_HS
    struct hs b = {h->len, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(&b.list,array_from_str("01xxxxx0"));
#else
    struct hs b = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&b.list,array_from_str("01xxxxx0"),false);
#endif

    hs_isect(h,&a);

    CPPUNIT_ASSERT(hs_is_equal(h,&b));
    hs_destroy(&a);
    hs_destroy(&b);

#ifdef NEW_HS
    struct hs c = {h->len, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(&c.list,array_from_str("10xxxxxx"));
#else
    struct hs c = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&c.list,array_from_str("10xxxxxx"),false);
#endif

    hs_isect(h,&c);

    CPPUNIT_ASSERT(hs_is_empty(h));
    hs_destroy(&c);
}

void HeaderspaceTest::test_isect_a() {
    test_add();

    debug("test_isect_a(): ========== Test 1 ==========", NULL);

#ifdef NEW_HS
    hs_vec_append(&h->list,array_from_str("01xxxxx0"));

    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};


    hs_vec_append(&a.list,array_from_str("0xxxxxx0"));
    hs_vec_append(&a.list,array_from_str("0xxxxxx1"));
#else
    hs_vec_append(&h->list,array_from_str("01xxxxx0"),false);

    struct hs a = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&a.list,array_from_str("0xxxxxx0"),false);
    hs_vec_append(&a.list,array_from_str("0xxxxxx1"),false);
#endif

#ifdef NEW_HS
    struct hs b = {h->len, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(&b.list,array_from_str("01xxxxx0"));
#else
    struct hs b = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&b.list,array_from_str("01xxxxx0"),false);
#endif
    struct hs *c = hs_isect_a(h,&a);

    CPPUNIT_ASSERT(hs_is_equal(c,&b));
    hs_destroy(&a);
    hs_destroy(&b);

    debug("test_isect_a(): ========== Test 2 ==========", NULL);

#ifdef NEW_HS
    struct hs d = {h->len, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(&d.list,array_from_str("10xxxxxx"));
#else
    struct hs d = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&d.list,array_from_str("10xxxxxx"),false);
#endif
    struct hs *e = hs_isect_a(c,&d);

    CPPUNIT_ASSERT(hs_is_empty(e));

    hs_destroy(&d);
    hs_free(c);
    hs_free(e);
}

void HeaderspaceTest::test_isect_arr() {
    test_add();

#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};
#else
    struct hs a = {h->len, {0, 0, 0, 0}};
#endif

    array_t *v1 = array_from_str("1xxxxxx1");

#ifdef NEW_HS
    struct hs b = {h->len, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(&b.list,array_from_str("1xxxxxx1"));
#else
    struct hs b = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&b.list,array_from_str("1xxxxxx1"),false);
#endif
    bool res = hs_isect_arr(&a,h,v1);

    CPPUNIT_ASSERT(res);
    CPPUNIT_ASSERT(hs_is_equal(&a,&b));

    hs_destroy(&a);
    hs_destroy(&b);
    array_free(v1);

#ifdef NEW_HS
    struct hs c = {h->len, {0, 0, 0}, {0, 0, 0}};
#else
    struct hs c = {h->len, {0, 0, 0, 0}};
#endif

    array_t *v2 = array_from_str("0xxxxxxx");

    res = hs_isect_arr(&c,h,v2);

    CPPUNIT_ASSERT(!res);
    CPPUNIT_ASSERT(hs_is_empty(&c));

    hs_destroy(&c);
    array_free(v2);
}

void HeaderspaceTest::test_minus() {
    test_add();

#ifdef NEW_HS
    hs_vec_append(&h->list,array_from_str("01xxxxxx"));

    hs_vec_append(&h->diff,array_from_str("1xxxxxx1"));
    hs_vec_append(&h->diff,array_from_str("01xxxxx1"));
#else
    hs_vec_append(&h->list,array_from_str("01xxxxxx"),false);

    hs_vec_append(h->list.diff,array_from_str("1xxxxxx1"),true);
    hs_vec_append(h->list.diff,array_from_str("01xxxxx1"),true);
#endif

#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(&a.list,array_from_str("01xxxxxx"));
    hs_vec_append(&a.diff,array_from_str("01xxxxx1"));
#else
    struct hs a = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&a.list,array_from_str("01xxxxxx"),false);
    hs_vec_append(a.list.diff,array_from_str("01xxxxx1"),true);
#endif

#ifdef NEW_HS
    struct hs b = {h->len, {0, 0, 0}, {0, 0, 0}};

    //hs_vec_append(&b.list,array_from_str("10xxxxx0"));
    hs_vec_append(&b.list,array_from_str("1xxxxxx0"));
    //hs_vec_append(&b.list,array_from_str("01xxxxx1"));
#else
    struct hs b = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&b.list,array_from_str("10xxxxx0"),false);
    hs_vec_append(&b.list,array_from_str("1xxxxxx0"),false);
    hs_vec_append(&b.list,array_from_str("01xxxxx1"),false);
#endif

    debug("test_minus(): h = ", h);
    debug("test_minus(): a = ", &a);

    hs_minus(h,&a);

    debug("test_minus(): h - a = ", h);
    debug("test_minus(): b = ", &a);

    CPPUNIT_ASSERT(hs_is_equal(h,&b));

    hs_destroy(&a);
    hs_destroy(&b);
}

void HeaderspaceTest::test_rewrite() {
    test_add();

#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};
#ifdef STRICT_RW
    hs_vec_append(&a.list,array_from_str("0xx1xxx1"));
#else
    hs_vec_append(&a.list,array_from_str("1xx110x1")); // XXX: why not 0xx1xxx1?
#endif
#else
    struct hs a = {h->len, {0, 0, 0, 0}};
#ifdef STRICT_RW
    hs_vec_append(&a.list,array_from_str("0xx1xxx1"),false);
#else
    hs_vec_append(&a.list,array_from_str("1xx110x1"),false); // XXX: why not 0xx1xxx1?
#endif
#endif

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

#ifdef NEW_HS
    hs_vec_append(&h->list,array_from_str("1xxxxxxx"));
    hs_vec_append(&h->diff,array_from_str("1xxxxxx1"));
#else
    hs_vec_append(&h->list,array_from_str("1xxxxxxx"),false);
    hs_vec_append(&h->list.diff[0],array_from_str("1xxxxxx1"),true);
#endif

#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};
#else
    struct hs a = {h->len, {0, 0, 0, 0}};
#endif
    array_t *b = array_from_str("1xxxxxxx");
    array_t *c = array_from_str("1xxxxxx1");

#ifdef NEW_HS
    struct hs_vec d = {0, 0, 0};
#else
    struct hs_vec d = {0, 0, 0, 0};
#endif

    a.list.elems = (array_t **)xcalloc(1,sizeof *a.list.elems);
    a.list.alloc = 1;
    a.list.elems[0] = b;
    a.list.used = 1;

    d.elems = (array_t **)xcalloc(1,sizeof *d.elems);
    d.alloc = 1;
    d.elems[0] = c;
    d.used = 1;

#ifdef NEW_HS
    a.diff = d;
#else
    a.list.diff = &d;
#endif

    debug("test_vec_append(): h = ", h);
    debug("test_vec_append(): a = ", &a);

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    d.elems[0] = NULL;
    array_free(c);
#ifndef NEW_HS
    a.list.diff = NULL;
#endif
    free(d.elems);

    a.list.elems[0] = NULL;
    array_free(b);
    free(a.list.elems);
}

void HeaderspaceTest::test_enlarge() {
    test_vec_append();

#ifdef NEW_HS
    struct hs a = {2, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(&a.list,array_from_str("1xxxxxxxxxxxxxxx"));
    hs_vec_append(&a.diff,array_from_str("1xxxxxx1xxxxxxxx"));
#else
    struct hs a = {2, {0, 0, 0, 0}};

    hs_vec_append(&a.list,array_from_str("1xxxxxxxxxxxxxxx"),false);
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxxx1xxxxxxxx"),true);
#endif

    hs_enlarge(h,2);
    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}


#ifdef USE_DEPRECATED
void HeaderspaceTest::test_potponed_diff_and_rewrite() {
    debug("\n -> No tests implemented since this function is never used by \
net_plumber.\n", NULL);
}
#endif


void HeaderspaceTest::test_is_empty() {
    printf("\n");

#ifdef NEW_HS
    struct hs a = {1, {0, 0, 0}, {0, 0, 0}};
#else
    struct hs a = {1, {0, 0, 0, 0}};
#endif

    CPPUNIT_ASSERT(hs_is_empty(&a));

    hs_destroy(&a);

    hs *b = NULL;
    CPPUNIT_ASSERT(hs_is_empty(b));
}

void HeaderspaceTest::test_is_equal() {
    printf("\n");


#ifdef NEW_HS
    hs_vec_append(&h->list,array_from_str("10xxxxxx"));
    hs_vec_append(&h->list,array_from_str("11xxxxxx"));

    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(&a.list,array_from_str("1xxxxxxx"));

#else
    hs_vec_append(&h->list,array_from_str("10xxxxxx"),false);
    hs_vec_append(&h->list,array_from_str("11xxxxxx"),false);

    struct hs a = {h->len, {0, 0, 0, 0}};

    hs_vec_append(&a.list,array_from_str("1xxxxxxx"),false);
#endif

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

#ifdef NEW_HS
    hs_vec_append(&h->diff,array_from_str("1xxxxxx1"));

    hs_vec_append(&a.diff,array_from_str("10xxxxx1"));
    hs_vec_append(&a.diff,array_from_str("11xxxxx1"));

#else
    hs_vec_append(&h->list.diff[0],array_from_str("1xxxxxx1"),true);
    hs_vec_append(&h->list.diff[1],array_from_str("1xxxxxx1"),true);

    hs_vec_append(a.list.diff,array_from_str("10xxxxx1"),true);
    hs_vec_append(a.list.diff,array_from_str("11xxxxx1"),true);
#endif

    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_is_equal_regression() {
    printf("\n");

#ifdef NEW_HS
    struct hs a = {47, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(
        &a.list,array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );
#else
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
#endif


#ifdef NEW_HS
    struct hs b = {47, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(
        &b.list,
        array_from_str("\
00000000,00000000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,00000001,00001101,10111000,\
00001010,10111100,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
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
")
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
")
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
")
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
")
    );
#else
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
#endif

    CPPUNIT_ASSERT(!hs_is_equal(&a,&b));
    hs_destroy(&a);
    hs_destroy(&b);
}

void HeaderspaceTest::test_is_equal_and_is_sub_eq_regression() {

#ifdef NEW_HS
    struct hs a = {47, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(
        &a.list,
        array_from_str("\
00000000,00000000,00000110,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,00000000,00010110,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000000,00000000,\
00000000,00000000,00000000,00000000,00000000,00000000,00000001\
")
    );

#else
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
#endif



#ifdef NEW_HS
    struct hs b = {47, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000001,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
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
")
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
")
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
")
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
")
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
")
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
")
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
")
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
")
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
")
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
")
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
")
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
")
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
")
    );

#else
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
#endif


#ifdef NEW_HS
    struct hs c = {47, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(
        &c.list,
        array_create(47,BIT_X)
    );
#else
    struct hs c = {47, {0, 0, 0, 0}};

    hs_vec_append(
        &c.list,
        array_create(47,BIT_X),
        false
    );
#endif

    CPPUNIT_ASSERT(!hs_is_equal(&c,&b));
    CPPUNIT_ASSERT(!hs_is_sub_eq(&a,&b));

    hs_destroy(&a);
    hs_destroy(&b);
    hs_destroy(&c);
}

void HeaderspaceTest::test_is_sub_regression() {
#ifdef NEW_HS
    struct hs a = {47, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(
        &a.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &a.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000001,xxxxxxxx,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &a.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000010,xxxxxxxx,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &a.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000100,00000010,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &a.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000100,00000001,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &a.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000011,00000000,00100000,00000001,00001101,\
10111000,00001010,10111100,00000000,00100100,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

#else
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
#endif


#ifdef NEW_HS
    struct hs b = {47, {0, 0, 0}, {0, 0, 0}};

    hs_vec_append(
        &b.list,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );


    hs_vec_append(
        &b.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,00000001,00001101,10111000,\
00001010,10111100,00000000,00000001,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &b.diff,
        array_from_str("\
00000000,00000000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,00000001,00001101,10111000,\
00001010,10111100,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &b.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00000100,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,00101011,xxxxxxxx,00000000,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &b.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00000100,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,00101011,00000010,00000001,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &b.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000001,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &b.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,10000000,xxxxxxxx,00000010,00000000,00000000,\
11010010,11110000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &b.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000010,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &b.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000100,00000010,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &b.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000100,00000001,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &b.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,00000011,00000000,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );

    hs_vec_append(
        &b.diff,
        array_from_str("\
xxxxxxxx,xxxxxxxx,00111010,10000001,xxxxxxxx,00000010,00000000,00000000,\
11010010,11110000,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxx1,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00100000,\
00000001,00001101,10111000,00001010,10111100,00000000,00000001,xxxxxxxx,\
xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx\
")
    );
#else
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
#endif

    CPPUNIT_ASSERT(hs_is_sub(&a,&b));

    hs_destroy(&a);
    hs_destroy(&b);
}


void HeaderspaceTest::test_is_sub() {
    test_add();

    debug("test_is_sub(): ========== Test 1 ==========", NULL);

#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xxxxxx1"));
#else
    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xxxxxx1"),false);
#endif

    CPPUNIT_ASSERT(hs_is_sub(&a,h));

    debug("test_is_sub(): ========== Test 2 ==========", NULL);

#ifdef NEW_HS
    hs_vec_append(&a.list,array_from_str("1xxxxxx0"));
#else
    hs_vec_append(&a.list,array_from_str("1xxxxxx0"),false);
#endif

    CPPUNIT_ASSERT(!hs_is_sub(&a,h));

    debug("test_is_sub(): ========== Test 3 ==========", NULL);


#ifdef NEW_HS
    hs_vec_append(&a.diff,array_from_str("1xxxxx11"));
#else
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxx11"),true);
#endif

    debug("test_is_sub(): a = ", &a);
    debug("test_is_sub(): h = ", h);

    CPPUNIT_ASSERT(hs_is_sub(&a,h));

    debug("test_is_sub(): ========== Test 4 ==========", NULL);
#ifdef NEW_HS
    hs_vec_append(&h->diff,array_from_str("1xxxxx11"));
    hs_vec_append(&a.diff,array_from_str("1xxxxx1x"));
#else
    hs_vec_append(&h->list.diff[0],array_from_str("1xxxxx11"),true);
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxx1x"),true);
#endif

    CPPUNIT_ASSERT(!hs_is_sub(&a,h));

    debug("test_is_sub(): ========== Test 5 ==========", NULL);


    CPPUNIT_ASSERT(!hs_is_sub(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_is_sub_eq() {
    test_add();

    debug("test_is_sub_eq(): ========== Test 1 ==========", NULL);

#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};
    hs_vec_append(&a.list, array_from_str("1xxxxxx1"));
#else
    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xxxxxx1"),false);
#endif

    CPPUNIT_ASSERT(hs_is_sub_eq(&a,h));

    debug("test_is_sub_eq(): ========== Test 2 ==========", NULL);
#ifdef NEW_HS
    hs_vec_append(&a.list, array_from_str("1xxxxxx0"));
#else
    hs_vec_append(&a.list,array_from_str("1xxxxxx0"),false);
#endif
    CPPUNIT_ASSERT(hs_is_sub_eq(&a,h));

    debug("test_is_sub_eq(): ========== Test 3 ==========", NULL);
#ifdef NEW_HS
    // h = 1xxxxxxx - 1xxxxx1x = 1xxxxxxx + 0xxxxxxx + xxxxxx0x
    hs_vec_append(&h->diff, array_from_str("1xxxxx1x"));

    // a = (1xxxxxx1 + 1xxxxxx0) - (1xxxxxx1 + 1xxxxxx0) = (nil)
    hs_vec_append(&a.diff, array_from_str("1xxxxxx1"));
    hs_vec_append(&a.diff, array_from_str("1xxxxxx0"));
#else
    // h = 1xxxxxxx - 1xxxxx1x
    hs_vec_append(&h->list.diff[0],array_from_str("1xxxxx1x"),true);

    // a = (1xxxxxx1 - (1xxxxxx1 + 1xxxxxx0)) + (1xxxxxx0 - (1xxxxxx1 + 1xxxxxx0))
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxxx1"),true);
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxxx0"),true);
    hs_vec_append(&a.list.diff[1],array_from_str("1xxxxxx1"),true);
    hs_vec_append(&a.list.diff[1],array_from_str("1xxxxxx0"),true);
#endif

    CPPUNIT_ASSERT(hs_is_sub_eq(&a,h));

    debug("test_is_sub_eq(): ========== Test 4 ==========", NULL);
#ifdef NEW_HS
    // a = (1xxxxxx1 + 1xxxxxx0) - (1xxxxxx1 + 1xxxxxx0 + 1xxxxx1x) = (nil)
    hs_vec_append(&a.diff, array_from_str("1xxxxx1x"));
#else
    // a = (1xxxxxx1 - (1xxxxxx1 + 1xxxxxx0 + 1xxxxx1x)) +
    //     (1xxxxxx0 - (1xxxxxx1 + 1xxxxxx0))
    hs_vec_append(&a.list.diff[0],array_from_str("1xxxxx1x"),true);
#endif

    CPPUNIT_ASSERT(hs_is_sub_eq(&a, h));

    debug("test_is_sub_eq(): ========== Test 5 ==========", NULL);

    debug("test_is_sub_eq(): h = ", h);
    debug("test_is_sub_eq(): a = ", &a);

#ifdef NEW_HS
    CPPUNIT_ASSERT(hs_is_sub_eq(h,&a));
#else // XXX: broken test!
    CPPUNIT_ASSERT(hs_is_sub_eq(&a, h));
#endif

    debug("test_is_sub_eq(): ========== Test 6 ==========", NULL);
#ifdef NEW_HS
    CPPUNIT_ASSERT(hs_is_equal(h, &a));
#else // XXX: broken test!
    CPPUNIT_ASSERT(!hs_is_equal(h, &a));
#endif

    hs_destroy(&a);
}

void HeaderspaceTest::test_merge() {
    test_add();

#ifdef NEW_HS
    struct hs a = {h->len, {0, 0, 0}, {0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xxxxxx1"));
#else
    struct hs a = {h->len, {0, 0, 0, 0}};
    hs_vec_append(&a.list,array_from_str("1xxxxxx1"),false);
#endif

    CPPUNIT_ASSERT(hs_is_sub(&a,h));

#ifdef NEW_HS
    hs_vec_append(&a.list,array_from_str("1xxxxxx0"));
#else
    hs_vec_append(&a.list,array_from_str("1xxxxxx0"),false);
#endif

    hs_simple_merge(&a);
    CPPUNIT_ASSERT(hs_is_equal(h,&a));

    hs_destroy(&a);
}

void HeaderspaceTest::test_compact_regression() {
    struct hs a = {4, {0, 0, 0, 0}};
    hs_vec_append(&a.list, array_from_str("xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx"), false);
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001001x,xxxxxxxx"), true); // dip = 10.0.18.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001100x,xxxxxxxx"), true); // dip = 10.0.24.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001011x,xxxxxxxx"), true); // dip = 10.0.22.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001111x,xxxxxxxx"), true); // dip = 10.0.30.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001001x,xxxxxxxx"), true); // dip = 10.0.18.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0000111x,xxxxxxxx"), true); // dip = 10.0.12.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001000x,xxxxxxxx"), true); // dip = 10.0.16.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0000110x,xxxxxxxx"), true); // dip = 10.0.14.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001010x,xxxxxxxx"), true); // dip = 10.0.20.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("01111011,01111011,00110000,xxxxxxxx"), true); // dip = 123.123.48.0/24

    struct hs b = {4, {0, 0, 0, 0}};
    hs_vec_append(&b.list, array_from_str("xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx"), false);
    hs_vec_append(&b.list.diff[0], array_from_str("01111011,01111011,00110000,xxxxxxxx"), true); // dip = 123.123.48.0/24
    hs_vec_append(&b.list.diff[0], array_from_str("00001010,00000000,0001x0xx,xxxxxxxx"), true); // dip = 10.0.{16,18,24,26}.0/23
    hs_vec_append(&b.list.diff[0], array_from_str("00001010,00000000,0000111x,xxxxxxxx"), true); // dip = 10.0.14.0/23
    hs_vec_append(&b.list.diff[0], array_from_str("00001010,00000000,0001x11x,xxxxxxxx"), true); // dip = 10.0.{22,30}.0/23
    hs_vec_append(&b.list.diff[0], array_from_str("00001010,00000000,000xx10x,xxxxxxxx"), true); // dip = 10.0.{4,12,20,28}.0/23 <- this is wrong

    struct hs c = {4, {0, 0, 0, 0}};
    hs_vec_append(&c.list, array_from_str("xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx"), false);
    hs_vec_append(&c.list.diff[0], array_from_str("01111011,01111011,00110000,xxxxxxxx"), true); // dip = 123.123.48.0/24
    hs_vec_append(&c.list.diff[0], array_from_str("00001010,00000000,0001010x,xxxxxxxx"), true); // dip = 10.0.20.0/23
    hs_vec_append(&c.list.diff[0], array_from_str("00001010,00000000,00010x1x,xxxxxxxx"), true); // dip = 10.0.{18,22}.0/23
    hs_vec_append(&c.list.diff[0], array_from_str("00001010,00000000,0001x00x,xxxxxxxx"), true); // dip = 10.0.{16,24}.0/23
    hs_vec_append(&c.list.diff[0], array_from_str("00001010,00000000,0000110x,xxxxxxxx"), true); // dip = 10.0.12.0/23
    hs_vec_append(&c.list.diff[0], array_from_str("00001010,00000000,000x111x,xxxxxxxx"), true); // dip = 10.0.{14,30}.0/23

    hs_compact(&a);

    CPPUNIT_ASSERT(!hs_is_equal(&a, &b));
    CPPUNIT_ASSERT(hs_is_equal(&a, &c));

    hs_destroy(&a);
    hs_destroy(&b);
    hs_destroy(&c);
}


void HeaderspaceTest::test_is_equal_regression2() {
    printf("\n");

    struct hs a = {4, {0, 0, 0, 0}};
    hs_vec_append(&a.list, array_from_str("xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx"), false);
    hs_vec_append(&a.list.diff[0], array_from_str("01111011,01111011,00110000,xxxxxxxx"), true); // dip = 123.123.48.0/24
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001x0xx,xxxxxxxx"), true); // dip = 10.0.{16,18,24,26}.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0000111x,xxxxxxxx"), true); // dip = 10.0.14.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001x11x,xxxxxxxx"), true); // dip = 10.0.{22,30}.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,000xx10x,xxxxxxxx"), true); // dip = 10.0.{4,12,20,28}.0/23

    struct hs b = {4, {0, 0, 0, 0}};
    hs_vec_append(&b.list, array_from_str("xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx"), false);
    hs_vec_append(&b.list.diff[0], array_from_str("01111011,01111011,00110000,xxxxxxxx"), true); // dip = 123.123.48.0/24
    hs_vec_append(&b.list.diff[0], array_from_str("00001010,00000000,0001010x,xxxxxxxx"), true); // dip = 10.0.20.0/23
    hs_vec_append(&b.list.diff[0], array_from_str("00001010,00000000,00010x1x,xxxxxxxx"), true); // dip = 10.0.{18,22}.0/23
    hs_vec_append(&b.list.diff[0], array_from_str("00001010,00000000,0001x00x,xxxxxxxx"), true); // dip = 10.0.{16,24}.0/23
    hs_vec_append(&b.list.diff[0], array_from_str("00001010,00000000,0000110x,xxxxxxxx"), true); // dip = 10.0.12.0/23
    hs_vec_append(&b.list.diff[0], array_from_str("00001010,00000000,000x111x,xxxxxxxx"), true); // dip = 10.0.{14,30}.0/23

    CPPUNIT_ASSERT(!hs_is_equal(&a, &b));

    hs_destroy(&a);
    hs_destroy(&b);
}


void HeaderspaceTest::test_comp_diff_regression() {
    printf("\n");

    struct hs a = {4, {0, 0, 0, 0}};

    //                                     dip=0.0.0.0/0
    hs_vec_append(&a.list, array_from_str("xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx"), false);

    //                                             dip=123.123.123.0/24
    hs_vec_append(&a.list.diff[0], array_from_str("01111011,01111011,00110000,xxxxxxxx"), true);

    //                                             dip=10.0.12.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0000110x,xxxxxxxx"), true);

    //                                             dip=10.0.16.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001000x,xxxxxxxx"), true);

    //                                             dip=10.0.18.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001001x,xxxxxxxx"), true);

    //                                             dip=10.0.20.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001010x,xxxxxxxx"), true);

    //                                             dip=10.0.22.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001011x,xxxxxxxx"), true);

    //                                             dip=10.0.24.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001100x,xxxxxxxx"), true);

    //                                             dip=10.0.30.0/23
    hs_vec_append(&a.list.diff[0], array_from_str("00001010,00000000,0001111x,xxxxxxxx"), true);

    hs_comp_diff(&a); // test passes if no memory explosion occurs

    hs_destroy(&a);
}
