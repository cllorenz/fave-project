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

bool overlap_called = false;
void overlap_callback(NetPlumber *N, Flow *f, void *data) {
  overlap_called = true;
}

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
  auto np = NetPlumber(1);
  np.slice_overlap_callback = overlap_callback;
  char *hstr;

  CPPUNIT_ASSERT(np.slices.size() == 1);
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "DX");
  free(hstr);
  
  struct hs *net_space = hs_create(1);
  hs_add(net_space, array_from_str("1000xxxx"));

  CPPUNIT_ASSERT(np.add_slice(1, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  //TODO(jan): possibly add proper comparison (should be tested in hs-unit)
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) != "DX");
  free(hstr);
  hstr = hs_to_str(np.slices[1].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "1000xxxx");
  free(hstr);

  CPPUNIT_ASSERT(np.add_slice(2, net_space) == false);
  CPPUNIT_ASSERT(overlap_called == true);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  //TODO(jan): possibly add proper comparison (should be tested in hs-unit)
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) != "DX");
  free(hstr);
  hstr = hs_to_str(np.slices[1].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "1000xxxx");
  free(hstr);

  overlap_called = false;
  net_space = hs_create(1);
  hs_add(net_space, array_from_str("1001xxxx"));
  CPPUNIT_ASSERT(np.add_slice(2, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 3);
  //TODO(jan): possibly add proper comparison (should be tested in hs-unit)
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) != "DX");
  free(hstr);
  hstr = hs_to_str(np.slices[1].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "1000xxxx");
  free(hstr);
  hstr = hs_to_str(np.slices[2].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "1001xxxx");
  free(hstr);

  overlap_called = false;
  
  // currently would cause double free or corruption, due double assign
  // because of broken hs-unit
  //
  // overlap_called = false;
  // CPPUNIT_ASSERT(np.add_slice(3, net_space) == false);
  // CPPUNIT_ASSERT(overlap_called == true);
  // CPPUNIT_ASSERT(np.slices.size() == 3);
  // hstr = hs_to_str(np.slices[0].net_space);
  // CPPUNIT_ASSERT(std::string(hstr) != "DX");
  // free(hstr);
  // hstr = hs_to_str(np.slices[1].net_space);
  // CPPUNIT_ASSERT(std::string(hstr) == "1000xxxx");
  // free(hstr);
  // hstr = hs_to_str(np.slices[2].net_space);
  // CPPUNIT_ASSERT(std::string(hstr) == "1001xxxx");
  // free(hstr);
}

// represents small example with 6 pipes
//
//        _______  T1: 100xxxxx _______  S1
//       /
// S0   /________  T2: 101xxxxx _______  S2
//      \  
//       \_______  T3: default  _______  S3
void NetPlumberSlicingTest::test_add_remove_slice_pipes() {
  auto np = NetPlumber(1);
  np.slice_overlap_callback = overlap_callback;

  char *hstr;

  // add tables
  uint32_t t1ports[2] = { 101, 102 };
  List_t lt1ports = make_sorted_list_from_array(2, t1ports);
  np.add_table(1, lt1ports);

  uint32_t t2ports[2] = { 201, 202 };
  List_t lt2ports = make_sorted_list_from_array(2, t2ports);
  np.add_table(2, lt2ports);

  uint32_t t3ports[2] = { 301, 302 };
  List_t lt3ports = make_sorted_list_from_array(3, t3ports);
  np.add_table(3, lt3ports);

  // add links
  np.add_link(0, 101);
  np.add_link(0, 201);
  np.add_link(0, 301);
  np.add_link(102, 103);
  np.add_link(202, 203);
  np.add_link(302, 303);

  // add rules
  array_t *m1 = array_from_str("100xxxxx");
  array_t *m2 = array_from_str("101xxxxx");
  array_t *mask = array_from_str("xxxxxxxx");
  array_t *rw = NULL;

  uint32_t r1in[1] = { 101 };
  uint32_t r1out[1] = { 102 };
  uint32_t r2in[1] = { 201 };
  uint32_t r2out[1] = { 202 };
  uint32_t r3in[1] = { 301 };
  uint32_t r3out[1] = { 302 };

  List_t tr1in = make_sorted_list_from_array(1, r1in);
  List_t tr1out = make_sorted_list_from_array(1, r1out);
  List_t tr2in = make_sorted_list_from_array(1, r2in);
  List_t tr2out = make_sorted_list_from_array(1, r2out);
  List_t tr3in = make_sorted_list_from_array(1, r3in);
  List_t tr3out = make_sorted_list_from_array(1, r3out);

  np.add_rule(1, 1, tr1in, tr1out, array_copy(m1,1), array_copy(mask,1), rw);
  np.add_rule(1, 1, tr2in, tr2out, array_copy(m2,1), array_copy(mask,1), rw);
  np.add_rule(1, 1, tr3in, tr3out, array_copy(mask,1), array_copy(mask,1), rw);

  // add source
  uint32_t sl[1] = { 0 };
  List_t lsl = make_sorted_list_from_array(1, sl);
  struct hs *shs = hs_create(1);
  hs_add(shs, array_copy(mask,1));
  np.add_source(shs, lsl);

  // add source probes
  uint32_t s1[1] = { 103 };
  uint32_t s2[1] = { 203 };
  uint32_t s3[1] = { 303 };
  List_t ss1 = make_sorted_list_from_array(1, s1);
  List_t ss2 = make_sorted_list_from_array(1, s2);
  List_t ss3 = make_sorted_list_from_array(1, s3);
  PROBE_MODE mode = EXISTENTIAL;
  Condition *f1 = new FalseCondition();
  Condition *t1 = new TrueCondition();
  Condition *f2 = new FalseCondition();
  Condition *t2 = new TrueCondition();
  Condition *f3 = new FalseCondition();
  Condition *t3 = new TrueCondition();
  np.add_source_probe(ss1, mode, f1, t1, NULL, NULL);
  np.add_source_probe(ss2, mode, f2, t2, NULL, NULL);
  np.add_source_probe(ss3, mode, f3, t3, NULL, NULL);

  // create slices
  CPPUNIT_ASSERT(np.slices.size() == 1);
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "DX");
  free(hstr);
  // forward pipes + backward pipes
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 12);

  struct hs *net_space = hs_create(1);
  hs_add(net_space, array_from_str("100xxxxx"));
  CPPUNIT_ASSERT(np.add_slice(1, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) != "DX");
  free(hstr);
  hstr = hs_to_str(np.slices[1].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "100xxxxx");
  free(hstr);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 8);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 4);

  net_space = hs_create(1);
  hs_add(net_space, array_from_str("101xxxxx"));
  CPPUNIT_ASSERT(np.add_slice(2, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 3);
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) != "DX");
  free(hstr);
  hstr = hs_to_str(np.slices[1].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "100xxxxx");
  free(hstr);
  hstr = hs_to_str(np.slices[2].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "101xxxxx");
  free(hstr);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 4);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 4);
  CPPUNIT_ASSERT(np.slices[2].pipes.size() == 4);

  // test pipe reassignment after removal
  np.remove_slice(2);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) != "DX");
  free(hstr);
  hstr = hs_to_str(np.slices[1].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "100xxxxx");
  free(hstr);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 8);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 4);
  
  // cleanup
  free(m1);
  free(m2);
  free(mask);

  overlap_called = false;
}

void NetPlumberSlicingTest::test_remove_slice() {
  auto np = NetPlumber(1);
  np.slice_overlap_callback = overlap_callback;
  char *hstr;

  CPPUNIT_ASSERT(np.slices.size() == 1);
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "DX");
  free(hstr);
  
  struct hs *net_space = hs_create(1);
  hs_add(net_space, array_from_str("1000xxxx"));

  CPPUNIT_ASSERT(np.add_slice(1, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  //TODO(jan): possibly add proper comparison (should be tested in hs-unit)
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) != "DX");
  free(hstr);
  hstr = hs_to_str(np.slices[1].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "1000xxxx");
  free(hstr);

  np.remove_slice(0);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  //TODO(jan): possibly add proper comparison (should be tested in hs-unit)
  hstr = hs_to_str(np.slices[0].net_space);
  CPPUNIT_ASSERT(std::string(hstr) != "DX");
  free(hstr);
  hstr = hs_to_str(np.slices[1].net_space);
  CPPUNIT_ASSERT(std::string(hstr) == "1000xxxx");
  free(hstr);

  np.remove_slice(1);
  CPPUNIT_ASSERT(np.slices.size() == 1);
  hstr = hs_to_str(np.slices[0].net_space);
  //CPPUNIT_ASSERT(std::string(hstr) == "DX"); -- would work with proper compact
  free(hstr);
}
#endif /* PIPE_SLICING */
