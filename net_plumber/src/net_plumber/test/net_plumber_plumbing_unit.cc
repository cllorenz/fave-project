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

#include "net_plumber_plumbing_unit.h"
#include "../net_plumber_utils.h"
#include <sstream>
#include "../array_packet_set.h"
#include "../hs_packet_set.h"
#ifdef USE_BDD
#include "../bdd_packet_set.h"
#endif

using namespace net_plumber;
using namespace std;
using namespace log4cxx;

template<class T1, class T2>
LoggerPtr NetPlumberPlumbingTest<T1, T2>::logger(
    Logger::getLogger("NetPlumber-PlumbingUnitTest"));

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::setUp() {
#ifdef USE_BDD
  if (bdd_isrunning()) bdd_done();
  bdd_init(100000, 1000);
  bdd_setvarnum(8);
#endif
  N = new NetPlumber<T1, T2>(1);
  N->add_link(2,4);
  N->add_link(4,2);
  N->add_link(3,6);
  N->add_link(6,3);
  N->add_link(5,8);
  N->add_link(8,5);
  N->add_link(7,9);
  N->add_link(9,7);
  N->add_table(1, make_sorted_list(4,1,2,3,15));
  N->add_table(2, make_sorted_list(3,4,5,11));
  N->add_table(3, make_sorted_list(4,6,7,12,14));
  N->add_table(4, make_sorted_list(3,8,9,13));
  node_ids.push_back(N->add_rule(1,10,
              make_sorted_list(1,1),
              make_sorted_list(1,2),
#ifdef GENERIC_PS
              new T2 ("1010xxxx"),
#else
              array_from_str("1010xxxx"),
#endif
              NULL,
              NULL));
  node_ids.push_back(N->add_rule(1,20,
              make_sorted_list(1,1),
              make_sorted_list(1,2),
#ifdef GENERIC_PS
              new T2 ("10001xxx"),
#else
              array_from_str("10001xxx"),
#endif
              NULL,
              NULL));
  node_ids.push_back(N->add_rule(1,30,
              make_sorted_list(2,1,2),
              make_sorted_list(1,3),
#ifdef GENERIC_PS
              new T2 ("10xxxxxx"),
#else
              array_from_str("10xxxxxx"),
#endif
              NULL,
              NULL));
  node_ids.push_back(N->add_rule(2,10,
              make_sorted_list(1,4),
              make_sorted_list(2,5,11),
#ifdef GENERIC_PS
              new T2 ("1011xxxx"),
              new T2 ("00011000"),
              new T2 ("00001000")
#else
              array_from_str("1011xxxx"),
              array_from_str("00011000"),
              array_from_str("00001000")
#endif
  ));
  node_ids.push_back(N->add_rule(2,20,
              make_sorted_list(1,4),
              make_sorted_list(1,5),
#ifdef GENERIC_PS
              new T2 ("10xxxxxx"),
              new T2 ("01100000"),
              new T2 ("01100000")
#else
              array_from_str("10xxxxxx"),
              array_from_str("01100000"),
              array_from_str("01100000")
#endif
  ));
  node_ids.push_back(N->add_rule(3,10,
              make_sorted_list(3,6,7,12),
              make_sorted_list(1,7),
#ifdef GENERIC_PS
              new T2 ("101xxxxx"),
              new T2 ("00000111"),
              new T2 ("00000111")
#else
              array_from_str("101xxxxx"),
              array_from_str("00000111"),
              array_from_str("00000111")
#endif
  ));
  node_ids.push_back(N->add_rule(4,10,
              make_sorted_list(1,8),
              make_sorted_list(1,13),
#ifdef GENERIC_PS
              new T2 ("xxx010xx"),
#else
              array_from_str("xxx010xx"),
#endif
              NULL,
              NULL));
  memset(&A,0,sizeof A);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::tearDown() {
  delete N;
  node_ids.clear();
#ifdef USE_BDD
  if (bdd_isrunning()) bdd_done();
#endif
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_setup() {
  printf("\n");
  int stats[7][4]={
      {1,0,1,0},
      {1,0,1,0},
      {1,0,0,2},
      {1,0,1,0},
      {1,2,0,1},
      {0,1,0,0},
      {0,2,0,0}
  };
  //N->print_plumbing_network();
  this->verify_pipe_stats("test_setup", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_add_rule() {
  printf("\n");
  node_ids.push_back(N->add_rule(1,0,
              make_sorted_list(1,1),
              make_sorted_list(2,2,3),
#ifdef GENERIC_PS
              new T2 ("xx11xxxx"),
#else
              array_from_str("xx11xxxx"),
#endif
              NULL,
              NULL));
  int stats[8][4]={
      {1,0,1,0},
      {1,0,1,0},
      {1,0,0,3},
      {1,1,1,0},
      {1,3,0,1},
      {0,2,0,0},
      {0,2,0,0},
      {3,0,1,0} //new rule
  };
  //N->print_plumbing_network();
  this->verify_pipe_stats("test_pipeline_add_rule", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_remove_rule() {
  printf("\n");
  N->remove_rule(node_ids[4]);
  int stats[7][4]={
      {0,0,1,0},
      {0,0,1,0},
      {1,0,0,2},
      {1,0,0,0},
      {0,0,0,0},
      {0,1,0,0},
      {0,1,0,0}
  };
  //N->print_plumbing_network();
  this->verify_pipe_stats("test_pipeline_remove_rule", stats);
}

#ifdef USE_GROUPS
template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_add_group_rule() {
  printf("\n");
  node_ids.push_back(N->add_rule_to_group(1,1,
              make_sorted_list(1,1),
              make_sorted_list(1,2),
#ifdef GENERIC_PS
              new T2 ("xxxx11xx"),
              new T2 ("00110000"),
              new T2 ("00000000"),
#else
              array_from_str("xxxx11xx"),
              array_from_str("00110000"),
              array_from_str("00000000"),
#endif
              0
  ));
  node_ids.push_back(N->add_rule_to_group(1,0,
              make_sorted_list(1,1),
              make_sorted_list(1,3),
              new T2 ("xxxx11xx"),
              NULL,
              NULL,node_ids[node_ids.size()-1]));
  int stats[9][4]={
      {1,0,2,0},
      {1,0,1,1},
      {1,0,0,3},
      {1,0,1,0},
      {1,3,0,1},
      {0,2,0,0},
      {0,2,0,0},
      {1,0,2,1}, //new rule 1
      {1,0,2,1}  //new rule 2
  };
  //N->print_plumbing_network();
  this->verify_pipe_stats("test_pipeline_add_group_rule", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_add_group_rule_mix() {
  printf("\n");
  this->test_pipeline_add_group_rule();
  node_ids.push_back(N->add_rule(1,2,
              make_sorted_list(1,1),
              make_sorted_list(2,2,3),
#ifdef GENERIC_PS
              new T2 ("xx11xxxx"),
#else
              array_from_str("xx11xxxx"),
#endif
              NULL,
              NULL));
  int stats[10][4]={
      {1,0,2,0},
      {1,0,1,1},
      {1,0,0,4},
      {1,1,1,0},
      {1,4,0,1},
      {0,3,0,0},
      {0,2,0,0},
      {1,0,3,1}, //new rule 1
      {1,0,3,1}, //new rule 2
      {3,0,1,1}  //new rule 3
  };
  //N->print_plumbing_network();
  this->verify_pipe_stats("test_pipeline_add_group_rule_mix", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_remove_group_rule() {
  printf("\n");
  this->test_pipeline_add_group_rule();
  N->remove_rule(node_ids[node_ids.size()-1]);
  node_ids.pop_back();
  node_ids.pop_back();
  this->test_setup();
}
#endif

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_add_link() {
  printf("\n");
  N->add_link(11,12);
  int stats[7][4]={
      {1,0,1,0},
      {1,0,1,0},
      {1,0,0,2},
      {2,0,1,0},
      {1,2,0,1},
      {0,2,0,0},
      {0,2,0,0}
  };
  //N->print_plumbing_network();
  this->verify_pipe_stats("test_pipeline_add_link", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_remove_link() {
  this->test_pipeline_add_link();
  N->remove_link(11,12);
  //N->print_plumbing_network();
  this->test_setup();
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_add_source() {
  printf("\n");
  N->add_link(100,1);
#ifdef GENERIC_PS
  T1 *h = new T1("1xxxxxxx");
#else
  T1 *h = hs_from_str("1xxxxxxx");
#endif
  node_ids.push_back(
      N->add_source(h, make_sorted_list(1,100), 1)
  );
  int stats[8][4]={
      {1,1,1,0},
      {1,1,1,0},
      {1,1,0,2},
      {1,0,1,0},
      {1,2,0,1},
      {0,1,0,0},
      {0,2,0,0},
      {3,0,0,0}
  };
  //N->print_plumbing_network();
  this->verify_pipe_stats("test_pipeline_add_source", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_remove_source() {
  printf("\n");
  N->add_link(100,1);
#ifdef GENERIC_PS
  T1 *h = new T1(1);
  T2 a = T2 ("1xxxxxxx");
  h->psunion2(&a);
#else
  T1 *h = hs_from_str("1xxxxxxx");
#endif
  uint64_t id = N->add_source(h, make_sorted_list(1,100), 1);
  //N->print_plumbing_network();
  N->remove_source(id);
  this->test_setup();
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_add_probe() {
  printf("\n");
  N->add_link(13,200);
  node_ids.push_back(N->add_source_probe(
      make_sorted_list(1,200), EXISTENTIAL, nullptr, new TrueCondition<T1, T2>(),
      new TrueCondition<T1, T2>(),NULL, NULL, 1));
  int stats[8][4]={
      {1,0,1,0},
      {1,0,1,0},
      {1,0,0,2},
      {1,0,1,0},
      {1,2,0,1},
      {0,1,0,0},
      {1,2,0,0},
      {0,1,0,0},
  };
  //N->print_plumbing_network();
  this->verify_pipe_stats("test_pipeline_add_probe", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_remove_probe() {
  this->test_pipeline_add_probe();
  N->remove_source_probe(node_ids[7]);
  node_ids.pop_back();
  //N->print_plumbing_network();
  this->test_setup();
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_pipeline_shared_ports() {
  printf("\n");
  N->add_table(5,make_sorted_list(3,14,15,16));
  N->add_link(11,14);
  N->add_link(15,8);
  node_ids.push_back(N->add_rule(5,10,
              make_sorted_list(0),
              make_sorted_list(1,15),
#ifdef GENERIC_PS
              new T2 ("10xxxxxx"),
              new T2 ("01100000"),
              new T2 ("01100000")
#else
              array_from_str("10xxxxxx"),
              array_from_str("01100000"),
              array_from_str("01100000")
#endif
  ));
  node_ids.push_back(N->add_rule(5,20,
              make_sorted_list(0),
              make_sorted_list(1,16),
#ifdef GENERIC_PS
              new T2 ("1000xxxx"),
#else
              array_from_str("1000xxxx"),
#endif
              NULL,
              NULL));
  node_ids.push_back(N->add_rule(5,30,
              make_sorted_list(0),
              make_sorted_list(1,15),
#ifdef GENERIC_PS
              new T2 ("1010xxxx"),
              new T2 ("01100000"),
              new T2 ("01000000")
#else
              array_from_str("1010xxxx"),
              array_from_str("01100000"),
              array_from_str("01000000")
#endif
  ));
  int stats[10][4]={
      {1,0,1,0},
      {1,0,1,0},
      {1,0,0,2},
      {3,0,1,0},
      {1,2,0,1},
      {0,1,0,0},
      {0,4,0,0},
      {1,1,2,0},
      {0,0,0,1},
      {1,1,0,1}
  };
  //N->print_plumbing_network();
  this->verify_pipe_stats("test_pipeline_shared_ports", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_add_source() {
  printf("\n");
  N->add_link(100,1);
#ifdef GENERIC_PS
  T1 *h = new T1(1);
  T2 a = T2 ("1xxxxxxx");
  h->psunion2(&a);
#else
  T1 *h = hs_from_str("1xxxxxxx");
#endif
  N->add_source(h, make_sorted_list(1,100), 1);
  int stats[7][2] = {
      {1,0},
      {1,0},
#ifdef USE_BDD
      {3,0},
#else
      {1,2},
#endif
      {0,0},
      {2,0},
#ifdef NEW_HS
      {1,1},
#else
      {1,0},
#endif
      {2,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_add_source", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_remove_source() {
  printf("\n");
  N->add_link(100,1);
#ifdef GENERIC_PS
  T1 *h = new T1(1);
  T2 a = T2 ("1xxxxxxx");
  h->psunion2(&a);
#else
  T1 *h = hs_from_str("1xxxxxxx");
#endif
  /*uint64_t id1 = */N->add_source(h, make_sorted_list(1,100), 1);
#ifdef GENERIC_PS
  h = new T1(1);
  T2 b = T2 ("xxxxxxxx");
  h->psunion2(&b);
#else
  h = hs_from_str("xxxxxxxx");
#endif
  uint64_t id2 = N->add_source(h, make_sorted_list(1,100), 2);
  //N->print_plumbing_network();
  N->remove_source(id2);
  int stats[7][2] = {
      {1,0},
      {1,0},
#ifdef USE_BDD
      {3,0},
#else
      {1,2},
#endif
      {0,0},
      {2,0},
#ifdef NEW_HS
      {1,1},
#else
      {1,0},
#endif
      {2,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_remove_source", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_add_fwd_rule_lower_priority() {
  printf("\n");
  this->test_routing_add_source();
  node_ids.push_back(N->add_rule(1,-1,
              make_sorted_list(1,1),
              make_sorted_list(2,2,3),
#ifdef GENERIC_PS
              new T2 ("xxx11xxx"),
#else
              array_from_str("xxx11xxx"),
#endif
              NULL,
              NULL));
  int stats[8][2] = {
      {1,0},
      {1,0},
#ifdef USE_BDD
      {3,0},
#else
      {1,2},
#endif
      {0,0},
      {2,0},
#ifdef NEW_HS
      {1,1},
#else
      {1,0},
#endif
      {2,0},
#ifdef NEW_HS
      {1,1}
#else
      {1,0}
#endif
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_add_fwd_rule_lower_priority", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_add_rw_rule_lower_priority() {
  printf("\n");
  this->test_routing_add_source();
  node_ids.push_back(N->add_rule(1,-1,
              make_sorted_list(1,1),
              make_sorted_list(2,2,3),
#ifdef GENERIC_PS
              new T2 ("xxx11xxx"),
              new T2 ("01000000"),
              new T2 ("00000000")
#else
              array_from_str("xxx11xxx"),
              array_from_str("01000000"),
              array_from_str("00000000")
#endif
  ));
  int stats[8][2] = {
      {1,0},
      {1,0},
#ifdef USE_BDD
      {3,0},
#else
      {1,2},
#endif
// XXX: dirty fix
#ifdef NEW_HS
      {0,0},
      {2,0},
      {1,1},
      {2,0},
      {1,1}
#else
      {1,0},
      {3,0},
      {2,0},
      {3,0},
      {1,0}
#endif
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_add_rw_rule_lower_priority", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_add_fwd_rule_higher_priority() {
  printf("\n");
  this->test_routing_add_source();
  node_ids.push_back(N->add_rule(1,0,
              make_sorted_list(1,1),
              make_sorted_list(2,2,3),
#ifdef GENERIC_PS
              new T2 ("xxxx11xx"),
#else
              array_from_str("xxxx11xx"),
#endif
              NULL,
              NULL));
  int stats[8][2] = {
#ifdef USE_BDD
      {2,0},
#else
      {1,1},
#endif
#ifdef NEW_HS
      {1,1},
#else
      {1,0},
#endif
#ifdef USE_BDD
      {5,0},
#else
      {1,3},
#endif
      {1,0},
#ifdef NEW_HS
      {3,3},
      {2,2},
      {2,0},
#else
#ifdef USE_BDD
      {3,0},
#else
      {3,1},
#endif
      {2,0},
      {2,0},
#endif
      {1,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats(
    "test_routing_add_fwd_rule_higher_priority",
    stats
  );
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_add_rw_rule_higher_priority() {
  printf("\n");
  this->test_routing_add_source();
  node_ids.push_back(N->add_rule(2,0,
              make_sorted_list(1,4),
              make_sorted_list(1,5),
#ifdef GENERIC_PS
              new T2 ("10xx1xxx"),
              new T2 ("11000000"),
              new T2 ("01000000")
#else
              array_from_str("10xx1xxx"),
              array_from_str("11000000"),
              array_from_str("01000000")
#endif
              ));
  int stats[8][2] = {
      {1,0},
      {1,0},
#ifdef USE_BDD
      {3,0},
#else
      {1,2},
#endif
      {0,0},
#ifdef NEW_HS
      {1,1},
      {1,2},
      {3,1},
#else
      {1,0},
      {1,0},
      {2,0},
#endif
      {2,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_add_rw_rule_higher_priority", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_add_rw_rule_higher_priority2() {
  printf("\n");
  this->test_routing_add_source();
  node_ids.push_back(N->add_rule(3,0,
              make_sorted_list(1,6),
              make_sorted_list(1,7),
#ifdef GENERIC_PS
              new T2 ("1xxxxxxx"),
              new T2 ("00100000"),
              new T2 ("00000000")
#else
              array_from_str("1xxxxxxx"),
              array_from_str("00100000"),
              array_from_str("00000000")
#endif
              ));
  int stats[8][2] = {
      {1,0},
      {1,0},
#ifdef USE_BDD
      {3,0},
#else
      {1,2},
#endif
      {0,0},
      {2,0},
      {0,0},
      {2,0},
#ifdef WITH_EXTRA_NEW
#ifdef NEW_HS
      {1,2}
#else
      {1,0}
#endif
#else
      {1,1}
#endif
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_add_rw_rule_higher_priority2", stats);
}

#ifdef USE_GROUPS
template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_add_group_rule_mid_priority() {
  printf("\n");
  this->test_routing_add_source();
  node_ids.push_back(N->add_rule_to_group(1,1,
              make_sorted_list(1,1),
              make_sorted_list(1,2),
#ifdef GENERIC_PS
              new T2 ("xxxx11xx"),
              new T2 ("00011000"),
              new T2 ("00000000"),
#else
              array_from_str("xxxx11xx"),
              array_from_str("00011000"),
              array_from_str ("00000000"),
#endif
              0
  ));
  node_ids.push_back(N->add_rule_to_group(1,0,
              make_sorted_list(1,1),
              make_sorted_list(1,3),
#ifdef GENERIC_PS
              new T2 ("xxxx11xx"),
#else
              array_from_str("xxxx11xx"),
#endif
              NULL,
              NULL,node_ids[node_ids.size()-1]));
  int stats[9][2] = {
      {1,0},
#ifdef NEW_HS
      {1,1},
#else
      {1,0},
#endif
      {1,3},
      {0,0},
#ifdef NEW_HS
      {3,2},
      {2,4},
      {2,1},
      {1,1}, // new rule 1
      {1,1}  // new rule 2
#else
      {3,0},
      {2,0},
      {2,0},
      {1,0}, // new rule 1
      {1,1}  // new rule 2
#endif
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_add_group_rule_mid_priority", stats);
}
#endif

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_add_rule_block_bounce() {
  printf("\n");
  this->test_routing_add_source();
  node_ids.push_back(N->add_rule(1,0,
              make_sorted_list(3,1,2,3),
              make_sorted_list(2,2,3),
#ifdef GENERIC_PS
              new T2 ("xxxx11xx"),
#else
              array_from_str("xxxx11xx"),
#endif
              NULL,
              NULL));
  node_ids.push_back(N->add_rule(3,0,
              make_sorted_list(1,6),
              make_sorted_list(1,6),
#ifdef GENERIC_PS
              new T2 ("100x11xx"),
#else
              array_from_str("100x11xx"),
#endif
              NULL,
              NULL));
  int stats[9][2] = {
#ifdef USE_BDD
      {2,0},
#else
      {1,1},
#endif
#ifdef NEW_HS
      {1,1},
#else
      {1,0},
#endif
#ifdef USE_BDD
      {5,0},
#else
      {1,3},
#endif
      {1,0},
#ifdef NEW_HS
      {3,3},
      {2,3},
      {2,2},
#else
#ifdef USE_BDD
      {3,0},
#else
      {3,1},
#endif
      {2,0},
      {2,0},
#endif
      {1,0},
      {1,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_add_rule_block_bounce", stats);
}

#ifdef USE_GROUPS
template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_remove_group_rule_mid_priority() {
  this->test_routing_add_group_rule_mid_priority();
  N->remove_rule(node_ids[node_ids.size()-1]);
  node_ids.pop_back();
  node_ids.pop_back();
  int stats[7][2] = {
      {1,0},
      {1,0},
#ifdef USE_BDD
      {3,0},
#else
      {1,2},
#endif
      {0,0},
      {2,0},
#ifdef NEW_HS
      {1,2},
#else
      {1,0},
#endif
      {2,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_remove_group_rule_mid_priority", stats);
}
#endif

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_remove_fwd_rule_lower_priority() {
  printf("\n");
  this->test_routing_add_source();
  N->remove_rule(node_ids[2]);
  typename std::vector<uint64_t>::iterator it = node_ids.begin();
  advance(it,2);
  node_ids.erase(it);
  int stats[6][2] = {
      {1,0},
      {1,0},
      {0,0},
      {2,0},
      {0,0},
      {2,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_remove_fwd_rule_lower_priority", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_remove_rw_rule_lower_priority() {
  printf("\n");
  this->test_routing_add_source();
  N->remove_rule(node_ids[4]);
  typename std::vector<uint64_t>::iterator it = node_ids.begin();
  advance(it,4);
  node_ids.erase(it);
  int stats[6][2] = {
      {1,0},
      {1,0},
#ifdef USE_BDD
      {3,0},
#else
      {1,2},
#endif
      {0,0},
#ifdef NEW_HS
      {1,2},
#else
      {1,0},
#endif
      {0,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_remove_rw_rule_lower_priority", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_remove_fwd_rule_higher_priority() {
  this->test_routing_add_fwd_rule_higher_priority();
  N->remove_rule(node_ids.back());
  node_ids.pop_back();
  int stats[7][2] = {
      {1,0},
      {1,0},
#ifdef USE_BDD
      {3,0},
#else
      {1,2},
#endif
      {0,0},
      {2,0},
#ifdef NEW_HS
      {1,2},
#else
      {1,0},
#endif
      {2,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_remove_fwd_rule_higher_priority", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_remove_rw_rule_higher_priority() {
  this->test_routing_add_rw_rule_higher_priority();
  N->remove_rule(node_ids.back());
  node_ids.pop_back();
  int stats[7][2] = {
      {1,0},
      {1,0},
#ifdef USE_BDD
      {3,0},
#else
      {1,2},
#endif
      {0,0},
      {2,0},
#ifdef NEW_HS
      {1,2},
#else
      {1,0},
#endif
      {2,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_remove_rw_rule_higher_priority", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_add_link() {
  this->test_routing_add_fwd_rule_higher_priority();
  node_ids.push_back(N->add_rule(3,0,
              make_sorted_list(1,12),
              make_sorted_list(1,7),
#ifdef GENERIC_PS
              new T2 ("10xxxxx1"),
              new T2 ("11100111"),
              new T2 ("00000000")
#else
              array_from_str("10xxxxx1"),
              array_from_str("11100111"),
              array_from_str("00000000")
#endif
  ));
  N->add_link(11,12);
  N->add_link(7,8);
  int stats[9][2] = {
#ifdef USE_BDD
      {2,0},
#else
      {1,1},
#endif
#ifdef NEW_HS
      {1,1},
#else
      {1,0},
#endif
#ifdef USE_BDD
      {5,0},
#else
      {1,3},
#endif
      {1,0},
#ifdef NEW_HS
      {3,3},
      {3,3},
#else
#ifdef USE_BDD
      {3,0},
#else
      {3,1},
#endif
      {3,0},
#endif
      {3,0},
      {1,0},
      {1,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_add_link", stats);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_routing_remove_link() {
  this->test_routing_add_link();

  N->remove_link(7,8);
  int stats1[9][2] = {
#ifdef USE_BDD
      {2,0},
#else
      {1,1},
#endif
#ifdef NEW_HS
      {1,1},
#else
      {1,0},
#endif
#ifdef USE_BDD
      {5,0},
#else
      {1,3},
#endif
      {1,0},
#ifdef NEW_HS
      {3,3},
      {3,3},
#else
#ifdef USE_BDD
      {3,0},
#else
      {3,1},
#endif
      {3,0},
#endif
      {2,0},
      {1,0},
      {1,0}
  };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_remove_link", stats1);
  N->remove_link(11,12);
  int stats2[9][2] = {
#ifdef USE_BDD
        {2,0},
#else
        {1,1},
#endif
// XXX: dirty fix
#ifdef NEW_HS
        {1,1},
#else
        {1,0},
#endif
#ifdef USE_BDD
        {5,0},
#else
        {1,3},
#endif
        {1,0},
// XXX: dirty fix
#ifdef NEW_HS
        {3,3},
        {2,2},
#else
#ifdef USE_BDD
        {3,0},
#else
        {3,1},
#endif
        {2,0},
#endif
        {2,0},
        {1,0},
        {0,0}
    };
  //N->print_plumbing_network();
  this->verify_source_flow_stats("test_routing_remove_link", stats2);
}

template<class T1, class T2>
void loop_detected(NetPlumber<T1, T2>* /*N*/, Flow<T1, T2>* f, void* data) {
  bool *is_looped = (bool *)(data);
  *is_looped = true;
  return;
  uint32_t table_ids[4] = {1,3,2,1};
  for (int i=0; i < 4; i++) {
    RuleNode<T1, T2> *r = (RuleNode<T1, T2> *)f->node;
    CPPUNIT_ASSERT(r->table == table_ids[i]);
    f = *f->p_flow;
  }
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_detect_loop() {
  printf("\n");
  bool is_looped = false;
  N->loop_callback = loop_detected;
  N->loop_callback_data = &is_looped;
  this->test_routing_add_fwd_rule_higher_priority();
  N->add_link(2,12);
  N->add_link(14,15);
  node_ids.push_back(N->add_rule(3,0,
              make_sorted_list(1,12),
              make_sorted_list(1,14),
#ifdef GENERIC_PS
              new T2 ("10xxxxx1"),
#else
              array_from_str("10xxxxx1"),
#endif
              NULL,
              NULL));
  node_ids.push_back(N->add_rule(1,0,
              make_sorted_list(1,15),
              make_sorted_list(1,2),
#ifdef GENERIC_PS
              new T2 ("10xxxxxx"),
#else
              array_from_str("10xxxxxx"),
#endif
              NULL,
              NULL));
  //N->print_plumbing_network();
  CPPUNIT_ASSERT(is_looped);
}

template<class T1, class T2>
void probe_fire_counter(void* /*caller*/, SourceProbeNode<T1, T2>* /*p*/, Flow<T1, T2>* /*f*/,
                   void *data, PROBE_TRANSITION t) {
  probe_counter_t *a = (probe_counter_t*)data;
  switch (t) {
    case(STARTED_FALSE): (*a).start_false++; break;
    case(STARTED_TRUE): (*a).start_true++; break;
    case(TRUE_TO_FALSE): (*a).true_to_false++; break;
    case(FALSE_TO_TRUE): (*a).false_to_true++; break;
    case(MORE_FALSE): (*a).more_false++; break;
    case(LESS_FALSE): (*a).less_false++; break;
    case(MORE_TRUE): (*a).more_true++; break;
    case(LESS_TRUE): (*a).less_true++; break;
    default: break;
  }
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_false_probe() {
  this->test_routing_add_source();
  N->add_link(13,200);
  probe_counter_t a = {0,0,0,0,0,0,0,0};
  probe_counter_t r = {0,3,0,0,0,0,0,0};
  node_ids.push_back(N->add_source_probe(
       make_sorted_list(1,200), EXISTENTIAL, nullptr, new TrueCondition<T1, T2>(),
       new FalseCondition<T1, T2>(), probe_fire_counter, &a, 3));
  node_ids.push_back(N->add_source_probe(
       make_sorted_list(1,200), UNIVERSAL, nullptr, new TrueCondition<T1, T2>(),
       new FalseCondition<T1, T2>(), probe_fire_counter, &a, 4));
  this->check_probe_counter("test_false_probe", a, r);
  //N->print_plumbing_network();
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_true_probe() {
  this->test_routing_add_source();
  N->add_link(13,200);
  probe_counter_t a = {0,0,0,0,0,0,0,0};
  probe_counter_t r = {3,0,0,0,0,0,0,0};
  node_ids.push_back(N->add_source_probe(
       make_sorted_list(1,200), EXISTENTIAL, nullptr, new TrueCondition<T1, T2>(),
       new TrueCondition<T1, T2>(), probe_fire_counter, &a, 3));
  node_ids.push_back(N->add_source_probe(
       make_sorted_list(1,200), UNIVERSAL, nullptr, new TrueCondition<T1, T2>(),
       new TrueCondition<T1, T2>(), probe_fire_counter, &a, 4));
  this->check_probe_counter("test_true_probe", a, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_port_probe() {
  this->test_routing_add_source();
  N->add_link(13,200);
  probe_counter_t a = {0,0,0,0,0,0,0,0};
  probe_counter_t r = {1,0,0,0,0,0,0,0};
  PathCondition<T1, T2> *c = new PathCondition<T1, T2>();
  c->add_pathlet(new PortSpecifier<T1, T2>(4));
  N->add_source_probe(
         make_sorted_list(1,200), UNIVERSAL, nullptr, new TrueCondition<T1, T2>(),
         c, probe_fire_counter, &a, 3);
  this->check_probe_counter("test_port_probe", a, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_table_probe() {
  this->test_routing_add_source();
  N->add_link(13,200);
  probe_counter_t a = {0,0,0,0,0,0,0,0};
  probe_counter_t r = {2,0,0,0,0,0,0,0};
  PathCondition<T1, T2> *c = new PathCondition<T1, T2>();
  c->add_pathlet(new TableSpecifier<T1, T2>(2));
  PathCondition<T1, T2> *f = new PathCondition<T1, T2>();
  c->add_pathlet(new LastPortsSpecifier<T1, T2>(make_sorted_list(1,1)));
  N->add_source_probe(
         make_sorted_list(1,200), EXISTENTIAL, nullptr, f,
         c, probe_fire_counter, &a, 3);
  this->check_probe_counter("test_table_probe",  a, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_reachability() {
  this->test_routing_add_source();
  N->add_link(13,200);
  probe_counter_t a = {0,0,0,0,0,0,0,0};
  probe_counter_t r = {2,0,0,0,0,0,0,0};
  PathCondition<T1, T2> *c = new PathCondition<T1, T2>();
  c->add_pathlet(new LastPortsSpecifier<T1, T2>(make_sorted_list(1,1)));
  N->add_source_probe(
         make_sorted_list(1,200), EXISTENTIAL, nullptr, new TrueCondition<T1, T2>(),
         c, probe_fire_counter, &a, 3);
  this->check_probe_counter("test_reachability", a, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_probe_transition_no_update_add_rule() {
  this->test_routing_add_source();
  N->add_link(13,200);
  memset(&A,0,sizeof A);
  probe_counter_t r = {2,0,0,0,0,0,0,0};
  PathCondition<T1, T2> *c = new PathCondition<T1, T2>();
  c->add_pathlet(new LastPortsSpecifier<T1, T2>(make_sorted_list(1,1)));
  N->add_source_probe(
         make_sorted_list(1,200), EXISTENTIAL, nullptr, new TrueCondition<T1, T2>(),
         c, probe_fire_counter, &A, 3);
  node_ids.push_back(N->add_rule(1,-1,
              make_sorted_list(1,1),
              make_sorted_list(2,2,3),
#ifdef GENERIC_PS
              new T2 ("xxx11xxx"),
#else
              array_from_str("xxx11xxx"),
#endif
              NULL,
              NULL));
  //N->print_plumbing_network();
  this->check_probe_counter("test_probe_transition_no_update_add_rule", A, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_probe_transition_no_update_remove_rule() {
  this->test_probe_transition_no_update_add_rule();
  memset(&A,0,sizeof A);
  probe_counter_t r = {0,0,0,0,0,0,0,0};
  N->remove_rule(node_ids[node_ids.size()-1]);
  this->check_probe_counter("test_probe_transition_no_update_remove_rule", A, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_probe_transition_with_update_add_rule1() {
  this->test_routing_add_source();
  N->add_link(13,200);
  memset(&A,0,sizeof A);
// XXX: dirty fix
#ifdef NEW_HS
  probe_counter_t r = {2,0,0,0,0,0,0,0};
#else
  probe_counter_t r = {2,0,0,0,1,0,0,0};
#endif
  PathCondition<T1, T2> *c = new PathCondition<T1, T2>();
  c->add_pathlet(new LastPortsSpecifier<T1, T2>(make_sorted_list(1,1)));
  N->add_source_probe(
         make_sorted_list(1,200), EXISTENTIAL, nullptr, new TrueCondition<T1, T2>(),
         c, probe_fire_counter, &A, 3);
  node_ids.push_back(N->add_rule(3,0,
              make_sorted_list(1,6),
              make_sorted_list(1,7),
#ifdef GENERIC_PS
              new T2 ("1xxxxxxx"),
              new T2 ("00011000"),
              new T2 ("00001000")
#else
              array_from_str("1xxxxxxx"),
              array_from_str("00011000"),
              array_from_str ("00001000")
#endif
              ));
  node_ids.push_back(N->add_rule(4, -1,
    make_sorted_list(1,9),
    make_sorted_list(1,13),
#ifdef GENERIC_PS
    new T2 ("xxxxxxxx"),
#else
    array_from_str("xxxxxxxx"),
#endif
    NULL,
    NULL
  ));
  //N->print_plumbing_network();
  this->check_probe_counter("test_probe_transition_with_update_add_rule1", A, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_probe_transition_with_update_add_rule2() {
  this->test_routing_add_source();
  N->add_link(13,200);
  memset(&A,0,sizeof A);
  probe_counter_t r = {2,0,1,0,0,0,0,1};
  PathCondition<T1, T2> *c = new PathCondition<T1, T2>();
  c->add_pathlet(new LastPortsSpecifier<T1, T2>(make_sorted_list(1,1)));
  N->add_source_probe(
         make_sorted_list(1,200), EXISTENTIAL, nullptr, new TrueCondition<T1, T2>(),
         c, probe_fire_counter, &A, 3);
  node_ids.push_back(N->add_rule(1,0,
              make_sorted_list(1,1),
              make_sorted_list(1,15),
#ifdef GENERIC_PS
              new T2 ("10xxxxxx"),
#else
              array_from_str("10xxxxxx"),
#endif
              NULL,
              NULL));
  //N->print_plumbing_network();
  this->check_probe_counter("test_probe_transition_with_update_add_rule2", A, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_probe_transition_with_update_remove_rule() {
  this->test_probe_transition_with_update_add_rule2();
  memset(&A,0,sizeof A);
  N->remove_rule(node_ids[node_ids.size()-1]);
  probe_counter_t r = {0,0,0,1,1,0,0,0};
  this->check_probe_counter("test_probe_transition_with_update_remove_rule", A, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_probe_transition_add_link() {
  printf("\n");
  N->add_link(13,200);
  memset(&A,0,sizeof A);
  probe_counter_t r = {0,1,0,1,0,0,0,0};
  PathCondition<T1, T2> *c = new PathCondition<T1, T2>();
  c->add_pathlet(new TableSpecifier<T1, T2>(3));
  N->add_source_probe(
         make_sorted_list(1,200), EXISTENTIAL, nullptr, new TrueCondition<T1, T2>(),
         c, probe_fire_counter, &A, 3);
  this->test_routing_add_link();
  //N->print_plumbing_network();
  this->check_probe_counter("test_probe_transition_add_link", A, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_probe_transition_remove_link() {
  printf("\n");
  N->add_link(13,200);
  memset(&A,0,sizeof A);
  probe_counter_t r = {0,1,1,1,0,0,0,0};
  PathCondition<T1, T2> *c = new PathCondition<T1, T2>();
  c->add_pathlet(new TableSpecifier<T1, T2>(3));
  N->add_source_probe(
         make_sorted_list(1,200), EXISTENTIAL, nullptr, new TrueCondition<T1, T2>(),
         c, probe_fire_counter, &A, 3);
  this->test_routing_remove_link();
  //N->print_plumbing_network();
  this->check_probe_counter("test_probe_transition_remove_link", A, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_probe_transition_add_source() {
  printf("\n");
  this->test_routing_add_source();
  N->add_link(13,200);
  N->add_link(300,4);
  memset(&A,0,sizeof A);
  probe_counter_t r = {0,1,0,1,1,0,0,0};
  PathCondition<T1, T2> *c = new PathCondition<T1, T2>();
  c->add_pathlet(new LastPortsSpecifier<T1, T2>(make_sorted_list(1,4)));
  N->add_source_probe(
         make_sorted_list(1,200), EXISTENTIAL, nullptr, new TrueCondition<T1, T2>(),
         c, probe_fire_counter, &A, 3);
#ifdef GENERIC_PS
  T1 *h = new T1(1);
  T2 a = T2 ("xxxxxxxx");
  h->psunion2(&a);
#else
  T1 *h = hs_from_str("xxxxxxxx");
#endif
  node_ids.push_back(
      N->add_source(h, make_sorted_list(1,300), 2)
      );

  //N->print_plumbing_network();
  this->check_probe_counter("test_probe_transition_add_source", A, r);
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::test_probe_transition_remove_source() {
  printf("\n");
  this->test_probe_transition_add_source();
  memset(&A,0,sizeof A);
  probe_counter_t r = {0,0,1,0,0,0,0,1};
  N->remove_source(node_ids[node_ids.size()-1]);
  //N->print_plumbing_network();
  this->check_probe_counter("test_probe_transition_remove_source", A, r);
}

/* * * * * * * * * * *
 * Testing FUnctions *
 * * * * * * * * * * *
 */

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::verify_pipe_stats(const char *test_case, const int stats[][4]) {

  if (logger->isDebugEnabled()) {
    stringstream intro_msg;
    intro_msg << "========== pipelines: " << test_case << " ==========";
    LOG4CXX_DEBUG(logger, intro_msg.str());
  }

  for (unsigned i = 0; i < node_ids.size(); i++) {
      int fwd_pipeline;
      int bck_pipeline;
      int influence_on;
      int influenced_by;
      N->get_pipe_stats(node_ids[i],fwd_pipeline,bck_pipeline,
          influence_on,influenced_by);

      if (logger->isDebugEnabled()) {
        stringstream error_msg;
        error_msg << "(fwd, bck, inf_on, inf_by) - Obtained: " << fwd_pipeline <<
            " , " << bck_pipeline << " , " << influence_on << " , " <<
            influenced_by << " Expected " << stats[i][0] << " , " << stats[i][1]
            << " , " << stats[i][2] << " , " << stats[i][3];
        LOG4CXX_DEBUG(logger,error_msg.str());
      }

      if (fwd_pipeline != stats[i][0]) N->print_node(node_ids[i]);
      CPPUNIT_ASSERT(fwd_pipeline == stats[i][0]);
      if (bck_pipeline != stats[i][1]) N->print_node(node_ids[i]);
      CPPUNIT_ASSERT(bck_pipeline == stats[i][1]);
      if (influence_on != stats[i][2]) N->print_node(node_ids[i]);
      CPPUNIT_ASSERT(influence_on == stats[i][2]);
      if (influenced_by != stats[i][3]) N->print_node(node_ids[i]);
      CPPUNIT_ASSERT(influenced_by == stats[i][3]);
  }
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::verify_source_flow_stats(const char *test_case, const int stats[][2]) {
  if (logger->isDebugEnabled()) {
    stringstream intro_msg;
    intro_msg << "========== source flows: " << test_case << " ==========";
    LOG4CXX_DEBUG(logger, intro_msg.str());
  }

  stringstream dir;
  dir << "np_dump/" << test_case;
  N->dump_net_plumber(dir.str());

  for (unsigned i = 0; i < node_ids.size(); i++) {
    int inc, exc;
    N->get_source_flow_stats(node_ids[i], inc, exc);
    if (logger->isDebugEnabled()) {
      stringstream error_msg;
      error_msg << "For node 0x" << std::hex << node_ids[i] <<  " (included wc, excluded_wc) - Obtained: " << inc <<
          " , " << exc << " Expected " << stats[i][0] << " , " << stats[i][1];
      LOG4CXX_DEBUG(logger,error_msg.str());
    }

    if (inc != stats[i][0]) N->print_node(node_ids[i]);
    CPPUNIT_ASSERT(inc == stats[i][0]);
    if (exc != stats[i][1]) N->print_node(node_ids[i]);
    CPPUNIT_ASSERT(exc == stats[i][1]);
  }
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::log_probe_counter(
    std::string counter, size_t result, size_t expected
) {
  if (logger->isDebugEnabled()) {
    stringstream error_msg;
    error_msg << counter << " obtained:\t" << result << " , " << expected;
    LOG4CXX_DEBUG(logger,error_msg.str());
  }
}

template<class T1, class T2>
void NetPlumberPlumbingTest<T1, T2>::check_probe_counter(
    const char *test_case,
    const probe_counter_t result,
    const probe_counter_t expected
) {
  if (logger->isDebugEnabled()) {
    stringstream intro_msg;
    intro_msg << "========== probe counter: " << test_case << " ==========";
    LOG4CXX_DEBUG(logger, intro_msg.str());
  }

  log_probe_counter("start_true", result.start_true, expected.start_true);
  CPPUNIT_ASSERT(result.start_true == expected.start_true);
  log_probe_counter("start_false", result.start_false, expected.start_false);
  CPPUNIT_ASSERT(result.start_false == expected.start_false);
  log_probe_counter("true_to_false", result.true_to_false, expected.true_to_false);
  CPPUNIT_ASSERT(result.true_to_false == expected.true_to_false);
  log_probe_counter("false_to_true", result.false_to_true, expected.false_to_true);
  CPPUNIT_ASSERT(result.false_to_true == expected.false_to_true);
  log_probe_counter("more_true", result.more_true, expected.more_true);
  CPPUNIT_ASSERT(result.more_true == expected.more_true);
  log_probe_counter("more_false", result.more_false, expected.more_false);
  CPPUNIT_ASSERT(result.more_false == expected.more_false);
  log_probe_counter("less_false", result.less_false, expected.less_false);
  CPPUNIT_ASSERT(result.less_false == expected.less_false);
  log_probe_counter("less_true", result.less_true, expected.less_true);
  CPPUNIT_ASSERT(result.less_true == expected.less_true);
}

#ifdef GENERIC_PS
template class NetPlumberPlumbingTest<HeaderspacePacketSet, ArrayPacketSet>;
#ifdef USE_BDD
template class NetPlumberPlumbingTest<BDDPacketSet, BDDPacketSet>;
#endif
#else
template class NetPlumberPlumbingTest<hs, array_t>;
#endif
