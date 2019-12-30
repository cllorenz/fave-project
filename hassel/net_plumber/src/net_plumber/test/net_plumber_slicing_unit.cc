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
#include "../array_packet_set.h"
#include "../hs_packet_set.h"

using namespace net_plumber;
using namespace log4cxx;

// override standard callbacks for testing
bool overlap_called = false;
template<class T1, class T2>
void overlap_callback(NetPlumber<T1, T2>* /*N*/, Flow<T1, T2>* /*f*/, void* /*data*/) {
  overlap_called = true;
}
bool leakage_called = false;
template<class T1, class T2>
void leakage_callback(NetPlumber<T1, T2>* /*N*/, Flow<T1, T2>* /*f*/, void* /*data*/) {
  leakage_called = true;
}

template<class T1, class T2>
LoggerPtr NetPlumberSlicingTest<T1, T2>::logger(
    Logger::getLogger("NetPlumber-SlicingUnitTest"));

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::setUp() {
}

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::tearDown() {
}

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_add_slice_matrix() {
  auto np = NetPlumber<T1, T2>(1);
  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == true);

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

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_add_slice_matrix_errors() {
  auto np = NetPlumber<T1, T2>(1);

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == true);
  // 3 == number of lines where some exception is set
  CPPUNIT_ASSERT(np.matrix.size() == 3);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix("a,1,2,3,4,5,\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix("aaa,1,2,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(" ,1,2,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5,\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,18446744073709551616,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2abc,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,abc2,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "1,,x,x,x,,,,,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();
  
  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "1,,x,x,x,,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "abc,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "18446744073709551616,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "18449551616,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,x,,\n"
				     "6,,,x,,\n"
				     "7,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,3,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "4,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();

  CPPUNIT_ASSERT(np.add_slice_matrix(",1,2,2,4,5\n"
				     "1,,x,x,x,\n"
				     "2,x,,,,x\n"
				     "3,,,,,\n"
				     "4,,,x,,\n"
				     "5,,,,,") == false);
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.remove_slice_matrix();
}

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_remove_slice_matrix() {
  auto np = NetPlumber<T1, T2>(1);
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

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_add_slice_allow() {
  auto np = NetPlumber<T1, T2>(1);
  CPPUNIT_ASSERT(np.matrix.empty());

  np.add_slice_allow(1,1);
  CPPUNIT_ASSERT(np.matrix.size() == 1);

  auto fk = np.matrix.find(1);
  CPPUNIT_ASSERT(fk != np.matrix.end());
  auto fs = fk->second.find(1);
  CPPUNIT_ASSERT(fs != fk->second.end());
  CPPUNIT_ASSERT(fk->second.size() == 1);
}

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_remove_slice_allow() {
  auto np = NetPlumber<T1, T2>(1);
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

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_add_slice() {
  auto np = NetPlumber<T1, T2>(1);
  np.slice_overlap_callback = overlap_callback;
  std::string hstr;

  CPPUNIT_ASSERT(np.slices.size() == 1);
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "xxxxxxxx");
  hstr.clear();
  
  T1 *net_space = new T1("1000xxxx");

  CPPUNIT_ASSERT(np.add_slice(1, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  //TODO(jan): possibly add proper comparison (should be tested in hs-unit)
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr != "xxxxxxxx");
  hstr.clear();
  hstr = np.slices[1].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "1000xxxx");
  hstr.clear();

  CPPUNIT_ASSERT(np.add_slice(2, net_space) == false);
  CPPUNIT_ASSERT(overlap_called == true);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  //TODO(jan): possibly add proper comparison (should be tested in hs-unit)
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr != "xxxxxxxx");
  hstr.clear();
  hstr = np.slices[1].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "1000xxxx");
  hstr.clear();

  overlap_called = false;
  net_space = new T1("1001xxxx");
  CPPUNIT_ASSERT(np.add_slice(2, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 3);
  //TODO(jan): possibly add proper comparison (should be tested in hs-unit)
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr != "xxxxxxxx");
  hstr.clear();
  hstr = np.slices[1].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "1000xxxx");
  hstr.clear();
  hstr = np.slices[2].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "1001xxxx");
  hstr.clear();

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
  // hstr.clear();
  // hstr = hs_to_str(np.slices[1].net_space);
  // CPPUNIT_ASSERT(std::string(hstr) == "1000xxxx");
  // hstr.clear();
  // hstr = hs_to_str(np.slices[2].net_space);
  // CPPUNIT_ASSERT(std::string(hstr) == "1001xxxx");
  // hstr.clear();
}

// represents small example with 6 pipes
/*
       _______  T1: 100xxxxx _______  S1
      /
S0   /________  T2: 101xxxxx _______  S2
     \ 
      \_______  T3: default  _______  S3

*/
template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_add_remove_slice_pipes() {
  auto np = NetPlumber<T1, T2>(1);
  np.slice_overlap_callback = overlap_callback;

  std::string hstr;

  // add tables
  uint32_t t1ports[2] = { 101, 102 };
  List_t lt1ports = make_sorted_list_from_array(2, t1ports);
  np.add_table(1, lt1ports);

  uint32_t t2ports[2] = { 201, 202 };
  List_t lt2ports = make_sorted_list_from_array(2, t2ports);
  np.add_table(2, lt2ports);

  uint32_t t3ports[2] = { 301, 302 };
  List_t lt3ports = make_sorted_list_from_array(2, t3ports);
  np.add_table(3, lt3ports);

  // add links
  np.add_link(0, 101);
  np.add_link(0, 201);
  np.add_link(0, 301);
  np.add_link(102, 103);
  np.add_link(202, 203);
  np.add_link(302, 303);

  // add rules
  T2 *m1 = new T2(std::string("100xxxxx"));
  T2 *m2 = new T2(std::string("101xxxxx"));
  T2 *mask = new T2(std::string("xxxxxxxx"));
  T2 *rw = NULL;

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

  np.add_rule(1, 1, tr1in, tr1out, new T2(*m1), new T2(*mask), rw);
  np.add_rule(2, 1, tr2in, tr2out, new T2(*m2), new T2(*mask), rw);
  np.add_rule(3, 1, tr3in, tr3out, new T2(*mask), new T2(*mask), rw);

  // add source
  uint32_t sl[1] = { 0 };
  List_t lsl = make_sorted_list_from_array(1, sl);
  T1 *shs = new T1(1);
  shs->psunion2(mask);
  np.add_source(shs, lsl);

  // add source probes
  uint32_t s1[1] = { 103 };
  uint32_t s2[1] = { 203 };
  uint32_t s3[1] = { 303 };
  List_t ss1 = make_sorted_list_from_array(1, s1);
  List_t ss2 = make_sorted_list_from_array(1, s2);
  List_t ss3 = make_sorted_list_from_array(1, s3);
  PROBE_MODE mode = EXISTENTIAL;
  Condition<T1, T2> *f1 = new FalseCondition<T1, T2>();
  Condition<T1, T2> *t1 = new TrueCondition<T1, T2>();
  Condition<T1, T2> *f2 = new FalseCondition<T1, T2>();
  Condition<T1, T2> *t2 = new TrueCondition<T1, T2>();
  Condition<T1, T2> *f3 = new FalseCondition<T1, T2>();
  Condition<T1, T2> *t3 = new TrueCondition<T1, T2>();
  np.add_source_probe(ss1, mode, f1, t1, NULL, NULL);
  np.add_source_probe(ss2, mode, f2, t2, NULL, NULL);
  np.add_source_probe(ss3, mode, f3, t3, NULL, NULL);

  // create slices
  CPPUNIT_ASSERT(np.slices.size() == 1);
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "xxxxxxxx");
  hstr.clear();
  // forward pipes + backward pipes
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 12);

  T1 *net_space = new T1("100xxxxx");
  CPPUNIT_ASSERT(np.add_slice(1, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr != "xxxxxxxx");
  hstr.clear();
  hstr = np.slices[1].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "100xxxxx");
  hstr.clear();
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 8);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 4);

  net_space = new T1("101xxxxx");
  CPPUNIT_ASSERT(np.add_slice(2, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 3);
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr != "xxxxxxxx");
  hstr.clear();
  hstr = np.slices[1].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "100xxxxx");
  hstr.clear();
  hstr = np.slices[2].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "101xxxxx");
  hstr.clear();
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 4);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 4);
  CPPUNIT_ASSERT(np.slices[2].pipes.size() == 4);

  // test pipe reassignment after removal
  np.remove_slice(2);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr != "xxxxxxxx");
  hstr.clear();
  hstr = np.slices[1].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "100xxxxx");
  hstr.clear();
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 8);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 4);
  
  // cleanup
  free(m1);
  free(m2);
  free(mask);

  overlap_called = false;
}

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_remove_slice() {
  auto np = NetPlumber<T1, T2>(1);
  np.slice_overlap_callback = overlap_callback;
  std::string hstr;

  CPPUNIT_ASSERT(np.slices.size() == 1);
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "xxxxxxxx");
  hstr.clear();
  
  T1 *net_space = new T1("1000xxxx");

  CPPUNIT_ASSERT(np.add_slice(1, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  //TODO(jan): possibly add proper comparison (should be tested in hs-unit)
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr != "xxxxxxxx");
  hstr.clear();
  hstr = np.slices[1].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "1000xxxx");
  hstr.clear();

  np.remove_slice(0);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  //TODO(jan): possibly add proper comparison (should be tested in hs-unit)
  hstr = np.slices[0].net_space->to_str();
  CPPUNIT_ASSERT(hstr != "xxxxxxxx");
  hstr.clear();
  hstr = np.slices[1].net_space->to_str();
  CPPUNIT_ASSERT(hstr == "1000xxxx");
  hstr.clear();

  np.remove_slice(1);
  CPPUNIT_ASSERT(np.slices.size() == 1);
  hstr = np.slices[0].net_space->to_str();
  //CPPUNIT_ASSERT(std::string(hstr) == "DX"); -- would work with proper compact
  hstr.clear();
}

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_add_pipe_to_slices_matching() {
  auto np = NetPlumber<T1, T2>(1);
  auto pipe1 = Pipeline<T1, T2>();

  T2 *mask = new T2(std::string("xxxxxxxx"));
  T1 *space = new T1(1);
  space->psunion2(mask);

  uint32_t nports[1] = { 0 };
  List_t lnports = make_sorted_list_from_array(1, nports);

  auto nid = np.add_source(space, lnports);
  auto node = np.id_to_node[nid];
  pipe1.node = node;
  pipe1.net_space_id = 0;
  pipe1.pipe_array = new T2(std::string("100xxxxx"));

  space = new T1("100xxxxx");
  CPPUNIT_ASSERT(np.add_slice(1, space) == true);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 0);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 0);

  np.add_pipe_to_slices(&pipe1);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 0);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 1);
  CPPUNIT_ASSERT(pipe1.net_space_id == 1);

  // cleanup
  free(pipe1.pipe_array);
  free(mask);
}

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_add_pipe_to_slices_not_matching() {
  auto np = NetPlumber<T1, T2>(1);
  auto pipe1 = Pipeline<T1, T2>();

  T2 *mask = new T2(std::string("xxxxxxxx"));
  T1 *space = new T1(1);
  space->psunion2(mask);

  uint32_t nports[1] = { 0 };
  List_t lnports = make_sorted_list_from_array(1, nports);

  auto nid = np.add_source(space, lnports);
  auto node = np.id_to_node[nid];
  pipe1.node = node;
  pipe1.net_space_id = 0;
  pipe1.pipe_array = new T2(std::string("101xxxxx"));

  space = new T1("100xxxxx");
  CPPUNIT_ASSERT(np.add_slice(1, space) == true);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 0);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 0);

  np.add_pipe_to_slices(&pipe1);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 1);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 0);
  CPPUNIT_ASSERT(pipe1.net_space_id == 0);

  // cleanup
  free(pipe1.pipe_array);
  free(mask);
}

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_remove_pipe_from_slices() {
  auto np = NetPlumber<T1, T2>(1);
  auto pipe1 = Pipeline<T1, T2>();
  auto pipe2 = Pipeline<T1, T2>();
  
  T2 *mask = new T2(std::string("xxxxxxxx"));
  T1 *space = new T1(1);
  space->psunion2(mask);

  uint32_t nports[1] = { 0 };
  List_t lnports = make_sorted_list_from_array(1, nports);

  auto nid = np.add_source(space, lnports);
  auto node = np.id_to_node[nid];
  pipe1.node = node;
  pipe1.net_space_id = 0;
  pipe1.pipe_array = new T2(std::string("100xxxxx"));
  pipe2.node = node;
  pipe2.net_space_id = 5;
  pipe2.pipe_array = new T2(std::string("101xxxxx"));

  space = new T1("100xxxxx");
  CPPUNIT_ASSERT(np.add_slice(1, space) == true);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 0);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 0);

  np.add_pipe_to_slices(&pipe1);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 0);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 1);
  CPPUNIT_ASSERT(pipe1.net_space_id == 1);

  // try to remove nonexisting pipe
  // tried with nonexisting netspace,
  // otherwise r_slice must be set
  np.remove_pipe_from_slices(&pipe2);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 0);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 1);

  // remove existing pipe
  np.remove_pipe_from_slices(&pipe1);
  CPPUNIT_ASSERT(np.slices.size() == 2);
  CPPUNIT_ASSERT(np.slices[0].pipes.size() == 0);
  CPPUNIT_ASSERT(np.slices[1].pipes.size() == 0);
  
  // cleanup
  free(pipe1.pipe_array);
  free(pipe2.pipe_array);
  free(mask);
}

// Unit tests checks on Pipeline pairs, structure is not completely initialized
template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_check_pipe_for_slice_leakage_no_exception() {
  auto np = NetPlumber<T1, T2>(1);
  auto pipe1 = Pipeline<T1, T2>();
  auto pipe2 = Pipeline<T1, T2>();

  T2 *mask = new T2(std::string("xxxxxxxx"));
  T1 *space = new T1(1);
  space->psunion2(mask);

  uint32_t nports[1] = { 0 };
  List_t lnports = make_sorted_list_from_array(1, nports);

  auto nid = np.add_source(space, lnports);
  auto node = np.id_to_node[nid];
  pipe1.node = node;
  pipe2.node = node;
  pipe1.net_space_id = 0;
  pipe2.net_space_id = 1;

  np.slice_leakage_callback = leakage_callback;
  leakage_called = false;
  
  CPPUNIT_ASSERT(np.matrix.size() == 0);
  np.check_pipe_for_slice_leakage(&pipe1, &pipe1);
  CPPUNIT_ASSERT(leakage_called == false);

  np.check_pipe_for_slice_leakage(&pipe1, &pipe2);
  CPPUNIT_ASSERT(leakage_called == true);
}

template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_check_pipe_for_slice_leakage_with_exception() {
  auto np = NetPlumber<T1, T2>(1);
  auto pipe1 = Pipeline<T1, T2>();
  auto pipe2 = Pipeline<T1, T2>();
  auto pipe3 = Pipeline<T1, T2>();
  
  T2 *mask = new T2(std::string("xxxxxxxx"));
  T1 *space = new T1(1);
  space->psunion2(mask);

  uint32_t nports[1] = { 0 };
  List_t lnports = make_sorted_list_from_array(1, nports);

  auto nid = np.add_source(space, lnports);
  auto node = np.id_to_node[nid];
  pipe1.node = node;
  pipe2.node = node;
  pipe3.node = node;
  pipe1.net_space_id = 0;
  pipe2.net_space_id = 1;
  pipe3.net_space_id = 2;

  np.slice_leakage_callback = leakage_callback;
  leakage_called = false;

  CPPUNIT_ASSERT(np.add_slice_allow(0, 1) == true);
  CPPUNIT_ASSERT(np.add_slice_allow(0, 2) == true);
  CPPUNIT_ASSERT(np.add_slice_allow(1, 0) == true);
  CPPUNIT_ASSERT(np.add_slice_allow(2, 0) == true);
  
  CPPUNIT_ASSERT(np.matrix.size() == 3);
  np.check_pipe_for_slice_leakage(&pipe1, &pipe1);
  CPPUNIT_ASSERT(leakage_called == false);

  np.check_pipe_for_slice_leakage(&pipe1, &pipe2);
  CPPUNIT_ASSERT(leakage_called == false);

  np.check_pipe_for_slice_leakage(&pipe2, &pipe1);
  CPPUNIT_ASSERT(leakage_called == false);

  np.check_pipe_for_slice_leakage(&pipe1, &pipe3);
  CPPUNIT_ASSERT(leakage_called == false);

  np.check_pipe_for_slice_leakage(&pipe3, &pipe1);
  CPPUNIT_ASSERT(leakage_called == false);
  
  np.check_pipe_for_slice_leakage(&pipe2, &pipe3);
  CPPUNIT_ASSERT(leakage_called == true);
  leakage_called = false;

  np.check_pipe_for_slice_leakage(&pipe3, &pipe2);
  CPPUNIT_ASSERT(leakage_called == true);
  leakage_called = false;
}

// represents demo_leak1 example
template<class T1, class T2>
void NetPlumberSlicingTest<T1, T2>::test_end_to_end() {
  auto np = NetPlumber<T1, T2>(1);
  np.slice_overlap_callback = overlap_callback;
  np.slice_leakage_callback = leakage_callback;
  overlap_called = false;
  leakage_called = false;

  // add slices
  CPPUNIT_ASSERT(np.slices.size() == 1);
  T1 *net_space = new T1("000xxxxx");
  CPPUNIT_ASSERT(np.add_slice(1, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 2);

  net_space = new T1("001xxxxx");
  CPPUNIT_ASSERT(np.add_slice(2, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 3);

  net_space = new T1("010xxxxx");
  CPPUNIT_ASSERT(np.add_slice(3, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 4);

  net_space = new T1("011xxxxx");
  CPPUNIT_ASSERT(np.add_slice(4, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 5);

  net_space = new T1("100xxxxx");
  CPPUNIT_ASSERT(np.add_slice(5, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 6);
  
  net_space = new T1("101xxxxx");
  CPPUNIT_ASSERT(np.add_slice(6, net_space) == true);
  CPPUNIT_ASSERT(overlap_called == false);
  CPPUNIT_ASSERT(np.slices.size() == 7);

  // add slice matrix
  CPPUNIT_ASSERT(np.matrix.empty());
  CPPUNIT_ASSERT(np.add_slice_matrix(",0,1,2,3,4,5,6\n"
				     "0,x,x,x,x,x,x,x\n"
				     "1,x,,,,,,\n"
				     "2,x,,,,,,\n"
				     "3,x,,,,,,\n"
				     "4,x,,,,,,\n"
				     "5,x,,,,,,\n"
				     "6,x,,,,,,\n")
		 == true);
  CPPUNIT_ASSERT(!np.matrix.empty());
  CPPUNIT_ASSERT(np.matrix.size() == 7);
  CPPUNIT_ASSERT(np.matrix[0].size() == 7);

  // add forwarding tables
  uint32_t t1ports[2] = { 101, 102 };
  List_t lt1ports = make_sorted_list_from_array(2, t1ports);
  np.add_table(1, lt1ports);

  uint32_t t2ports[2] = { 201, 202 };
  List_t lt2ports = make_sorted_list_from_array(2, t2ports);
  np.add_table(2, lt2ports);

  uint32_t t3ports[2] = { 301, 302 };
  List_t lt3ports = make_sorted_list_from_array(2, t3ports);
  np.add_table(3, lt3ports);

  uint32_t t4ports[2] = { 401, 402 };
  List_t lt4ports = make_sorted_list_from_array(2, t4ports);
  np.add_table(4, lt4ports);

  uint32_t t5ports[2] = { 501, 502 };
  List_t lt5ports = make_sorted_list_from_array(2, t5ports);
  np.add_table(5, lt5ports);

  uint32_t t6ports[4] = { 601, 602, 603, 604 };
  List_t lt6ports = make_sorted_list_from_array(4, t6ports);
  np.add_table(6, lt6ports);

  uint32_t t7ports[7] = { 1, 11, 12, 13, 14, 15, 16 };
  List_t lt7ports = make_sorted_list_from_array(7, t7ports);
  np.add_table(7, lt7ports);

  // add links
  np.add_link(0, 1);
  np.add_link(11, 101);
  np.add_link(12, 201);
  np.add_link(13, 301);
  np.add_link(14, 401);
  np.add_link(15, 501);
  np.add_link(16, 601);
  np.add_link(2, 603);
  np.add_link(604, 501);

  np.add_link(102, 103);
  np.add_link(202, 203);
  np.add_link(302, 303);
  np.add_link(402, 403);
  np.add_link(502, 503);
  np.add_link(602, 605);

  // add rules
  T2 *m1 = new T2(std::string("000xxxxx"));
  T2 *m2 = new T2(std::string("001xxxxx"));
  T2 *m3 = new T2(std::string("010xxxxx"));
  T2 *m4 = new T2(std::string("011xxxxx"));
  T2 *m5 = new T2(std::string("100xxxxx"));
  T2 *m6 = new T2(std::string("101xxxxx"));
  T2 *mask = new T2(std::string("xxxxxxxx"));
  T2 *rwd = nullptr;
  T2 *mska = new T2(std::string("11100000"));
  T2 *rwa = new T2(std::string("100xxxxx"));

  uint32_t r1in[1] = { 1 };
  uint32_t r1out[1] = { 11 };
  uint32_t r2in[1] = { 1 };
  uint32_t r2out[1] = { 12 };
  uint32_t r3in[1] = { 1 };
  uint32_t r3out[1] = { 13 };
  uint32_t r4in[1] = { 1 };
  uint32_t r4out[1] = { 14 };
  uint32_t r5in[1] = { 1 };
  uint32_t r5out[1] = { 15 };
  uint32_t r6in[1] = { 1 };
  uint32_t r6out[1] = { 16 };
  
  List_t tr1in = make_sorted_list_from_array(1, r1in);
  List_t tr1out = make_sorted_list_from_array(1, r1out);
  List_t tr2in = make_sorted_list_from_array(1, r2in);
  List_t tr2out = make_sorted_list_from_array(1, r2out);
  List_t tr3in = make_sorted_list_from_array(1, r3in);
  List_t tr3out = make_sorted_list_from_array(1, r3out);
  List_t tr4in = make_sorted_list_from_array(1, r4in);
  List_t tr4out = make_sorted_list_from_array(1, r4out);
  List_t tr5in = make_sorted_list_from_array(1, r5in);
  List_t tr5out = make_sorted_list_from_array(1, r5out);
  List_t tr6in = make_sorted_list_from_array(1, r6in);
  List_t tr6out = make_sorted_list_from_array(1, r6out);
  
  np.add_rule(7, 1, tr1in, tr1out, new T2(*m1), new T2(*mask), rwd);
  np.add_rule(7, 2, tr2in, tr2out, new T2(*m2), new T2(*mask), rwd);
  np.add_rule(7, 3, tr3in, tr3out, new T2(*m3), new T2(*mask), rwd);
  np.add_rule(7, 4, tr4in, tr4out, new T2(*m4), new T2(*mask), rwd);
  np.add_rule(7, 5, tr5in, tr5out, new T2(*m5), new T2(*mask), rwd);
  np.add_rule(7, 6, tr6in, tr6out, new T2(*m6), new T2(*mask), rwd);

  // add dummy rules
  uint32_t rd1in[1] = { 101 };
  uint32_t rd1out[1] = { 102 };
  uint32_t rd2in[1] = { 201 };
  uint32_t rd2out[1] = { 202 };
  uint32_t rd3in[1] = { 301 };
  uint32_t rd3out[1] = { 302 };
  uint32_t rd4in[1] = { 401 };
  uint32_t rd4out[1] = { 402 };
  uint32_t rd5in[1] = { 501 };
  uint32_t rd5out[1] = { 502 };
  uint32_t rd6in[1] = { 601 };
  uint32_t rd6out[1] = { 602 };
  uint32_t rd7in[1] = { 603 };
  uint32_t rd7out[1] = { 604 };

  List_t trd1in = make_sorted_list_from_array(1, rd1in);
  List_t trd1out = make_sorted_list_from_array(1, rd1out);
  List_t trd2in = make_sorted_list_from_array(1, rd2in);
  List_t trd2out = make_sorted_list_from_array(1, rd2out);
  List_t trd3in = make_sorted_list_from_array(1, rd3in);
  List_t trd3out = make_sorted_list_from_array(1, rd3out);
  List_t trd4in = make_sorted_list_from_array(1, rd4in);
  List_t trd4out = make_sorted_list_from_array(1, rd4out);
  List_t trd5in = make_sorted_list_from_array(1, rd5in);
  List_t trd5out = make_sorted_list_from_array(1, rd5out);
  List_t trd6in = make_sorted_list_from_array(1, rd6in);
  List_t trd6out = make_sorted_list_from_array(1, rd6out);
  List_t trd7in = make_sorted_list_from_array(1, rd7in);
  List_t trd7out = make_sorted_list_from_array(1, rd7out);

  np.add_rule(1, 1, trd1in, trd1out, new T2(*m1), new T2(*mask), rwd);
  np.add_rule(2, 1, trd2in, trd2out, new T2(*m2), new T2(*mask), rwd);
  np.add_rule(3, 1, trd3in, trd3out, new T2(*m3), new T2(*mask), rwd);
  np.add_rule(4, 1, trd4in, trd4out, new T2(*m4), new T2(*mask), rwd);
  np.add_rule(5, 1, trd5in, trd5out, new T2(*m5), new T2(*mask), rwd);
  np.add_rule(6, 1, trd6in, trd6out, new T2(*m6), new T2(*mask), rwd);
  np.add_rule(6, 2, trd7in, trd7out, new T2(*m6), new T2(*mska), new T2(*rwa));

  // add source probes
  uint32_t s1[1] = { 103 };
  uint32_t s2[1] = { 203 };
  uint32_t s3[1] = { 303 };
  uint32_t s4[1] = { 403 };
  uint32_t s5[1] = { 503 };
  uint32_t s6[1] = { 605 };
  List_t ss1 = make_sorted_list_from_array(1, s1);
  List_t ss2 = make_sorted_list_from_array(1, s2);
  List_t ss3 = make_sorted_list_from_array(1, s3);
  List_t ss4 = make_sorted_list_from_array(1, s4);
  List_t ss5 = make_sorted_list_from_array(1, s5);
  List_t ss6 = make_sorted_list_from_array(1, s6);
  PROBE_MODE mode = EXISTENTIAL;
  Condition<T1, T2> *f1 = new FalseCondition<T1, T2>();
  Condition<T1, T2> *t1 = new TrueCondition<T1, T2>();
  Condition<T1, T2> *f2 = new FalseCondition<T1, T2>();
  Condition<T1, T2> *t2 = new TrueCondition<T1, T2>();
  Condition<T1, T2> *f3 = new FalseCondition<T1, T2>();
  Condition<T1, T2> *t3 = new TrueCondition<T1, T2>();
  Condition<T1, T2> *f4 = new FalseCondition<T1, T2>();
  Condition<T1, T2> *t4 = new TrueCondition<T1, T2>();
  Condition<T1, T2> *f5 = new FalseCondition<T1, T2>();
  Condition<T1, T2> *t5 = new TrueCondition<T1, T2>();
  Condition<T1, T2> *f6 = new FalseCondition<T1, T2>();
  Condition<T1, T2> *t6 = new TrueCondition<T1, T2>();
  np.add_source_probe(ss1, mode, f1, t1, NULL, NULL);
  np.add_source_probe(ss2, mode, f2, t2, NULL, NULL);
  np.add_source_probe(ss3, mode, f3, t3, NULL, NULL);
  np.add_source_probe(ss4, mode, f4, t4, NULL, NULL);
  np.add_source_probe(ss5, mode, f5, t5, NULL, NULL);
  np.add_source_probe(ss6, mode, f6, t6, NULL, NULL);

  CPPUNIT_ASSERT(leakage_called == false);

  // add sources
  uint32_t sa0[1] = { 0 };
  uint32_t sa1[1] = { 2 };
  List_t lsa0 = make_sorted_list_from_array(1, sa0);
  List_t lsa1 = make_sorted_list_from_array(1, sa1);

  net_space = new T1(1);
  net_space->psunion2(mask);
  np.add_source(net_space, lsa0);
  CPPUNIT_ASSERT(leakage_called == false);

  // finally creates the leaking pipe from 604 to 501 via 603-604 rule
  net_space = new T1(1);
  net_space->psunion2(m6);
  np.add_source(net_space, lsa1);
  CPPUNIT_ASSERT(leakage_called == true);

  // cleanup
  free(m1);
  free(m2);
  free(m3);
  free(m4);
  free(m5);
  free(m6);
  free(mask);
  free(mska);
  free(rwa);
  
  overlap_called = false;
  leakage_called = false;
}

template class NetPlumberSlicingTest<HeaderspacePacketSet, ArrayPacketSet>;
#endif /* PIPE_SLICING */
