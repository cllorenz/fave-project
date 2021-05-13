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


#include "conditions_unit.h"
#include "../net_plumber_utils.h"
#include "../source_node.h"
#include "../rule_node.h"
#include <stdarg.h>
#include "../array_packet_set.h"
#include "../hs_packet_set.h"
#ifdef USE_BDD
#include "../bdd_packet_set.h"
#endif

using namespace std;
using namespace net_plumber;


template<class T1, class T2>
void ConditionsTest<T1, T2>::setUp() {
#ifdef USE_BDD
    if (bdd_isrunning()) bdd_done();
    bdd_init(100000, 1000);
    bdd_setvarnum(8);
#endif
}

template<class T1, class T2>
void ConditionsTest<T1, T2>::tearDown() {
#ifdef USE_BDD
  if (bdd_isrunning()) bdd_done();
#endif
}


template<class T1, class T2>
void ConditionsTest<T1, T2>::test_port() {
  printf("\n");
  list<Flow<T1, T2> *>* flows = create_flow(make_unsorted_list(3,1,2,3),
                                  make_unsorted_list(3,100,200,300));
  PathCondition<T1, T2> c;
  c.add_pathlet(new PortSpecifier<T1, T2>(2));
  CPPUNIT_ASSERT(c.check(*(flows->begin())));
  c.add_pathlet(new PortSpecifier<T1, T2>(1));
  c.add_pathlet(new EndPathSpecifier<T1, T2>());
  CPPUNIT_ASSERT(c.check(*(flows->begin())));
  free_flow(flows);
}

template<class T1, class T2>
void ConditionsTest<T1, T2>::test_table() {
  printf("\n");
  list<Flow<T1, T2> *>* flows = create_flow(make_unsorted_list(3,1,2,3),
                                  make_unsorted_list(3,100,200,300));
  PathCondition<T1, T2> c;
  c.add_pathlet(new TableSpecifier<T1, T2>(300));
  CPPUNIT_ASSERT(c.check(*(flows->begin())));
  c.add_pathlet(new TableSpecifier<T1, T2>(200));
  c.add_pathlet(new EndPathSpecifier<T1, T2>());
  CPPUNIT_ASSERT(!c.check(*(flows->begin())));
  free_flow(flows);
}

template<class T1, class T2>
void ConditionsTest<T1, T2>::test_port_sequence() {
  printf("\n");
  list<Flow<T1, T2> *>* flows = create_flow(make_unsorted_list(5,1,2,3,4,5),
                                  make_unsorted_list(5,100,200,300,400,500));
  PathCondition<T1, T2> c;
  c.add_pathlet(new PortSpecifier<T1, T2>(4));
  c.add_pathlet(new NextPortsSpecifier<T1, T2>(make_sorted_list(1,3)));
  CPPUNIT_ASSERT(c.check(*(flows->begin())));
  c.add_pathlet(new NextPortsSpecifier<T1, T2>(make_sorted_list(1,1)));
  CPPUNIT_ASSERT(!c.check(*(flows->begin())));
  free_flow(flows);
}

template<class T1, class T2>
void ConditionsTest<T1, T2>::test_sequence() {
  printf("\n");
  list<Flow<T1, T2> *>* flows = create_flow(make_unsorted_list(5,1,2,3,4,5),
                                  make_unsorted_list(5,100,200,300,400,500));
  PathCondition<T1, T2> c;
  c.add_pathlet(new PortSpecifier<T1, T2>(4));
  c.add_pathlet(new NextTablesSpecifier<T1, T2>(make_sorted_list(1,300)));
  CPPUNIT_ASSERT(c.check(*(flows->begin())));
  c.add_pathlet(new SkipNextSpecifier<T1, T2>());
  c.add_pathlet(new NextTablesSpecifier<T1, T2>(make_sorted_list(1,100)));
  CPPUNIT_ASSERT(c.check(*(flows->begin())));
  free_flow(flows);
}

template<class T1, class T2>
void ConditionsTest<T1, T2>::test_path_length() {
  printf("\n");
  list<Flow<T1, T2> *>* flows1 = create_flow(make_unsorted_list(4,1,2,3,4),
                                  make_unsorted_list(4,100,200,300,400));
  list<Flow<T1, T2> *>* flows2 = create_flow(make_unsorted_list(2,1,2),
                                  make_unsorted_list(2,100,200));
  // path of length 1
  PathCondition<T1, T2> *c1 = new PathCondition<T1, T2>();
  c1->add_pathlet(new SkipNextSpecifier<T1, T2>());
  c1->add_pathlet(new EndPathSpecifier<T1, T2>());
  // path of length 2
  PathCondition<T1, T2> *c2 = new PathCondition<T1, T2>();
  c2->add_pathlet(new SkipNextSpecifier<T1, T2>());
  c2->add_pathlet(new SkipNextSpecifier<T1, T2>());
  c2->add_pathlet(new EndPathSpecifier<T1, T2>());
  // path of length 3
  PathCondition<T1, T2> *c3 = new PathCondition<T1, T2>();
  c3->add_pathlet(new SkipNextSpecifier<T1, T2>());
  c3->add_pathlet(new SkipNextSpecifier<T1, T2>());
  c3->add_pathlet(new SkipNextSpecifier<T1, T2>());
  c3->add_pathlet(new EndPathSpecifier<T1, T2>());
  // OR the three cases
  OrCondition<T1, T2> *oc1 = new OrCondition<T1, T2>(c1,c2);
  OrCondition<T1, T2> c(oc1,c3);
  // flow 1 has length of 4 and doesn't pass
  CPPUNIT_ASSERT(!c.check(*(flows1->begin())));
  // flow 2 has length of 2 and does pass
  CPPUNIT_ASSERT(c.check(*(flows2->begin())));
  free_flow(flows1);
  free_flow(flows2);
}

template<class T1, class T2>
void ConditionsTest<T1, T2>::test_lasts() {
  printf("\n");
  list<Flow<T1, T2> *>* flows1 = create_flow(make_unsorted_list(4,10,2,3,4),
                                  make_unsorted_list(4,100,200,300,400));
  list<Flow<T1, T2> *>* flows2 = create_flow(make_unsorted_list(4,11,2,3,4),
                                  make_unsorted_list(4,101,200,300,400));
  PathCondition<T1, T2> c1;
  c1.add_pathlet(new LastPortsSpecifier<T1, T2>(make_sorted_list(2,10,11)));
  PathCondition<T1, T2> c2;
  c2.add_pathlet(new LastTablesSpecifier<T1, T2>(make_sorted_list(2,100,101)));
  CPPUNIT_ASSERT(c1.check(*(flows1->begin())));
  CPPUNIT_ASSERT(c1.check(*(flows2->begin())));
  CPPUNIT_ASSERT(c2.check(*(flows1->begin())));
  CPPUNIT_ASSERT(c2.check(*(flows2->begin())));
  free_flow(flows1);
  free_flow(flows2);
}

template<class T1, class T2>
void ConditionsTest<T1, T2>::test_header() {
  printf("\n");
  list<Flow<T1, T2> *>* flows = create_flow(make_unsorted_list(5,1,2,3,4,5),
                                  make_unsorted_list(5,100,200,300,400,500));
  Flow<T1, T2> *f = *(flows->begin());

#ifdef GENERIC_PS
  f->processed_hs = new T1(1);
  T2 tmp1 = T2("10xxxxxx");
  f->processed_hs->psunion2(&tmp1);
  T2 tmp2 = T2("1011xxxx");
  f->processed_hs->diff2(&tmp2);

  T1 *hc1_hs = new T1(1);
  T2 tmp3 = T2("100xxxxx");
  hc1_hs->psunion2(&tmp3);

  T1 *hc2_hs = new T1(1);
  T2 tmp4 = T2("10111xxx");
  hc2_hs->psunion2(&tmp4);
#else
  f->processed_hs = hs_create(1);
  T2 *tmp1 = array_from_str("10xxxxxx");
  hs_add(f->processed_hs, tmp1);
  T2 *tmp2 = array_from_str("1011xxxx");
  hs_diff(f->processed_hs, tmp2);

  T1 *hc1_hs = hs_create(1);
  T2 *tmp3 = array_from_str("100xxxxx");
  hs_add(hc1_hs, tmp3);

  T1 *hc2_hs = hs_create(1);
  T2 *tmp4 = array_from_str("10111xxx");
  hs_add(hc2_hs, tmp4);
#endif

  HeaderCondition<T1, T2> *hc1 = new HeaderCondition<T1, T2>(hc1_hs);
  HeaderCondition<T1, T2> *hc2 = new HeaderCondition<T1, T2>(hc2_hs);

  CPPUNIT_ASSERT(hc1->check(f));
  CPPUNIT_ASSERT(!hc2->check(f));

  delete hc1;
  delete hc2;
#ifdef GENERIC_PS
  delete f->processed_hs;
#else
  hs_free(f->processed_hs);
  array_free(tmp2);
#endif
  free_flow(flows);
}

template<class T1, class T2>
list<Flow<T1, T2> *>* ConditionsTest<T1, T2>::create_flow(List_t ports, List_t tables) {
  assert(ports.size == tables.size);

  list<Flow<T1, T2> *> *result = new list<Flow<T1, T2> *>();
  Flow<T1, T2> *f, *prev;
  auto *s = new SourceNode<T1, T2>(
    NULL, 1, 0,
#ifdef GENERIC_PS
    new T1(1),
#else
    hs_create(1),
#endif
    make_sorted_list(1,0)
  );
  prev = (Flow<T1, T2> *)malloc(sizeof *prev);
  prev->node = s;
  prev->in_port = 0;
  prev->p_flow = s->get_EOSFI();
  result->push_front(prev);
  for (uint32_t i = 0; i< ports.size; i++) {
    auto *r = new RuleNode<T1, T2>(NULL, 1, 0, tables.list[i], 0,
                           make_sorted_list(1,ports.list[i]),
                           make_sorted_list(1,ports.list[i]),
#ifdef GENERIC_PS
                           new T2(1),
#else
                           array_create(1, BIT_X),
#endif
                           NULL,
                           NULL);

    r->is_input_layer = true;
    r->is_output_layer = true;
    f = (Flow<T1, T2> *)malloc(sizeof *f);
    f->in_port = ports.list[i];
    f->node = r;
    f->p_flow = result->begin();
    result->push_front(f);
  }
  free(ports.list);
  free(tables.list);
  return result;
}

template<class T1, class T2>
void ConditionsTest<T1, T2>::free_flow(list<Flow<T1, T2> *>* flows) {
  typename list<Flow<T1, T2> *>::iterator it;
  for (it = flows->begin(); it != flows->end(); it++) {
    delete (*it)->node;
    free(*it);
  }
  delete flows;
}

#ifdef GENERIC_PS
template class ConditionsTest<HeaderspacePacketSet, ArrayPacketSet>;
#ifdef USE_BDD
template class ConditionsTest<BDDPacketSet, BDDPacketSet>;
#endif
#else
template class ConditionsTest<hs, array_t>;
#endif
