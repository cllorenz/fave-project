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
           kiekhebe@uni-potsdam.de (Sebastian Kiekheben)
*/

#ifndef SRC_NET_PLUMBER_RULE_NODE_H_
#define SRC_NET_PLUMBER_RULE_NODE_H_

#include "node.h"

template<class T1, class T2>
class RuleNode;

template<class T1, class T2>
struct Effect;

template<class T1, class T2>
struct Influence {
  RuleNode<T1, T2> *node;
  uint32_t len;
  typename std::list<struct Effect<T1, T2> *>::iterator effect;
  union { T2 *comm_arr; T1 *comm_hs; };
  List_t ports;
};

template<class T1, class T2>
struct Effect {
  RuleNode<T1, T2> *node;
  typename std::list<struct Influence<T1, T2> *>::iterator influence;
};

template<class T1, class T2>
class RuleNode : public Node<T1, T2> {
 public:
  const uint32_t table;
  const uint32_t index;
#ifdef USE_GROUPS
  uint64_t group;
#endif
  T2 *mask;
  T2 *rewrite;
  T2 *inv_rw;
  std::list<struct Effect<T1, T2> *> *effect_on;
  std::list<struct Influence<T1, T2> *> *influenced_by;

  /*
   * constructor
   */
#ifdef USE_GROUPS
  RuleNode(void *net_plumber, int length, uint64_t node_id, uint32_t table, uint32_t index,
           uint64_t group, List_t in_ports ,List_t out_ports,
           T2* match, T2 *mask, T2* rw);
#else
  RuleNode(void *net_plumber, int length, uint64_t node_id, uint32_t table, uint32_t index,
           List_t in_ports ,List_t out_ports,
           T2* match, T2 *mask, T2* rw);
#endif

  /*
   * destructor
   */
  virtual ~RuleNode();

  /*
   * generate a string representing the rule itself
   * (i.e. no influence or pipeline)
   */
  std::string rule_to_str();

  /*
   * generate a string representing the table influences.
   */
  std::string influence_to_str();

  /*
   * generate the full string representing this rule.
   */
  std::string to_string();

  /*
   * - process_src_flow: process flow @f by removing dependency hs and doing
   * appropriate rewrite action. then propagate it to next nodes.
   * - subtract_infuences_from_flows: call this function  when this rule is
   * added for the first time so that the influence of this flow on other nodes
   * is propagataed through the network
   * - subtract_from_src_flow: subtracts @arr_sub from @s_flow and propagates
   * the result throughout the network.
   */
  void process_src_flow(Flow<T1, T2> *f);
  void process_src_flow_at_location(typename std::list<struct Flow<T1, T2> *>::iterator loc,
                                    T2* change);
  void subtract_infuences_from_flows();

  /*
   * Setting influences.
   */
  typename std::list<struct Effect<T1, T2> *>::iterator set_effect_on(Effect<T1, T2> *eff);
  typename std::list<struct Influence<T1, T2> *>::iterator set_influence_by(Influence<T1, T2> *inf);

  /*
   * stats reporting functions
   */
  int count_effects();
  int count_influences();
  void enlarge(uint32_t size);

 protected:
  void set_layer_flags();
};

#endif  // SRC_NET_PLUMBER_RULE_NODE_H_
