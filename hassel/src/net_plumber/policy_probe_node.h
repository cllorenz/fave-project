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

#ifndef SRC_NET_PLUMBER_POLICY_PROBE_NODE_H_
#define SRC_NET_PLUMBER_POLICY_PROBE_NODE_H_

#include "probe_node_commons.h"
#include "node.h"
#include "policy_checker.h"
#include <map>
#include <list>

/*
 * PolicyProbeNode class provides a way to check global policies on source flows
 */
class PolicyProbeNode;
class PolicyChecker;

typedef void (*policy_probe_callback_t)
    (void *caller, PolicyProbeNode *p, Flow *f, void *data);

void default_probe_callback(void *caller, PolicyProbeNode *p, Flow *f,
                            void *data);
class PolicyProbeNode : public Node {
 protected:
  PROBE_STATE state;
  PolicyChecker *checker;
  std::list<PolicyProbeNode *>::iterator registrant;
  std::map< Flow*, bool >check_results;

  /*
   * probe trigger callback
   */
  policy_probe_callback_t probe_callback;
  void *probe_callback_data;

 public:
  PolicyProbeNode(void *n, int length, uint64_t node_id,
                  List_t ports,
                  PolicyChecker *checker,
                  policy_probe_callback_t probe_callback, void *callback_data);
  virtual ~PolicyProbeNode();

  /*
   * source flow management functions
   */
  void process_src_flow_at_location(std::list<struct Flow*>::iterator loc,
      array_t* change);
  void process_src_flow(Flow *f);
  void absorb_src_flow(std::list<struct Flow*>::iterator s_flow, bool first);

  void reprocess_flows();
  void update_check(Flow *f, PROBE_FLOW_ACTION action);
  void update_paths(Flow *f);
  void start_probe();
  void stop_probe();

  std::list<Flow*>::iterator get_source_flow_iterator();
  std::string to_string();

};

#endif  // SRC_NET_PLUMBER_POLICY_PROBE_NODE_H_
