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

   Author: Jan Sohre (jan@sohre.eu)
*/

#ifdef PIPE_SLICING

#include "net_plumber_slicing_unit.h"
#include "../net_plumber.h"
#include "../net_plumber_utils.h"
#include <sstream>

using namespace net_plumber;
using namespace log4cxx;

LoggerPtr NetPlumberSlicingTest::logger(
    Logger::getLogger("NetPlumber-SlicingUnitTest"));

void NetPlumberSlicingTest::setUp() {
}

void NetPlumberSlicingTest::tearDown() {
}

void NetPlumberSlicingTest::test_add_slice_matrix() {
  auto np = NetPlumber(1);
  np.add_slice_matrix(",1,2,3,4,5\n1,,x,x,x,\n2,x,,,,x\n3,,,,,\n4,,,x,,\n5,,,,,");

  auto fk = np.matrix.find(1);
  CPPUNIT_ASSERT(fk != np.matrix.end());
  fk = np.matrix.find(2);
  CPPUNIT_ASSERT(fk != np.matrix.end());
  fk = np.matrix.find(3);
  CPPUNIT_ASSERT(fk == np.matrix.end());
  fk = np.matrix.find(4);
  CPPUNIT_ASSERT(fk != np.matrix.end());
  fk = np.matrix.find(5);
  CPPUNIT_ASSERT(fk == np.matrix.end());

  auto fs = np.matrix.find(1);
  auto fe = fs->second.find(1);
  CPPUNIT_ASSERT(fe == fs->second.end());
  fe = fs->second.find(2);
  CPPUNIT_ASSERT(fe != fs->second.end());
  fe = fs->second.find(3);
  CPPUNIT_ASSERT(fe != fs->second.end());
  fe = fs->second.find(4);
  CPPUNIT_ASSERT(fe != fs->second.end());
  fe = fs->second.find(5);
  CPPUNIT_ASSERT(fe == fs->second.end());
  CPPUNIT_ASSERT(fs->second.size() == 3);

  fs = np.matrix.find(2);
  fe = fs->second.find(1);
  CPPUNIT_ASSERT(fe != fs->second.end());
  fe = fs->second.find(2);
  CPPUNIT_ASSERT(fe == fs->second.end());
  fe = fs->second.find(3);
  CPPUNIT_ASSERT(fe == fs->second.end());
  fe = fs->second.find(4);
  CPPUNIT_ASSERT(fe == fs->second.end());
  fe = fs->second.find(5);
  CPPUNIT_ASSERT(fe != fs->second.end());
  CPPUNIT_ASSERT(fs->second.size() == 2);

  fs = np.matrix.find(4);
  fe = fs->second.find(1);
  CPPUNIT_ASSERT(fe == fs->second.end());
  fe = fs->second.find(2);
  CPPUNIT_ASSERT(fe == fs->second.end());
  fe = fs->second.find(3);
  CPPUNIT_ASSERT(fe != fs->second.end());
  fe = fs->second.find(4);
  CPPUNIT_ASSERT(fe == fs->second.end());
  fe = fs->second.find(5);
  CPPUNIT_ASSERT(fe == fs->second.end());
  CPPUNIT_ASSERT(fs->second.size() == 1);
}

void NetPlumberSlicingTest::test_remove_slice_matrix() {
  auto np = NetPlumber(1);
  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,")
		 == true);
  CPPUNIT_ASSERT(np.matrix.size() != 0);

  np.remove_slice_matrix();
  CPPUNIT_ASSERT(np.matrix.size() == 0);
}

void NetPlumberSlicingTest::test_add_slice_allow() {
  auto np = NetPlumber(1);
  CPPUNIT_ASSERT(np.matrix.empty());

  np.add_slice_allow(1,1);
  CPPUNIT_ASSERT(np.matrix.size() == 1);

  auto fk = np.matrix.find(1);
  CPPUNIT_ASSERT(fk != np.matrix.end());
  auto fs = fk->second.find(1);
  CPPUNIT_ASSERT(fs != fk->second.end());
  CPPUNIT_ASSERT(fk->second.size() == 1);
}

void NetPlumberSlicingTest::test_remove_slice_allow() {
  auto np = NetPlumber(1);
  CPPUNIT_ASSERT(np.matrix.empty());
  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,")
		 == true);
  CPPUNIT_ASSERT(!np.matrix.empty());

  // check that all key-id mappings are present
  auto fk = np.matrix.find(2);
  CPPUNIT_ASSERT(fk != np.matrix.end());
  auto fs = fk->second.find(1);
  CPPUNIT_ASSERT(fs != fk->second.end());
  fs = fk->second.find(5);
  CPPUNIT_ASSERT(fs != fk->second.end());

  // should remove id 1 from set 2
  np.remove_slice_allow(2,1);
  np.print_slice_matrix();
  fk = np.matrix.find(2);
  CPPUNIT_ASSERT(fk != np.matrix.end());
  fs = fk->second.find(1);
  CPPUNIT_ASSERT(fs == fk->second.end());
  fs = fk->second.find(5);
  CPPUNIT_ASSERT(fs != fk->second.end());

  // should remove entire key from map
  np.remove_slice_allow(2,5);
  fk = np.matrix.find(2);
  CPPUNIT_ASSERT(fk == np.matrix.end());
}

void NetPlumberSlicingTest::test_add_slice() {

}

void NetPlumberSlicingTest::test_remove_slice() {

}

#endif /* PIPE_SLICING */
