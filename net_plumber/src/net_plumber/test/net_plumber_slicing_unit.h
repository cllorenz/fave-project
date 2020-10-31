/*
   Copyright 2018 Jan Sohre

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Authors: jan@sohre.eu (Jan Sohre)
            cllorenz@uni-potsdam.de (Claas Lorenz)
*/


#ifndef NET_PLUMBER_SLICING_UNIT_H_
#define NET_PLUMBER_SLICING_UNIT_H_

#include "cppunit/TestCase.h"
#include "cppunit/TestFixture.h"
#include <cppunit/extensions/HelperMacros.h>
#include "log4cxx/logger.h"

template<class T1, class T2>
class NetPlumberSlicingTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(NetPlumberSlicingTest);
  CPPUNIT_TEST(test_add_slice_matrix);
  CPPUNIT_TEST(test_add_slice_matrix_errors);
  CPPUNIT_TEST(test_remove_slice_matrix);
  CPPUNIT_TEST(test_add_slice_allow);
  CPPUNIT_TEST(test_remove_slice_allow);
  CPPUNIT_TEST(test_add_slice);
  CPPUNIT_TEST(test_add_remove_slice_pipes);
  CPPUNIT_TEST(test_remove_slice);
  CPPUNIT_TEST(test_add_pipe_to_slices_matching);
  CPPUNIT_TEST(test_add_pipe_to_slices_not_matching);
  CPPUNIT_TEST(test_remove_pipe_from_slices);
  CPPUNIT_TEST(test_check_pipe_for_slice_leakage_no_exception);
  CPPUNIT_TEST(test_check_pipe_for_slice_leakage_with_exception);
  CPPUNIT_TEST(test_end_to_end);
  CPPUNIT_TEST_SUITE_END();

 public:
  void setUp();
  void tearDown();
  void test_add_slice_matrix();
  void test_add_slice_matrix_errors();
  void test_remove_slice_matrix();
  void test_add_slice_allow();
  void test_remove_slice_allow();
  void test_add_slice();
  void test_add_remove_slice_pipes();
  void test_remove_slice();
  void test_add_pipe_to_slices_matching();
  void test_add_pipe_to_slices_not_matching();
  void test_remove_pipe_from_slices();
  void test_check_pipe_for_slice_leakage_no_exception();
  void test_check_pipe_for_slice_leakage_with_exception();
  void test_end_to_end();
 private:
  static log4cxx::LoggerPtr logger;
};
#endif  // NET_PLUMBER_SLICING_UNIT_H_
