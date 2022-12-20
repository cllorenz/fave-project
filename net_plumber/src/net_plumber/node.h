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

#ifndef SRC_NET_PLUMBER_NODE_H_
#define SRC_NET_PLUMBER_NODE_H_
#include <vector>
#include <list>
#include <string>
#include "net_plumber_utils.h"
extern "C" {
  #include "../headerspace/array.h"
  #include "../headerspace/hs.h"
}
#include "log4cxx/logger.h"


enum NODE_TYPE {
  BASE = 0,
  RULE,
  SOURCE,
  SINK,
  SOURCE_PROBE,
  SINK_PROBE,
};

template<class T1, class T2>
class Node;
template<class T1, class T2>
struct Pipeline;

template<class T1, class T2>
struct Flow {
  Node<T1, T2> *node; //pointer to next node
  uint64_t source; // the originating source node
  T1 *hs_object; //input hs
  T1 *processed_hs; //output hs. could be the same as hs_object
  uint32_t in_port;  //input port this flow is received on
  Pipeline<T1, T2>* pipe;  //the pipe it has gone through
  typename std::list< Flow<T1, T2>* >::iterator p_flow; // pointer to previous flow
  typename std::list<typename std::list< Flow<T1, T2>* >::iterator> *n_flows;  //pointer to next flow
};

template<typename T1, typename T2>
bool is_flow_looped(Flow<T1, T2> *f);

template<class T1, class T2>
struct Pipeline {
  Node<T1, T2> *node;
  T2 *pipe_array;
  uint32_t local_port;
  uint32_t len;
#ifdef PIPE_SLICING
  uint64_t net_space_id;
  typename std::list<Pipeline<T1, T2>*>::iterator r_slice;
#endif
  typename std::list<Pipeline<T1, T2>*>::iterator r_pipeline;
};

template<class T1, class T2>
class Node {
 protected:
  NODE_TYPE node_type;

  static log4cxx::LoggerPtr logger;

  void remove_src_flows_from_pipe(Pipeline<T1, T2> *fwd_p);
  void remove_sink_flow_from_pipe(Pipeline<T1, T2> *bck_p);
  bool should_block_flow(Flow<T1, T2> *f, uint32_t out_port);
  void remove_flows();
  void remove_pipes();

 public:
  const uint64_t node_id;
  uint32_t length;

  // pointer to net plumber instance.
  void *plumber;

  T2 *match;
  T2 *inv_match;
  bool is_input_layer;
  bool is_output_layer;

  struct List_t input_ports;
  struct List_t output_ports;

  // Note: next_in_pipeline owns the array_t*.
  std::list< Pipeline<T1, T2> *> next_in_pipeline;
  std::list< Pipeline<T1, T2> *> prev_in_pipeline;

  // source and sink flow
  std::list< Flow<T1, T2> *> source_flow;

  Node(void *plumber, int length, uint64_t node_id);
  virtual ~Node();
  NODE_TYPE get_type();
  virtual std::string to_string() = 0;

  /*
   * source flow processing and propagation
   * - process_src_flow: process src flow according to node's specs.
   * - propagate_src_flow_on_pipes: sends @s_flow on all fwd pipes.
   * - propagate_src_flows_on_pipe: sends all source_flow(s) on @pipe.
   * - absorb_src_flow: removes source flow from all nodes in network.
   * if erase is set, s_flow will be removed from @this node's source_flow and
   * its hs_object and processed_hs is freed.
   */
  // initial flow push
  virtual void process_src_flow(Flow<T1, T2> *f) = 0;
  void propagate_src_flow_on_pipes(typename std::list< Flow<T1, T2> *>::iterator s_flow);
  void propagate_src_flows_on_pipe(typename std::list< Pipeline<T1, T2> *>::iterator pipe);
  // updating flow push
  virtual void process_src_flow_at_location(typename std::list< Flow<T1, T2> *>::iterator
                                            loc, T2 *change) = 0;
  void repropagate_src_flow_on_pipes(typename std::list< Flow<T1, T2> *>::iterator s_flow,
                                            T2 *change);
  // removing flow push
  virtual void absorb_src_flow(typename std::list< Flow<T1, T2> *>::iterator s_flow,
      bool first);

  /*
   * to add pipelines
   */
  typename std::list<Pipeline<T1, T2> *>::iterator add_fwd_pipeline(Pipeline<T1, T2> *p);
  typename std::list<Pipeline<T1, T2> *>::iterator add_bck_pipeline(Pipeline<T1, T2> *p);

  /*
   * remove_link_pipes: to remove both fwd and bck pipelines and
   * source and sink flows going on that pipe.
   */
  void remove_link_pipes(uint32_t local_port,uint32_t remote_port);
  virtual void enlarge(uint32_t size) = 0;

  /*
   * generate a string representing the pipelines.
   */
  std::string pipeline_to_string();
  std::string src_flow_to_string();

  /*
   * stat reporting
   */
  int count_fwd_pipeline();
  int count_bck_pipeline();
  void count_src_flow(int &inc, int &exc);

  /*
   * getting input/output state
   */
  bool is_at_input_stage() { return this->is_input_layer; }
  bool is_at_output_stage() { return this->is_output_layer; }

  /*
   * end of source flow iterator
   */
  typename std::list<Flow<T1, T2> *>::iterator get_EOSFI() {return source_flow.end();}

};

#endif  // SRC_NET_PLUMBER_NODE_H_

