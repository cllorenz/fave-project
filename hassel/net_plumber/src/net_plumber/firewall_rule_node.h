/*
   Copyright 2016 Claas Lorenz

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Authors: cllorenz@uni-potsdam.de (Claas Lorenz),
            peyman.kazemian@gmail.com (Peyman Kazemian)
*/

#ifndef SRC_NET_PLUMBER_FIREWALL_NODE_H_
#define SRC_NET_PLUMBER_FIREWALL_NODE_H_

#include "rule_node.h"

class FirewallRuleNode : public RuleNode {
 public:
  hs *fw_match;

  /*
   * constructor
   */
  FirewallRuleNode(void *net_plumber, int length, uint64_t node_id, uint32_t table,
           List_t in_ports ,List_t out_ports,
           hs* fw_match);

  FirewallRuleNode(void *net_plumber, int length, uint64_t node_id, uint32_t table,
           uint64_t group, List_t in_ports ,List_t out_ports,
           hs* fw_match);

  /*
   * destructor
   */
  virtual ~FirewallRuleNode();

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
  //void process_src_flow(Flow *f);
  void process_src_flow_at_location(std::list<struct Flow*>::iterator loc,
                                    array_t* change);
  void process_src_flow_at_location(std::list<struct Flow*>::iterator loc,
                                    hs* change);
  void subtract_infuences_from_flows();
  void repropagate_src_flow_on_pipes(std::list<struct Flow*>::iterator s_flow,
    hs *change);
  void repropagate_src_flow_on_pipes(std::list<struct Flow*>::iterator s_flow,
    array_t *change);

  /*
   * Setting influences.
   */
  std::list<struct Effect*>::iterator set_effect_on(Effect *eff);
  std::list<struct Influence*>::iterator set_influence_by(Influence *inf);

  /*
   * stats reporting functions
   */
  int count_effects();
  int count_influences();
};

#endif  // SRC_NET_PLUMBER_FIREWALL_NODE_H_
