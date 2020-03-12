/*
   Copyright 2012 Google Inc.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Author: peyman.kazemian@gmail.com (Peyman Kazemian)
*/


#ifndef PACKET_SET_UNIT_H_
#define PACKET_SET_UNIT_H_

#include "cppunit/TestCase.h"
#include "cppunit/TestFixture.h"
#include <cppunit/extensions/HelperMacros.h>



template<class PS1, class PS2>
class PacketSetTest;

template<class PS1, class PS2>
PacketSetTest<PS1, PS2> t_psu;

template<class PS1, class PS2>
class PacketSetTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE( decltype(t_psu<PS1, PS2>) );

  CPPUNIT_TEST(test_from_str);
  CPPUNIT_TEST(test_to_str);
  CPPUNIT_TEST(test_from_json);
  CPPUNIT_TEST(test_to_json);
  CPPUNIT_TEST(test_compact);
#ifndef USE_BDD
  CPPUNIT_TEST(test_unroll);
#endif
  CPPUNIT_TEST(test_count);
  CPPUNIT_TEST(test_enlarge);
  CPPUNIT_TEST(test_diff);
  CPPUNIT_TEST(test_intersect);
  CPPUNIT_TEST(test_psunion);
  CPPUNIT_TEST(test_minus);
#ifdef USE_INV
  CPPUNIT_TEST(test_psand);
#endif
  CPPUNIT_TEST(test_is_empty);
  CPPUNIT_TEST(test_is_equal);
  CPPUNIT_TEST(test_is_subset);
  CPPUNIT_TEST(test_is_subset_equal);
  CPPUNIT_TEST(test_rewrite);
  CPPUNIT_TEST(test_negate);

  CPPUNIT_TEST_SUITE_END();

 public:
  void setUp();
  void tearDown();
  void test_from_str();
  void test_to_str();
  void test_from_json();
  void test_to_json();
  void test_compact();
#ifndef USE_BDD
  void test_unroll();
#endif
  void test_count();
  void test_enlarge();
  void test_diff();
  void test_intersect();
  void test_psunion();
  void test_minus();
#ifdef USE_INV
  void test_psand();
#endif
  void test_is_empty();
  void test_is_equal();
  void test_is_subset();
  void test_is_subset_equal();
  void test_rewrite();
  void test_negate();

  private:
    PS1 *ps;
};
#endif  // PACKET_SET_UNIT_H_
