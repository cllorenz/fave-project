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

        CPPUNIT_TEST(test_array_has_x);
        CPPUNIT_TEST(test_array_has_z);
        CPPUNIT_TEST(test_array_is_sub_eq);
        CPPUNIT_TEST(test_array_is_equal);
        CPPUNIT_TEST(test_array_is_sub);
        CPPUNIT_TEST(test_array_combine);
        CPPUNIT_TEST(test_array_merge);
        CPPUNIT_TEST(test_array_one_bit_subtract);
        CPPUNIT_TEST(test_array_and);
        CPPUNIT_TEST(test_array_cmpl);
        CPPUNIT_TEST(test_array_isect);
        CPPUNIT_TEST(test_array_not);
        CPPUNIT_TEST(test_array_rewrite);

        CPPUNIT_TEST_SUITE_END();

    public:
        void test_array_has_x();
        void test_array_has_z();
        void test_array_is_sub_eq();
        void test_array_is_equal();
        void test_array_is_sub();
        void test_array_combine();
        void test_array_merge();
        void test_array_one_bit_subtract();
        void test_array_and();
        void test_array_cmpl();
        void test_array_isect();
        void test_array_not();
        void test_array_rewrite();
};

#endif  // SRC_NET_PLUMBER_TEST_ARRAY_UNIT_H_
