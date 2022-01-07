/*
   Copyright 2021 Claas Lorenz

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Authors: cllorenz@uni-potsdam.de (Claas Lorenz)
*/


#ifndef NET_PLUMBER_ANOMALIES_UNIT_H_
#define NET_PLUMBER_ANOMALIES_UNIT_H_

#include "cppunit/TestCase.h"
#include "cppunit/TestFixture.h"
#include <cppunit/extensions/HelperMacros.h>
#include "log4cxx/logger.h"
#include "../net_plumber.h"

using namespace net_plumber;

template<class T1, class T2>
class NetPlumberAnomaliesTest;

template<class T1, class T2>
NetPlumberAnomaliesTest<T1, T2> t_npat;

template<class T1, class T2>
class NetPlumberAnomaliesTest : public CppUnit::TestFixture {
  NetPlumber<T1, T2> *n;

  CPPUNIT_TEST_SUITE( decltype(t_npat<T1, T2>) );
  CPPUNIT_TEST(test_rule_shadowing);
#ifdef CHECK_REACH_SHADOW
  CPPUNIT_TEST(test_rule_reachability);
#endif
  CPPUNIT_TEST(test_rule_shadowing_regression);
  CPPUNIT_TEST_SUITE_END();

 public:
  void setUp();
  void tearDown();
  void test_rule_shadowing();
#ifdef CHECK_REACH_SHADOW
  void test_rule_reachability();
#endif
  void test_rule_shadowing_regression();
 private:
  static log4cxx::LoggerPtr logger;
};

#endif  // NET_PLUMBER_ANOMALIES_UNIT_H_
