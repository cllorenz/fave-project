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
           cllorenz@uni-potsdam.de (Claas Lorenz)
           kiekhebe@uni-potsdam.de (Sebastian Kiekheben)
*/

#include "node.h"
#include <sstream>
#include <set>
#include "array_packet_set.h"
#include "hs_packet_set.h"

#include "net_plumber.h"
using namespace net_plumber;

using namespace std;
using namespace log4cxx;

template<class T1, class T2>
LoggerPtr Node<T1, T2>::logger(Logger::getLogger("NetPlumber"));

template<typename T1, typename T2>
bool is_flow_looped(Flow<T1, T2> *flow) {
  Flow<T1, T2> *f = flow;
  set<uint64_t> seen_rules;
  while(1) {
    uint64_t rule_id = (f->node->node_id);
    if (seen_rules.count(rule_id) == 0) {
      seen_rules.insert(rule_id);
    } else {
      return true;
    }
    if (f->node->get_type() == RULE) {
      f = *f->p_flow;
    } else {
      return false;
    }
  }
}

template<class T1, class T2>
Node<T1, T2>::Node(void *p, int l, uint64_t n) :
    node_type(BASE), node_id(n), length(l), plumber(p),
    match(nullptr), inv_match(nullptr),
    is_input_layer(false), is_output_layer(false)
{
  //do nothing
}

template<class T1, class T2>
void Node<T1, T2>::remove_flows() {
  for (auto f_it = source_flow.begin(); f_it != source_flow.end(); f_it++) {
    if ((*f_it)->processed_hs) delete (*f_it)->processed_hs;
    delete (*f_it)->hs_object;
    this->absorb_src_flow(f_it, true);
    if ((*f_it)->p_flow != this->source_flow.end()) {
      (*(*f_it)->p_flow)->n_flows->remove(f_it);
    }
    free(*f_it);
  }
  source_flow.clear();
}

template<class T1, class T2>
void Node<T1, T2>::remove_pipes() {
  for (auto &next: this->next_in_pipeline) {
    auto r = next->r_pipeline;
    delete (next->pipe_array);
    delete ((*r)->pipe_array);
    Node* other_n = (*r)->node;
    free(*r);
    other_n->prev_in_pipeline.erase(r);
#ifdef PIPE_SLICING
    ((NetPlumber *)plumber)->remove_pipe_from_slices(next);
#endif
    free(next);
  }
  next_in_pipeline.clear();
  for (auto &prev: this->prev_in_pipeline) {
    auto r = prev->r_pipeline;
    delete (prev->pipe_array);
    delete ((*r)->pipe_array);
    Node* other_n = (*r)->node;
    free(*r);
    other_n->next_in_pipeline.erase(r);
    free(prev);
  }
  prev_in_pipeline.clear();
}

template<class T1, class T2>
Node<T1, T2>::~Node() {
  this->remove_flows();
  this->remove_pipes();
  if (!input_ports.shared) free(input_ports.list);
  if (!output_ports.shared) free(output_ports.list);

  if (this->match != this->inv_match) {
    delete this->inv_match;
  }
  delete this->match;
}

template<class T1, class T2>
NODE_TYPE Node<T1, T2>::get_type() {
  return this->node_type;
}

template<class T1, class T2>
typename list<Pipeline<T1, T2>*>::iterator Node<T1, T2>::add_fwd_pipeline(Pipeline<T1, T2> *p) {
  this->next_in_pipeline.push_front(p);
  return this->next_in_pipeline.begin();
}

template<class T1, class T2>
typename list<Pipeline<T1, T2> *>::iterator Node<T1, T2>::add_bck_pipeline(Pipeline<T1, T2> *p) {
  this->prev_in_pipeline.push_front(p);
  return this->prev_in_pipeline.begin();
}

template<class T1, class T2>
string Node<T1, T2>::pipeline_to_string() {
  stringstream result;
  result << "Pipelined TO:\n";
  for (auto const &next: next_in_pipeline) {
    result << "\tNode 0x" << std::hex << (*next->r_pipeline)->node->node_id;
    result << " Pipe HS: " << next->pipe_array->to_str();
    result << " [" << next->local_port << "-->" << (*next->r_pipeline)->local_port << "]\n";
  }
  result << "Pipelined FROM:\n";
  for (auto const &prev: prev_in_pipeline) {
    result << "\tNode 0x" << std::hex << (*prev->r_pipeline)->node->node_id;
    result << " Pipe HS: " << prev->pipe_array->to_str();
    result << " [" << ((*prev->r_pipeline))->local_port << "-->" << prev->local_port << "]\n";
  }
  return result.str();
}

template<class T1, class T2>
string Node<T1, T2>::src_flow_to_string() {
  stringstream result;
  result << "Source Flow:\n";
  for (auto const &flow: source_flow) {
    result << "\tHS: " <<  flow->hs_object->to_str() << " --> ";
    if (flow->processed_hs) {
      result << (flow)->processed_hs->to_str();
    } else {
      if (is_flow_looped(flow)) {
        result << "LOOPED";
      } else {
        result << "DEAD";
      }
    }
    if (flow->node->get_type() == RULE) {
      result << "; From Port: " << flow->in_port;
    }
    result << "\n";
  }
  return result.str();
}

template<class T1, class T2>
void Node<T1, T2>::remove_link_pipes(uint32_t local_port,uint32_t remote_port) {
  for (auto it = next_in_pipeline.begin(); it != next_in_pipeline.end(); ) {
    auto r = (*it)->r_pipeline;
    if ((*it)->local_port == local_port && (*r)->local_port == remote_port) {
      (*r)->node->remove_src_flows_from_pipe(*it);
      (*it)->node->remove_sink_flow_from_pipe(*r);
      delete (*it)->pipe_array;
      auto tmp = r;
      struct Pipeline<T1, T2> *pipe = *r;
      delete pipe->pipe_array;
      (*r)->node->prev_in_pipeline.erase(r);
      free(pipe);
      free(*it);
      tmp = it;
      it++;
      next_in_pipeline.erase(tmp);
    } else {
      it++;
    }
  }
}

template<class T1, class T2>
void Node<T1, T2>::remove_src_flows_from_pipe(Pipeline<T1, T2> *fwd_p) {
  for (auto it = source_flow.begin(); it != source_flow.end(); /*none*/) {
    if ((*it)->pipe == fwd_p) {
      this->absorb_src_flow(it,true);
      (*(*it)->p_flow)->n_flows->remove(it);
      if ((*it)->processed_hs) delete (*it)->processed_hs;
      delete (*it)->hs_object;
      free(*it);
      auto tmp = it;
      it++;
      source_flow.erase(tmp);
    } else {
      it++;
    }
  }
}

template<class T1, class T2>
void Node<T1, T2>::enlarge(uint32_t length) {
	if (length <= this->length) {
		return;
	}
	if (this->match)
		this->match->enlarge(length);
	if (this->inv_match)
		this->inv_match->enlarge(length);
	for (auto const &next: next_in_pipeline)
        next->pipe_array->enlarge(length);
	for (auto const &prev: prev_in_pipeline)
        prev->pipe_array->enlarge(length);

    for (auto const &flow: source_flow) {
      flow->hs_object->enlarge(length);
      flow->processed_hs->enlarge(length);
    }

    this->length = length;
}

template<class T1, class T2>
void Node<T1, T2>::remove_sink_flow_from_pipe(Pipeline<T1, T2>* /*bck_p*/) {

}

template<class T1, class T2>
int Node<T1, T2>::count_fwd_pipeline() {
  return this->next_in_pipeline.size();
}

template<class T1, class T2>
int Node<T1, T2>::count_bck_pipeline() {
  return this->prev_in_pipeline.size();
}

template<class T1, class T2>
void Node<T1, T2>::count_src_flow(int &inc, int &exc) {
  inc = 0;
  exc = 0;
  for (auto const &flow: source_flow) {
    if (flow->processed_hs) {
      inc += flow->processed_hs->count();
      exc += flow->processed_hs->count_diff();
    }
  }
}

template<class T1, class T2>
bool Node<T1, T2>::should_block_flow(Flow<T1, T2> *f, uint32_t out_port) {
  if (is_input_layer) {
    return f->in_port == out_port;
  } else {
    return (*f->p_flow)->node->should_block_flow(*f->p_flow, out_port);
  }

}

template<class T1, class T2>
void Node<T1, T2>::propagate_src_flow_on_pipes(typename list<Flow<T1, T2> *>::iterator s_flow) {
  T1 *h = nullptr;
  for (auto const &next: next_in_pipeline) {
    if (is_output_layer && should_block_flow(*s_flow, next->local_port))
      continue;
    if (!h) h = new T1(*(*s_flow)->processed_hs);
    h->intersect2(next->pipe_array);

    if (!h->is_empty()) {

#ifdef CHECK_BLACKHOLES
      // TODO: fix blackhole check
      if (h->is_sub((*s_flow)->processed_hs) && ((NetPlumber*)plumber)->blackhole_callback) {
        ((NetPlumber*)plumber)->blackhole_callback(
          (NetPlumber*)plumber,
          *s_flow,
          ((NetPlumber*)plumber)->blackhole_callback_data
        );
      }
#endif

      // create a new flow struct to pass to next node in pipeline
      Flow<T1, T2> *next_flow = (Flow<T1, T2> *)malloc(sizeof *next_flow);
      next_flow->node = (*next->r_pipeline)->node;
      next_flow->hs_object = h;
      next_flow->in_port = (*next->r_pipeline)->local_port;
      next_flow->pipe = next;
      next_flow->p_flow = s_flow;
      next_flow->n_flows = nullptr;
      next_flow->processed_hs = nullptr;
      // request next node to process this flow
      (*next->r_pipeline)->node->process_src_flow(next_flow);
      h = nullptr;
    }
  }
  if (h) delete h;
}

template<class T1, class T2>
void Node<T1, T2>::propagate_src_flows_on_pipe(typename list<Pipeline<T1, T2> *>::iterator pipe) {
  T1 *h = nullptr;
  for (auto it = source_flow.begin(); it != source_flow.end(); it++) {
    if (is_output_layer && should_block_flow(*it,(*pipe)->local_port))
      continue;
    if ((*it)->processed_hs == nullptr) continue;
    if (!h) h = new T1(*(*it)->processed_hs);
    h->intersect2((*pipe)->pipe_array);

    if (!h->is_empty()) {
#ifdef CHECK_BLACKHOLES
      T1 p_arr = T1(this->length);
      p_arr->psunion2(new T2(*(*pipe)->pipe_array));

      // TODO: fix blackhole check
      if (h->is_sub(p_arr) && ((NetPlumber*)plumber)->blackhole_callback) {
        ((NetPlumber*)plumber)->blackhole_callback(
          (NetPlumber*)plumber,
          (*it),
          ((NetPlumber*)plumber)->blackhole_callback_data
        );
      }
#endif

      Flow<T1, T2> *next_flow = (Flow<T1, T2> *)malloc(sizeof *next_flow);
      next_flow->node = (*(*pipe)->r_pipeline)->node;
      next_flow->hs_object = h;
      next_flow->in_port = (*(*pipe)->r_pipeline)->local_port;
      next_flow->pipe = *pipe;
      next_flow->p_flow = it;
      next_flow->n_flows = nullptr;
      next_flow->processed_hs = nullptr;
      (*(*pipe)->r_pipeline)->node->process_src_flow(next_flow);
      h = nullptr;
#ifdef CHECK_BLACKHOLES
      delete p_arr;
#endif
    }
  }
  if (h) free(h);
}

template<class T1, class T2>
void Node<T1, T2>::repropagate_src_flow_on_pipes(typename list<Flow<T1, T2> *>::iterator s_flow,
    T2 *change) {

  set<Pipeline<T1, T2> *> pipe_hash_set;
  T1 *h = nullptr;
  if ((*s_flow)->n_flows) {
    for (auto nit = (*s_flow)->n_flows->begin();
        nit != (*s_flow)->n_flows->end(); /*do nothing */) {
      Flow<T1, T2> *next_flow = **nit;
      if (change && !change->is_empty()) {
        T2 *piped = new T2(*change); //change through pipe
        piped->intersect(next_flow->pipe->pipe_array);
        if (!piped->is_empty()) {
          next_flow->hs_object->diff2(piped);
          next_flow->node->process_src_flow_at_location(*nit, piped);
        }
        delete piped;
        next_flow->node->process_src_flow_at_location(*nit, change);
        nit++;
      } else {
        pipe_hash_set.insert(next_flow->pipe);
        if (!h) h = new T1(*(*s_flow)->processed_hs);
        h->intersect2(next_flow->pipe->pipe_array);
        if (!h->is_empty()) {
          if (next_flow->hs_object) delete next_flow->hs_object;
          next_flow->hs_object = h;
          next_flow->node->process_src_flow_at_location(*nit, change);
          h = nullptr;
          nit++;
        } else { // then this flow no longer propagate on this path. absorb it.
          next_flow->node->absorb_src_flow(*nit, false);
          auto tmp_nit = nit;
          nit++;
          (*s_flow)->n_flows->erase(tmp_nit);
        }
      }
    }
  }
  if (change && !change->is_empty()) return;

  for (auto const &next: next_in_pipeline) {
    if (pipe_hash_set.count(next) > 0) continue;  //skip pipes visited above.
    if (is_output_layer && should_block_flow(*s_flow, next->local_port))
      continue;
    if (!h) h = new T1(*(*s_flow)->processed_hs);
    h->intersect2(next->pipe_array);
    if (!h->is_empty()) {
      // create a new flow struct to pass to next node in pipeline
      Flow<T1, T2> *next_flow = (Flow<T1, T2> *)malloc(sizeof *next_flow);
      next_flow->node = (*next->r_pipeline)->node;
      next_flow->hs_object = h;
      next_flow->in_port = (*next->r_pipeline)->local_port;
      next_flow->pipe = next;
      next_flow->p_flow = s_flow;
      next_flow->n_flows = nullptr;
      // request next node to process this flow
      (*next->r_pipeline)->node->process_src_flow(next_flow);
      h = nullptr;
    }
  }
  if (h) delete h;
}

template<class T1, class T2>
void Node<T1, T2>::absorb_src_flow(typename list<Flow<T1, T2> *>::iterator s_flow, bool first) {
  if ((*s_flow)->n_flows) {
    for (auto const &flow: *(*s_flow)->n_flows) {
      (*flow)->node->absorb_src_flow(flow, false);
    }
    delete (*s_flow)->n_flows;
    (*s_flow)->n_flows = nullptr;
  }
  if (!first) {
    delete (*s_flow)->hs_object;
    if ((*s_flow)->processed_hs) delete (*s_flow)->processed_hs;
    free(*s_flow);
    this->source_flow.erase(s_flow);
  }
}

template class Node<HeaderspacePacketSet, ArrayPacketSet>;
