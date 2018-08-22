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


#ifndef NET_PLUMBER_SLICING_UNIT_H_
#define NET_PLUMBER_SLICING_UNIT_H_

#include "cppunit/TestCase.h"
#include "cppunit/TestFixture.h"
#include <cppunit/extensions/HelperMacros.h>

class NetPlumberSlicingTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(NetPlumberSlicingTest);
  CPPUNIT_TEST(test_foobar);
  CPPUNIT_TEST_SUITE_END();

 public:
  void setUp();
  void tearDown();
  void test_foobar();
};

#endif  // NET_PLUMBER_SLICING_UNIT_H_
