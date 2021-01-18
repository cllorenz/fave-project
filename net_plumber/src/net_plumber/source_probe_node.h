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
            kiekhebe@uni-potsdam.de (Sebastian Kiekheben)
*/

#ifndef SRC_NET_PLUMBER_SOURCE_PROBE_NODE_H_
#define SRC_NET_PLUMBER_SOURCE_PROBE_NODE_H_

#include "node.h"
#include "probe_node_commons.h"
#include "conditions.h"
#include <map>

/*
 * SourceProbeNode class provides a way to check conditions on source flows.
 * The probe can be instantiated in two modes: Existential and Universal.
 * The probe accepts a filter condition (@filter) and a testing condition
 * (@condition):
 * - Universal Probe: "FOR ALL flows matching @filter condition, the @test
 * condition holds.
 * - Existential Probe: "THERE EXIST a flow matching @filter condition for
 * which @test condition holds.
 *
 * Examples 1: All flows from port P1 to port P2 pass through middle box M:
 *  * Connect a SourceNode to port P1.
 *  * Connect a Universal SourceProbeNode to port P2.
 *  * Set @filter condition of probe to ".*(p=P1)$" (i.e. PathCondition with
 *  a PortSpecifier(P1) and an EndPathSpecifier())
 *  * Set @test condition of probe to ".*(t=M)" (i.e. PathCondition with a
 *  TableSpecifier(M))
 *
 *  Example 2: port P1 can communicate to port P2:
 *  * Connect a SourceNode to port P1
 *  * Connect an Existential SourceProbeNode to port P2.
 *  * Set @filter condition of probe to TrueCondition (always true)
 *  * Set @test condition of probe to ".*(p=P1)$" (i.e. a PathCondition with a
 *  PortSpecifier(P1) and an EndPathSpecifier())
 *
 *  Example 3: All traffic from edge ports to port P should pass through
 *  Middle box M1 or M2 and immediately followed by filter box F1 or F2.
 *  * Connect a SourceNode to every edge port in network.
 *  * Connect a Universal SourceProbeNode to port P.
 *  * Set @filter condition of probe to LastPortsSpecifier([set of edge ports])
 *  * Set @test condition of probe to
 *  "(.*(t=M1)(t=F1 | t = F2)) | (.*(t=M2)(t = F1 | t = F2))"
 *  (i.e. OrCondition of two path conditions below:
 *    PathCondition1: TableSpecifier(M1) --> NextTablesSpecifier([F1,F2])
 *    PathCondition2: TableSpecifier(M2) --> NextTablesSpecifier([F1,F2])
 *  )
 *
 * Example 4: All flows from edge ports to Port P are at most 3 hubs long.
 *  * Connect a SourceNode to every edge port in network.
 *  * Connect a Universal SourceProbeNode to port P.
 *  * Set @filter condition of probe to LastPortsSpecifier([set of edge ports])
 *  * Set @test condition of probe to the following:
 *  .$ | ..$ | ...$ (i.e. OrCondition of the following:
 *  PathCondition1: SkipNextSpecifier --> EndPathSpecifier
 *  PathCondition2: SkipNextSpecifier(2 times) --> EndPathSpecifier
 *  PathCondition3: SkipNextSpecifier(3 times) --> EndPathSpecifier
 */

enum PROBE_MODE {
  EXISTENTIAL,
  UNIVERSAL
};

enum PROBE_TRANSITION {
  UNKNOWN = 0,
  STARTED_TRUE,
  STARTED_FALSE,
  TRUE_TO_FALSE,
  FALSE_TO_TRUE,
  MORE_TRUE,   // in existential mode: more matching flow.
  MORE_FALSE,  // in universal mode: more violating flow.
  LESS_FALSE,  // in universal mode: less violating flow, but still false
  LESS_TRUE    // in existential mode: less matching flow, but still true
};

std::string probe_transition(PROBE_TRANSITION t);

template<class T1, class T2>
class SourceProbeNode;

template<typename T1, typename T2>
using src_probe_callback_t = void (*)(void *caller, SourceProbeNode<T1, T2> *p, Flow<T1, T2> *f, void *data, PROBE_TRANSITION);

template<typename T1, typename T2>
void default_probe_callback(void *caller, SourceProbeNode<T1, T2> *p, Flow<T1, T2> *f,
                            void *data, PROBE_TRANSITION t);

template<class T1, class T2>
class SourceProbeNode : public Node<T1, T2> {
 protected:
  PROBE_STATE state;
  PROBE_MODE mode;
  Condition<T1, T2> *filter;
  Condition<T1, T2> *test;
  std::map< Flow<T1, T2> *, bool >check_results;
  int cond_count;

  /*
   * probe trigger callback
   */
  src_probe_callback_t<T1, T2> probe_callback;
  void *probe_callback_data;

 public:
  SourceProbeNode(void *n, int length, uint64_t node_id, T2 *match,
                  PROBE_MODE mode, List_t ports,
                  Condition<T1, T2> *filter, Condition<T1, T2> *condition,
                  src_probe_callback_t<T1, T2> probe_callback, void *callback_data);
  virtual ~SourceProbeNode();

  /*
   * source flow management functions
   */
  void process_src_flow_at_location(typename std::list<struct Flow<T1, T2> *>::iterator loc,
      T2* change);
  void process_src_flow(Flow<T1, T2> *f);
  void absorb_src_flow(typename std::list<struct Flow<T1, T2> *>::iterator s_flow, bool first);

  void update_check(Flow<T1, T2> *f, PROBE_FLOW_ACTION action);
  void start_probe();
  void stop_probe();
  void enlarge(uint32_t size);

  /*
   * get_condition_count: for existential mode, returns number of flows meeting
   * the condition. for universal case, returns number of flows violating a
   * condition.
   */
  int get_condition_count() {return this->cond_count;}

  PROBE_MODE get_mode() {return this->mode;}

  typename std::list<Flow<T1, T2> *>::iterator get_source_flow_iterator();
  std::string to_string();

  void mode_to_json(Json::Value&);
  void filter_to_json(Json::Value&);
  void test_to_json(Json::Value&);
  void match_to_json(Json::Value&);
};

#endif  // SRC_NET_PLUMBER_SOURCE_PROBE_NODE_H_
