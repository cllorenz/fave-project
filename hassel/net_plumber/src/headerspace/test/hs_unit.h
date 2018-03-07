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

#ifndef SRC_NET_PLUMBER_TEST_HS_UNIT_H_
#define SRC_NET_PLUMBER_TEST_HS_UNIT_H_

#include "cppunit/TestCase.h"
#include "cppunit/TestFixture.h"
#include <cppunit/extensions/HelperMacros.h>
extern "C" {
  #include "../hs.h"
}

#define HS_TEST_LEN 1

class HeaderspaceTest : public CppUnit::TestFixture {
        CPPUNIT_TEST_SUITE(HeaderspaceTest);

        CPPUNIT_TEST(test_copy);
        CPPUNIT_TEST(test_copy_a);
        CPPUNIT_TEST(test_add);
        CPPUNIT_TEST(test_add_hs);
        CPPUNIT_TEST(test_diff);
        CPPUNIT_TEST(test_compact);
        CPPUNIT_TEST(test_compact_m);
        CPPUNIT_TEST(test_comp_diff);
        CPPUNIT_TEST(test_cmpl);
        CPPUNIT_TEST(test_isect);
        CPPUNIT_TEST(test_isect_a);
        CPPUNIT_TEST(test_isect_arr);
        CPPUNIT_TEST(test_minus);
        CPPUNIT_TEST(test_rewrite);
        CPPUNIT_TEST(test_vec_append);
        CPPUNIT_TEST(test_enlarge);
        CPPUNIT_TEST(test_potponed_diff_and_rewrite);
        CPPUNIT_TEST(test_is_empty);
        CPPUNIT_TEST(test_is_equal);
        CPPUNIT_TEST(test_is_equal_regression);
        CPPUNIT_TEST(test_is_sub);
        CPPUNIT_TEST(test_is_sub_eq);
        CPPUNIT_TEST(test_is_equal_and_is_sub_eq_regression);
        CPPUNIT_TEST(test_merge);

        CPPUNIT_TEST_SUITE_END();

    public:
        void setUp();
        void tearDown();

        void test_copy();
        void test_copy_a();
        void test_add();
        void test_add_hs();
        void test_diff();
        void test_compact();
        void test_compact_m();
        void test_comp_diff();
        void test_cmpl();
        void test_isect();
        void test_isect_a();
        void test_isect_arr();
        void test_minus();
        void test_rewrite();
        void test_vec_append();
        void test_enlarge();
        void test_potponed_diff_and_rewrite();
        void test_is_empty();
        void test_is_equal();
        void test_is_equal_regression();
        void test_is_sub();
        void test_is_sub_eq();
        void test_is_equal_and_is_sub_eq_regression();
        void test_merge();

    private:
        hs *h;
};

#endif  // SRC_NET_PLUMBER_TEST_HS_UNIT_H_
