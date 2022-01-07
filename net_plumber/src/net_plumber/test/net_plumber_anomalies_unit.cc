/*
   Copyright 2021 Claas Lorenz.

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

#if defined(CHECK_SIMPLE_SHADOW) || defined(CHECK_REACH_SHADOW)

#include "net_plumber_anomalies_unit.h"
#include "../rule_node.h"
#include "../net_plumber_utils.h"
#include "../array_packet_set.h"
#include "../hs_packet_set.h"
#ifdef USE_BDD
#include "../bdd_packet_set.h"
#endif

using namespace net_plumber;
using namespace log4cxx;

// override standard callbacks for testing
bool shadow_called = false;
template<class T1, class T2>
void rule_shadow_callback(NetPlumber<T1, T2>* /*N*/, Flow<T1, T2>* /*f*/, void* /*data*/) {
  shadow_called = true;
}

void reset_shadow(void) {
  shadow_called = false;
}

#ifdef CHECK_REACH_SHADOW
bool unreach_called = false;
template<class T1, class T2>
void rule_unreach_callback(NetPlumber<T1, T2>* /*N*/, Flow<T1, T2>* /*f*/, void* /*data*/) {
  unreach_called = true;
}

void reset_unreach(void) {
  unreach_called = false;
}
#endif

template<class T1, class T2>
void NetPlumberAnomaliesTest<T1, T2>::setUp() {
#ifdef USE_BDD
  if (bdd_isrunning()) bdd_done();
  bdd_init(100000, 1000);
  bdd_setvarnum(8);
#endif
  this->n = new NetPlumber<T1, T2>(1);
  this->n->rule_shadow_callback = rule_shadow_callback;
#ifdef CHECK_REACH_SHADOW
  this->n->rule_unreach_callback = rule_unreach_callback;
#endif
}

template<class T1, class T2>
void NetPlumberAnomaliesTest<T1, T2>::tearDown() {
#ifdef USE_BDD
  if (bdd_isrunning()) bdd_done();
#endif
  delete this->n;
  reset_shadow();
#ifdef CHECK_REACH_SHADOW
  reset_unreach();
#endif
}

template<class T1, class T2>
void NetPlumberAnomaliesTest<T1, T2>::test_rule_shadowing() {
  printf("\n");
  List_t r1in = make_sorted_list(1, 1);
  List_t r1out = make_sorted_list(1, 2);
  List_t r2in = make_sorted_list(1, 1);
  List_t r2out = make_sorted_list(1, 2);
  List_t r3in = make_sorted_list(1, 1);
  List_t r3out = make_sorted_list(1, 2);
#ifdef CHECK_REACH_SHADOW
  List_t r4in = make_sorted_list(1, 1);
  List_t r4out = make_sorted_list(1, 2);
#endif
  List_t table_ports = make_sorted_list(2, 1, 2);

  T2 *m1 = array_from_str("xxxxxxx1");
  T2 *m2 = array_from_str("xxxxxxx0");
#ifdef CHECK_REACH_SHADOW
  T2 *m3 = array_from_str("xxxxxxxx");
#endif

  this->n->add_table(1, table_ports);

  this->n->add_rule(1, 1, r1in, r1out, m1, nullptr, nullptr);

  // test: shadowed rule
  this->n->add_rule(1, 3, r3in, r3out, array_copy(m1, 1), nullptr, nullptr);
  CPPUNIT_ASSERT(shadow_called == true);

  // test: unshadowed rule
  reset_shadow();
  this->n->add_rule(1, 2, r2in, r2out, m2, nullptr, nullptr);

  CPPUNIT_ASSERT(shadow_called == false);

#ifdef CHECK_REACH_SHADOW
  // test: shadowed rule
  reset_shadow();
  this->n->add_rule(1, 4, r4in, r4out, m3, nullptr, nullptr);

  CPPUNIT_ASSERT(shadow_called == true);
#endif
}

#ifdef CHECK_REACH_SHADOW
template<class T1, class T2>
void NetPlumberAnomaliesTest<T1, T2>::test_rule_reachability() {
  printf("\n");

  List_t r1in = make_sorted_list(1, 1);
  List_t r1out = make_sorted_list(1, 2);
  List_t r2in = make_sorted_list(1, 1);
  List_t r2out = make_sorted_list(1, 2);
  List_t r3in = make_sorted_list(1, 1);
  List_t r3out = make_sorted_list(1, 2);
  List_t table_ports = make_sorted_list(2, 1, 2);

  T2 *m1 = array_from_str("xxxxxxx1");
  T2 *m2 = array_from_str("xxxxxxx0");
  T2 *m3 = array_from_str("xxxxxxxx");

  this->n->add_table(1, table_ports);

  this->n->add_rule(1, 1, r1in, r1out, m1, nullptr, nullptr);

  // test: reachable rule
  this->n->add_rule(1, 2, r2in, r2out, m2, nullptr, nullptr);

  CPPUNIT_ASSERT(unreach_called == false);

  // test: unreachable rule
  this->n->add_rule(1, 3, r3in, r3out, m3, nullptr, nullptr);

  CPPUNIT_ASSERT(unreach_called == true);
}
#endif

template<class T1, class T2>
void NetPlumberAnomaliesTest<T1, T2>::test_rule_shadowing_regression() {
  printf("\n");

  List_t r1in = make_sorted_list(1, 1);
  List_t r1out = make_sorted_list(1, 2);
  List_t r2in = make_sorted_list(1, 1);
  List_t r2out = make_sorted_list(1, 2);
  List_t table_ports = make_sorted_list(2, 1, 2);

  this->n->expand(27);

  T2 *m1 = array_from_str("00010001,xxxxxxxx,10000011,10011111,00010100,xxxxxxxx,00000000,00000101,00000000,00000100,00000000,01100000,10000011,10011111,00001110,00101111,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,11101010,1xxxxxxx,xxxxxxxx,xxxxxxxx,00000001");
  T2 *m2 = array_from_str("00000110,xxxxxxxx,10000011,10011111,00010100,xxxxxxxx,00000000,00000101,00000000,00000100,00000000,01101101,10000011,10011111,00010100,00111110,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,00000011,10001001,xxxxxxxx,xxxxxxxx,00000001");

  this->n->add_table(1, table_ports);

  this->n->add_rule(1, 1, r1in, r1out, m1, nullptr, nullptr);

  // test: unshadowed rule
  this->n->add_rule(1, 2, r2in, r2out, m2, nullptr, nullptr);

  CPPUNIT_ASSERT(shadow_called == false);
}

#ifdef GENERIC_PS
template class NetPlumberAnomaliesTest<HeaderspacePacketSet, ArrayPacketSet>;
#ifdef USE_BDD
template class NetPlumberAnomaliesTest<BDDPacketSet, BDDPacketSet>;
#endif
#else
template class NetPlumberAnomaliesTest<hs, array_t>;
#endif
#endif // CHECK_REACH_SHADOW
