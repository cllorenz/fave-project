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
  NetPlumber *n = new NetPlumber(1);
  std::map<uint64_t, std::set<uint64_t> >::iterator fk;
  std::set<uint64_t>::iterator fs;
  std::map<uint64_t, std::set<uint64_t> > m;

  n->add_slice_matrix(",1,2,3,4,5\n1,,x,x,x,\n2,x,,,,x\n3,,,,,\n4,,,x,,\n5,,,,,");
  m = n->get_slice_matrix();

  fk = m.find(1);
  CPPUNIT_ASSERT(fk != m.end());
  fk = m.find(2);
  CPPUNIT_ASSERT(fk != m.end());
  fk = m.find(3);
  CPPUNIT_ASSERT(fk == m.end());
  fk = m.find(4);
  CPPUNIT_ASSERT(fk != m.end());
  fk = m.find(5);
  CPPUNIT_ASSERT(fk == m.end());

  fs = m[1].find(2);
  CPPUNIT_ASSERT(fs != m[1].end());
  fs = m[1].find(3);
  CPPUNIT_ASSERT(fs != m[1].end());
  fs = m[1].find(4);
  CPPUNIT_ASSERT(fs != m[1].end());
  CPPUNIT_ASSERT(m[1].size() == 3);

  fs = m[2].find(1);
  CPPUNIT_ASSERT(fs != m[1].end());
  fs = m[2].find(5);
  CPPUNIT_ASSERT(fs != m[1].end());
  CPPUNIT_ASSERT(m[2].size() == 2);

  fs = m[4].find(3);
  CPPUNIT_ASSERT(fs != m[1].end());
  CPPUNIT_ASSERT(m[4].size() == 1);
}

void NetPlumberSlicingTest::test_remove_slice_matrix() {
  NetPlumber *n = new NetPlumber(1);
  std::map<uint64_t, std::set<uint64_t> > m;

  n->add_slice_matrix(",1,2,3,4,5\n1,,x,x,x,\n2,x,,,,x\n3,,,,,\n4,,,x,,\n5,,,,,");
  m = n->get_slice_matrix();
  CPPUNIT_ASSERT(m.size() != 0);

  n->remove_slice_matrix();
  m = n->get_slice_matrix();
  CPPUNIT_ASSERT(m.size() == 0);
}

void NetPlumberSlicingTest::test_add_slice_allow() {
  NetPlumber *n = new NetPlumber(1);
  std::map<uint64_t, std::set<uint64_t> > m;
  std::map<uint64_t, std::set<uint64_t> >::iterator fk;
  std::set<uint64_t>::iterator fs;
  
  m = n->get_slice_matrix();
  CPPUNIT_ASSERT(m.empty());

  n->add_slice_allow(1,1);
  m = n->get_slice_matrix();
  CPPUNIT_ASSERT(m.size()==1);
  fk = m.find(1);
  CPPUNIT_ASSERT(fk != m.end());
  fs = m[1].find(1);
  CPPUNIT_ASSERT(fs != m[1].end());
  CPPUNIT_ASSERT(m[1].size() == 1);
}

void NetPlumberSlicingTest::test_remove_slice_allow() {
  NetPlumber *n = new NetPlumber(1);
  std::map<uint64_t, std::set<uint64_t> > m;
  std::map<uint64_t, std::set<uint64_t> >::iterator fk;
  std::set<uint64_t>::iterator fs;

  m = n->get_slice_matrix();
  CPPUNIT_ASSERT(m.empty());

  n->add_slice_matrix(",1,2,3,4,5\n1,,x,x,x,\n2,x,,,,x\n3,,,,,\n4,,,x,,\n5,,,,,");
  m = n->get_slice_matrix();
  fk = m.find(2);
  CPPUNIT_ASSERT(fk != m.end());
  fs = m[2].find(1);
  CPPUNIT_ASSERT(fs != m[2].end());
  fs = m[2].find(5);
  CPPUNIT_ASSERT(fs != m[2].end());
  
  n->remove_slice_allow(2,1);
  m = n->get_slice_matrix();
  fk = m.find(2);
  CPPUNIT_ASSERT(fk != m.end());
  fs = m[2].find(1);
  CPPUNIT_ASSERT(fs == m[2].end());
  fs = m[2].find(5);
  CPPUNIT_ASSERT(fs != m[2].end());

  n->remove_slice_allow(2,5);
  m = n->get_slice_matrix();
  fk = m.find(2);
  CPPUNIT_ASSERT(fk == m.end());
}

void NetPlumberSlicingTest::test_add_slice() {

}

void NetPlumberSlicingTest::test_remove_slice() {

}

#endif //PIPE_SLICING
