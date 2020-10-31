/*
  Copyright 2018, Claas Lorenz. This file is licensed under GPL v2 plus
  a special exception, as described in included LICENSE_EXCEPTION.txt.

  Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#ifndef SRC_NET_PLUMBER_TEST_ARRAY_UNIT_H_
#define SRC_NET_PLUMBER_TEST_ARRAY_UNIT_H_

#include "cppunit/TestCase.h"
#include "cppunit/TestFixture.h"
#include <cppunit/extensions/HelperMacros.h>
extern "C" {
  #include "../array.h"
}

class ArrayTest : public CppUnit::TestFixture {
        CPPUNIT_TEST_SUITE(ArrayTest);

        CPPUNIT_TEST(test_array_all_x);
        CPPUNIT_TEST(test_array_has_x);
        CPPUNIT_TEST(test_array_has_z);
        CPPUNIT_TEST(test_array_is_sub_eq);
        CPPUNIT_TEST(test_array_is_equal);
        CPPUNIT_TEST(test_array_is_sub);
        CPPUNIT_TEST(test_array_combine);
        CPPUNIT_TEST(test_array_merge);
        CPPUNIT_TEST(test_array_one_bit_subtract);
#ifdef USE_INV
        CPPUNIT_TEST(test_array_and);
#endif
        CPPUNIT_TEST(test_array_cmpl);
        CPPUNIT_TEST(test_array_isect);
        CPPUNIT_TEST(test_array_not);
        CPPUNIT_TEST(test_array_rewrite);
        CPPUNIT_TEST(test_array_generic_resize);
        CPPUNIT_TEST(test_array_combine_regression);
        CPPUNIT_TEST(test_array_has_xz_regression);

        CPPUNIT_TEST_SUITE_END();

    public:
        void test_array_all_x();
        void test_array_has_x();
        void test_array_has_z();
        void test_array_is_sub_eq();
        void test_array_is_equal();
        void test_array_is_sub();
        void test_array_combine();
        void test_array_merge();
        void test_array_one_bit_subtract();
#ifdef USE_INV
        void test_array_and();
#endif
        void test_array_cmpl();
        void test_array_isect();
        void test_array_not();
        void test_array_rewrite();
        void test_array_generic_resize();
        void test_array_combine_regression();
        void test_array_has_xz_regression();
};

#endif  // SRC_NET_PLUMBER_TEST_ARRAY_UNIT_H_
