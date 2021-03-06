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

#include "net_plumber_basic_unit.h"
#include "../rule_node.h"
#include "../net_plumber.h"
#include "../net_plumber_utils.h"
#include "../array_packet_set.h"
#include "../hs_packet_set.h"
#ifdef USE_BDD
#include "../bdd_packet_set.h"
#endif

using namespace net_plumber;

template<class T1, class T2>
void NetPlumberBasicTest<T1, T2>::setUp() {
#ifdef USE_BDD
  if (bdd_isrunning()) bdd_done();
  bdd_init(100000, 1000);
  bdd_setvarnum(8);
#endif
}

template<class T1, class T2>
void NetPlumberBasicTest<T1, T2>::tearDown() {
#ifdef USE_BDD
  if (bdd_isrunning()) bdd_done();
#endif
}

template<class T1, class T2>
void NetPlumberBasicTest<T1, T2>::test_rule_node_create() {
  printf("\n");
  List_t in_ports = make_sorted_list(2,2,3);
  List_t out_ports = make_sorted_list(2,1,4);
#ifdef GENERIC_PS
  T2 *match = new T2("xxxxxxxx,xxxxxxxx");
  T2 *mask = new T2("00000000,01111111");
  T2 *rewrite = new T2("00000000,00000011");
  T2 *inv_match = new T2("xxxxxxxx,x0000011");
#ifdef USE_INV
  T2 *inv_rw = new T2("xxxxxxxx,x0000000");
#endif
#else
  T2 *match = array_from_str("xxxxxxxx,xxxxxxxx");
  T2 *mask = array_from_str("00000000,01111111");
  T2 *rewrite = array_from_str("00000000,00000011");
  T2 *inv_match = array_from_str("xxxxxxxx,x0000011");
#ifdef USE_INV
  T2 *inv_rw = array_from_str("xxxxxxxx,x0000000");
#endif
#endif
  RuleNode<T1, T2> *r = new RuleNode<T1, T2>(NULL,2,1,1,0,in_ports,out_ports,match,mask,rewrite);
  CPPUNIT_ASSERT(r->output_ports.size == 2);
#ifdef GENERIC_PS
  CPPUNIT_ASSERT(r->inv_match->is_equal(inv_match));
#ifdef USE_INV
  CPPUNIT_ASSERT(r->inv_rw->is_equal(inv_rw));
  delete inv_rw;
#endif
  delete inv_match;
#else
  CPPUNIT_ASSERT(array_is_eq(r->inv_match, inv_match, 2));
#ifdef USE_INV
  CPPUNIT_ASSERT(array_is_eq(r->inv_rw, inv_rw, 2));
  array_free(inv_rw);
#endif
  array_free(inv_match);
#endif
  delete r;
}

template<class T1, class T2>
void NetPlumberBasicTest<T1, T2>::test_create_topology() {
  printf("\n");
  auto *n = new NetPlumber<T1, T2>(1);
  n->add_link(1,2);
  n->add_link(1,3);
  n->add_link(2,1);
  //n->print_topology();
  CPPUNIT_ASSERT(n->get_dst_ports(1)->size()==2);
  CPPUNIT_ASSERT(n->get_dst_ports(2)->size()==1);
  CPPUNIT_ASSERT(n->get_src_ports(3)->size()==1);
  delete n;
}

template<class T1, class T2>
void NetPlumberBasicTest<T1, T2>::test_create_rule_id() {
  printf("\n");
  auto *n = new NetPlumber<T1, T2>(1);
  n->add_table(1,make_sorted_list(3,1,2,3));
  // two conseq. rules
  List_t in_ports = make_sorted_list(1,1);
  List_t out_ports = make_sorted_list(1,2);
#ifdef GENERIC_PS
  T2 *match = new T2("xxxxxxxx");
#else
  T2 *match = array_from_str("xxxxxxxx");
#endif
  uint64_t id1 = n->add_rule(1,10,in_ports,out_ports,match,NULL,NULL);
  in_ports = make_sorted_list(1,2);
  out_ports = make_sorted_list(1,3);
#ifdef GENERIC_PS
  match = new T2("xxxxxxxx");
#else
  match = array_from_str("xxxxxxxx");
#endif
  uint64_t id2 = n->add_rule(1,11,in_ports,out_ports,match,NULL,NULL);
  CPPUNIT_ASSERT(id2-id1==1);
  // add to an invalid table
  in_ports = make_sorted_list(1,1);
  out_ports = make_sorted_list(1,2);
#ifdef GENERIC_PS
  match = new T2("xxxxxxxx");
#else
  match = array_from_str("xxxxxxxx");
#endif
  uint64_t id3 = n->add_rule(2,10,in_ports,out_ports,match,NULL,NULL);
  CPPUNIT_ASSERT(id3==0);
  // add to a removed table
  n->remove_table(1);
  in_ports = make_sorted_list(1,1);
  out_ports = make_sorted_list(1,2);
#ifdef GENERIC_PS
  match = new T2("xxxxxxxx");
#else
  match = array_from_str("xxxxxxxx");
#endif
  uint64_t id4 = n->add_rule(1,10,in_ports,out_ports,match,NULL,NULL);
  CPPUNIT_ASSERT(id4==0);
  delete n;
}

#ifdef GENERIC_PS
template class NetPlumberBasicTest<HeaderspacePacketSet, ArrayPacketSet>;
#ifdef USE_BDD
template class NetPlumberBasicTest<BDDPacketSet, BDDPacketSet>;
#endif
#else
template class NetPlumberBasicTest<hs, array_t>;
#endif
