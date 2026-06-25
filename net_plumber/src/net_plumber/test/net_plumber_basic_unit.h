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

   Authors: peyman.kazemian@gmail.com (Peyman Kazemian)
            cllorenz@uni-potsdam.de (Claas Lorenz)
*/


#ifndef NET_PLUMBER_BASIC_UNIT_H_
#define NET_PLUMBER_BASIC_UNIT_H_

#include "cppunit/TestCase.h"
#include "cppunit/TestFixture.h"
#include <cppunit/extensions/HelperMacros.h>

template<class T1, class T2>
class NetPlumberBasicTest;

template<class T1, class T2>
NetPlumberBasicTest<T1, T2> t_npbt;

template<class T1, class T2>
class NetPlumberBasicTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE( decltype(t_npbt<T1, T2>) );
  CPPUNIT_TEST(test_rule_node_create);
  CPPUNIT_TEST(test_create_topology);
  CPPUNIT_TEST(test_create_rule_id);
  CPPUNIT_TEST(test_remove_link);
  CPPUNIT_TEST(test_check_compliance_unknown_dst);
  // P1: orchestrator public-API contract tests
  CPPUNIT_TEST(test_event_api);
  CPPUNIT_TEST(test_rule_id_determinism_and_replacement);
  CPPUNIT_TEST(test_query_and_error_paths);
  CPPUNIT_TEST(test_source_lifecycle);
  CPPUNIT_TEST_SUITE_END();

 public:
  void setUp();
  void tearDown();
  void test_rule_node_create();
  void test_create_topology();
  void test_create_rule_id();
  void test_remove_link();
  void test_check_compliance_unknown_dst();
  void test_event_api();
  void test_rule_id_determinism_and_replacement();
  void test_query_and_error_paths();
  void test_source_lifecycle();
};

#endif  // NET_PLUMBER_BASIC_UNIT_H_
