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

#include "node.h"
#include <sstream>
#include <set>
#include "array_packet_set.h"
#include "hs_packet_set.h"
#ifdef USE_BDD
#include "bdd_packet_set.h"
#endif

#include "net_plumber.h"
using namespace net_plumber;

using namespace std;
using namespace log4cxx;

template<class T1, class T2>
LoggerPtr Node<T1, T2>::logger(Logger::getLogger("NetPlumber"));

template<typename T1, typename T2>
bool is_flow_looped(Flow<T1, T2> *flow) {
  Flow<T1, T2> *f = flow;
#ifdef DENSE_LOOPS
  set<uint64_t> seen_rules;
#else
  set<uint64_t> seen_tables;
#endif
  while(1) {
#if DENSE_LOOPS
    uint64_t rule_id = (f->node->node_id);
    if (seen_rules.count(rule_id) == 0) {
      seen_rules.insert(rule_id);
    } else {
      return true;
    }
#else
    uint64_t table_id = (f->node->node_id & 0xffffffff00000000);
    if (seen_tables.count(table_id) == 0) {
      seen_tables.insert(table_id);
    } else {
      return true;
    }
#endif
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
#ifdef GENERIC_PS
    if ((*f_it)->processed_hs) delete (*f_it)->processed_hs;
    delete (*f_it)->hs_object;
#else
    if ((*f_it)->processed_hs) hs_free((*f_it)->processed_hs);
    hs_free((*f_it)->hs_object);
#endif
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
#ifdef GENERIC_PS
    delete (next->pipe_array);
    delete ((*r)->pipe_array);
#else
    array_free(next->pipe_array);
    array_free((*r)->pipe_array);
#endif
    Node* other_n = (*r)->node;
    free(*r);
    other_n->prev_in_pipeline.erase(r);
#ifdef PIPE_SLICING
    ((NetPlumber<T1, T2> *)plumber)->remove_pipe_from_slices(next);
#endif
    free(next);
  }
  next_in_pipeline.clear();
  for (auto &prev: this->prev_in_pipeline) {
    auto r = prev->r_pipeline;
#ifdef GENERIC_PS
    delete (prev->pipe_array);
    delete ((*r)->pipe_array);
#else
    array_free(prev->pipe_array);
    array_free((*r)->pipe_array);
#endif
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
#ifdef GENERIC_PS
    delete this->inv_match;
#else
    array_free(this->inv_match);
#endif
  }
#ifdef GENERIC_PS
  delete this->match;
#else
  array_free(this->match);
#endif
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
#ifdef GENERIC_PS
    result << " Pipe HS: " << next->pipe_array->to_str();
#else
    result << " Pipe HS: " << array_to_str(next->pipe_array, this->length, false);
#endif
    result << " [" << next->local_port << "-->" << (*next->r_pipeline)->local_port << "]\n";
  }
  result << "Pipelined FROM:\n";
  for (auto const &prev: prev_in_pipeline) {
    result << "\tNode 0x" << std::hex << (*prev->r_pipeline)->node->node_id;
#ifdef GENERIC_PS
    result << " Pipe HS: " << prev->pipe_array->to_str();
#else
    result << " Pipe HS: " << array_to_str(prev->pipe_array, this->length, false);
#endif
    result << " [" << ((*prev->r_pipeline))->local_port << "-->" << prev->local_port << "]\n";
  }
  return result.str();
}

template<class T1, class T2>
string Node<T1, T2>::src_flow_to_string() {
  stringstream result;
  result << "Source Flow:\n";
  for (auto const &flow: source_flow) {
#ifdef GENERIC_PS
    result << "\tHS: " <<  flow->hs_object->to_str() << " --> ";
    if (flow->processed_hs) {
      result << (flow)->processed_hs->to_str();
#else
    result << "\tHS: " <<  hs_to_str(flow->hs_object) << " --> ";
    if (flow->processed_hs) {
      result << hs_to_str((flow)->processed_hs);
#endif
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
#ifdef GENERIC_PS
      delete (*it)->pipe_array;
#else
      array_free((*it)->pipe_array);
#endif
      auto tmp = r;
      struct Pipeline<T1, T2> *pipe = *r;
#ifdef GENERIC_PS
      delete pipe->pipe_array;
#else
      array_free(pipe->pipe_array);
#endif
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
#ifdef GENERIC_PS
      if ((*it)->processed_hs) delete (*it)->processed_hs;
      delete (*it)->hs_object;
#else
      if ((*it)->processed_hs) hs_free((*it)->processed_hs);
      hs_free((*it)->hs_object);
#endif
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
    const bool tracing = this->logger->isTraceEnabled();
    const bool debug = this->logger->isDebugEnabled();
    if (tracing) {
      stringstream enl;
      enl << "Node::enlarge(): id 0x" << std::hex << this->node_id;
      enl << " enlarge from " << std::dec << this->length << " to " << length;
      LOG4CXX_TRACE(this->logger, enl.str());
    }
    if (length <= this->length) {
        return;
    }
#ifdef GENERIC_PS
    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): enlarge match");
    if (this->match)
        this->match->enlarge(length);
    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): enlarge inverse match");
    if (this->inv_match)
        this->inv_match->enlarge(length);
    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): enlarge outgoing pipelines");
    for (auto const &next: next_in_pipeline)
        next->pipe_array->enlarge(length);
    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): enlarge incoming pipelines");
    for (auto const &prev: prev_in_pipeline)
        prev->pipe_array->enlarge(length);

    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): enlarge flows");
    for (auto const &flow: source_flow) {
      if (flow->hs_object) flow->hs_object->enlarge(length);
      if (flow->processed_hs) flow->processed_hs->enlarge(length);
    }
#else
    const size_t olen = this->length;
    T2 *tmp;
    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): enlarge match");
    if (this->match) {
        tmp = array_resize(this->match, olen, length);
        this->match = tmp;
    }
    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): enlarge inverse match");
    if (this->inv_match) {
        tmp = array_resize(this->inv_match, olen, length);
        this->inv_match = tmp;
    }
    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): enlarge outgoing pipelines");
    for (auto const &next: next_in_pipeline) {
        tmp = array_resize(next->pipe_array, olen, length);
        next->pipe_array = tmp;
    }
    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): enlarge incoming pipelines");
    for (auto const &prev: prev_in_pipeline) {
        tmp = array_resize(prev->pipe_array, olen, length);
        prev->pipe_array = tmp;
    }

    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): enlarge flows");
    for (auto const &flow: source_flow) {
      if (flow->hs_object) hs_enlarge(flow->hs_object, length);
      if (flow->processed_hs) hs_enlarge(flow->processed_hs, length);
    }
#endif

    if (tracing) LOG4CXX_TRACE(this->logger, "Node::enlarge(): persist length");
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
#ifdef GENERIC_PS
      inc += flow->processed_hs->count();
      exc += flow->processed_hs->count_diff();
#else
      inc += hs_count(flow->processed_hs);
      exc += hs_count_diff(flow->processed_hs);
#endif
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
  const bool tracing = this->logger->isTraceEnabled();

  T1 h;
#ifdef GENERIC_PS
  h.hs.len = this->length;
#else
  h.len = this->length;
#endif

  for (auto const &next: next_in_pipeline) {
    if (is_output_layer && should_block_flow(*s_flow, next->local_port))
      continue;

#ifdef GENERIC_PS
//    h = T1((*s_flow)->processed_hs, next->pipe_array);
//    const bool has_isect = !h.is_empty();
    const bool has_isect = hs_isect_arr(&h.hs, &(*s_flow)->processed_hs->hs, next->pipe_array->array); // XXX
#else
    const bool has_isect = hs_isect_arr(&h, (*s_flow)->processed_hs, next->pipe_array);
#endif

    if (tracing) {
      stringstream isect;
      isect << "Node::propagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
//      isect << " with " << h->to_str();
#ifdef GENERIC_PS
      isect << " with " << h.to_str();
      isect << " after intersecting " << (*s_flow)->processed_hs->to_str();
      isect << " with " << next->pipe_array->to_str();
#else
      char *tmp = hs_to_str(&h);
      isect << " with " << std::string(tmp);
      free(tmp); tmp = hs_to_str((*s_flow)->processed_hs);
      isect << " after intersecting " << std::string(tmp);
      free(tmp); tmp = array_to_str(next->pipe_array, this->length, false);
      isect << " with " << std::string(tmp);
      free(tmp);
#endif
      LOG4CXX_TRACE(this->logger, isect.str());
    }

    if (has_isect) {

#ifdef CHECK_BLACKHOLES
      // TODO: fix blackhole check, also for non-ps data types
      if (h->is_subset((*s_flow)->processed_hs) && ((NetPlumber<T1, T2>*)plumber)->blackhole_callback) {
        ((NetPlumber<T1, T2>*)plumber)->blackhole_callback(
          (NetPlumber<T1, T2>*)plumber,
          *s_flow,
          ((NetPlumber<T1, T2>*)plumber)->blackhole_callback_data
        );
      }
#endif

      if (tracing) {
        stringstream cont;
        cont << "Node::propagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
        cont << " not empty -> create new flow item and propagate on pipe";
        LOG4CXX_TRACE(this->logger, cont.str());
      }

      // create a new flow struct to pass to next node in pipeline
      Flow<T1, T2> *next_flow = (Flow<T1, T2> *)malloc(sizeof *next_flow);
      next_flow->node = (*next->r_pipeline)->node;
      next_flow->source = (*s_flow)->source;
#ifdef GENERIC_PS
      next_flow->hs_object = new T1(h.hs.len);
      next_flow->hs_object->hs = h.hs;
      h.hs.list = {0, 0, 0, 0};
#else
      next_flow->hs_object = hs_create(this->length);
      next_flow->hs_object->list = h.list;
      h.list = {0, 0, 0, 0};
#endif
      next_flow->in_port = (*next->r_pipeline)->local_port;
      next_flow->pipe = next;
      next_flow->p_flow = s_flow;
      next_flow->n_flows = nullptr;
      next_flow->processed_hs = nullptr;
      // request next node to process this flow
      (*next->r_pipeline)->node->process_src_flow(next_flow);
    } else {
      if (tracing) {
        stringstream cont;
        cont << "Node::propagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
        cont << " empty -> skip pipe";
        LOG4CXX_TRACE(this->logger, cont.str());
      }
    }
  }
}

template<class T1, class T2>
void Node<T1, T2>::propagate_src_flows_on_pipe(typename list<Pipeline<T1, T2> *>::iterator pipe) {
  const bool tracing = this->logger->isTraceEnabled();

  T1 h;
#ifdef GENERIC_PS
  h.hs.len = this->length;
#else
  h.len = this->length;
#endif

  for (auto it = source_flow.begin(); it != source_flow.end(); it++) {
    if (is_output_layer && should_block_flow(*it,(*pipe)->local_port))
      continue;
    if ((*it)->processed_hs == nullptr) continue;

#ifdef GENERIC_PS
//    h = T1((*it)->processed_hs, (*pipe)->pipe_array);
//    const bool has_isect = !h.is_empty();
    const bool has_isect = hs_isect_arr(&h.hs, &(*it)->processed_hs->hs, (*pipe)->pipe_array->array); // XXX
#else
    const bool has_isect = hs_isect_arr(&h, (*it)->processed_hs, (*pipe)->pipe_array);
#endif

    if (tracing) {
      stringstream isect;
      isect << "Node::propagate_src_flows_on_pipe(): id 0x" << std::hex << this->node_id;
//      isect << " with " << h->to_str();
#ifdef GENERIC_PS
      isect << " with " << h.to_str();
      isect << " after intersecting " << (*it)->processed_hs->to_str();
      isect << " with " << (*pipe)->pipe_array->to_str();
#else
      char *tmp = hs_to_str(&h);
      isect << " with " << std::string(tmp);
      free(tmp); tmp = hs_to_str((*it)->processed_hs);
      isect << " after intersecting " << std::string(tmp);
      free(tmp); tmp = array_to_str((*pipe)->pipe_array, this->length, false);
      isect << " with " << std::string(tmp);
      free(tmp);
#endif
      LOG4CXX_TRACE(this->logger, isect.str());
    }

    if (has_isect) {

#ifdef CHECK_BLACKHOLES
      T1 p_arr = T1(this->length);
      p_arr.psunion2((*pipe)->pipe_array);

      // TODO: fix blackhole check, also for non-ps data types
      if (h->is_subset(&p_arr) && ((NetPlumber<T1, T2>*)plumber)->blackhole_callback) {
        ((NetPlumber<T1, T2>*)plumber)->blackhole_callback(
          (NetPlumber<T1, T2>*)plumber,
          (*it),
          ((NetPlumber<T1, T2>*)plumber)->blackhole_callback_data
        );
      }
#endif

      if (tracing) {
        stringstream cont;
        cont << "Node::propagate_src_flows_on_pipe(): id 0x" << std::hex << this->node_id;
        cont << " not empty -> create new flow item and propagate on pipe";
        LOG4CXX_TRACE(this->logger, cont.str());
      }

      Flow<T1, T2> *next_flow = (Flow<T1, T2> *)malloc(sizeof *next_flow);
      next_flow->node = (*(*pipe)->r_pipeline)->node;
      next_flow->source = (*it)->source;
#ifdef GENERIC_PS
      next_flow->hs_object = new T1(h.hs.len);
      next_flow->hs_object->hs = h.hs;
      h.hs.list = {0, 0, 0, 0};
#else
      next_flow->hs_object = hs_create(this->length);
      next_flow->hs_object->list = h.list;
      h.list = {0, 0, 0, 0};
#endif
      next_flow->in_port = (*(*pipe)->r_pipeline)->local_port;
      next_flow->pipe = *pipe;
      next_flow->p_flow = it;
      next_flow->n_flows = nullptr;
      next_flow->processed_hs = nullptr;
      (*(*pipe)->r_pipeline)->node->process_src_flow(next_flow);
    } else {

      if (tracing) {
        stringstream cont;
        cont << "Node::propagate_src_flows_on_pipe(): id 0x" << std::hex << this->node_id;
        cont << " empty -> skip flow";
        LOG4CXX_TRACE(this->logger, cont.str());
      }
    }
  }
}

template<class T1, class T2>
void Node<T1, T2>::repropagate_src_flow_on_pipes(typename list<Flow<T1, T2> *>::iterator s_flow,
    T2 *change) {
  const bool tracing = this->logger->isTraceEnabled();

  set<Pipeline<T1, T2> *> pipe_hash_set;
  T1 h;
#ifdef GENERIC_PS
  h.hs.len = this->length;
#else
  h.len = this->length;
#endif
  if ((*s_flow)->n_flows) {
    for (auto nit = (*s_flow)->n_flows->begin();
        nit != (*s_flow)->n_flows->end(); /*do nothing */) {
      Flow<T1, T2> *next_flow = **nit;
#ifdef GENERIC_PS
      if (change && !change->is_empty()) { // non-empty change
//        T2 *piped = new T2(*change);
//        piped->intersect(next_flow->pipe->pipe_array);
        T2 piped = T2(this->length, BIT_X);
//        piped.intersect(next_flow->pipe->pipe_array);  //change through pipe
        const bool has_isect = array_isect(next_flow->pipe->pipe_array->array, change->array, this->length, piped.array); // XXX
#else
      if (change) { // non-empty change
        T2 piped[ARRAY_BYTES (this->length) / sizeof (array_t)];
        const bool has_isect = array_isect(next_flow->pipe->pipe_array, change, this->length, piped);
#endif

        if (tracing) {
          stringstream isect;
          isect << "Node::repropagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
//          isect << " with " << piped->to_str();
#ifdef GENERIC_PS
          isect << " with " << piped.to_str();
          isect << " after intersecting " << change->to_str();
          isect << " with " << next_flow->pipe->pipe_array->to_str();
#else
          char *tmp = array_to_str(piped, this->length, false);
          isect << " with " << std::string(tmp);
          free(tmp); tmp = array_to_str(change, this->length, false);
          isect << " after intersecting " << std::string(tmp);
          free(tmp); tmp = array_to_str(next_flow->pipe->pipe_array, this->length, false);
          isect << " with " << std::string(tmp);
          free(tmp);
#endif
          LOG4CXX_TRACE(this->logger, isect.str());
        }

//        if (!piped->is_empty()) {
        if (has_isect) {
#ifdef GENERIC_PS
//          next_flow->hs_object->diff2(piped);
          hs_diff(&next_flow->hs_object->hs, piped.array); // XXX
#else
          hs_diff(next_flow->hs_object, piped);
#endif
          if (tracing) {
            stringstream diff;
            diff << "Node::repropagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
            diff << " with next flow " << next_flow->hs_object->to_str();
//            diff << " after diffing " << piped->to_str();
            diff << " after diffing " << piped.to_str();
#else
            char *tmp = hs_to_str(next_flow->hs_object);
            diff << " with next flow " << std::string(tmp);
            free(tmp); tmp = array_to_str(piped, this->length, false);
            diff << " after diffing " << std::string(tmp);
            free(tmp);
#endif
            diff << " from incoming hs.";
            LOG4CXX_TRACE(this->logger, diff.str());
          }

#ifdef GENERIC_PS
          next_flow->node->process_src_flow_at_location(*nit, &piped); // XXX: why does this work without breaking?
#else
          next_flow->node->process_src_flow_at_location(*nit, piped);
#endif
        }
//        delete piped;
        next_flow->node->process_src_flow_at_location(*nit, change);
        nit++;
      } else { // empty change
        pipe_hash_set.insert(next_flow->pipe);
#ifdef GENERIC_PS
//        h = T1(*(*s_flow)->processed_hs, next_flow->pipe->pipe_array);
//        const bool has_isect = !h.is_empty();
        const bool has_isect = hs_isect_arr(&h.hs, &(*s_flow)->processed_hs->hs, next_flow->pipe->pipe_array->array); // XXX
#else
        const bool has_isect = hs_isect_arr(&h, (*s_flow)->processed_hs, next_flow->pipe->pipe_array);
#endif

        if (tracing) {
          stringstream isect;
          isect << "Node::repropagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
//          isect << " with " << h->to_str();
          isect << " with " << h.to_str();
          isect << " after intersecting " << (*s_flow)->processed_hs->to_str();
          isect << " with " << next_flow->pipe->pipe_array->to_str();
#else
          char *tmp = hs_to_str(&h);
          isect << " with " << std::string(tmp);
          free(tmp); tmp = hs_to_str((*s_flow)->processed_hs);
          isect << " after intersecting " << std::string(tmp);
          free(tmp); tmp = array_to_str(next_flow->pipe->pipe_array, this->length, false);
          isect << " with " << std::string(tmp);
          free(tmp);
#endif
          LOG4CXX_TRACE(this->logger, isect.str());
        }

        if (has_isect) {
          if (tracing) {
            stringstream cont;
            cont << "Node::repropagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
            cont << " not empty -> update hs_object and trigger processing.";
            LOG4CXX_TRACE(this->logger, cont.str());
          }

#ifdef GENERIC_PS
          if (next_flow->hs_object) hs_destroy(&next_flow->hs_object->hs);
          next_flow->hs_object->hs.list = h.hs.list;
          h.hs.list = {0, 0, 0, 0};
#else
          if (next_flow->hs_object) hs_destroy(next_flow->hs_object);
          next_flow->hs_object->list = h.list;
          h.list = {0, 0, 0, 0};
#endif
          next_flow->node->process_src_flow_at_location(*nit, change);
          nit++;
        } else { // then this flow no longer propagate on this path. absorb it.

          if (tracing) {
            stringstream cont;
            cont << "Node::repropagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
            cont << " empty -> stop propagation of this flow on this path by absorbing it.";
            LOG4CXX_TRACE(this->logger, cont.str());
          }

          next_flow->node->absorb_src_flow(*nit, false);
          auto tmp_nit = nit;
          nit++;
          (*s_flow)->n_flows->erase(tmp_nit);
        }
      }
    }
  }

#ifdef GENERIC_PS
  if (change && !change->is_empty()) {
#else
  if (change) {
#endif
    if (tracing) {
      stringstream cont;
      cont << "Node::repropagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
      cont << " stop propagation update as nothing changed.";
      LOG4CXX_TRACE(this->logger, cont.str());
    }
    return;
  }

  for (auto const &next: next_in_pipeline) {
    if (pipe_hash_set.count(next) > 0) continue;  //skip pipes visited above.
    if (is_output_layer && should_block_flow(*s_flow, next->local_port))
      continue;
#ifdef GENERIC_PS
//    h = T1(*(*s_flow)->processed_hs, next->pipe_array);
//    const bool has_isect = !h.is_empty();
    const bool has_isect = hs_isect_arr(&h.hs, &(*s_flow)->processed_hs->hs, next->pipe_array->array); // XXX
#else
    const bool has_isect = hs_isect_arr(&h, (*s_flow)->processed_hs, next->pipe_array);
#endif

    if (tracing) {
      stringstream isect;
      isect << "Node::repropagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
//      isect << " with " << h->to_str();
#ifdef GENERIC_PS
      isect << " with " << h.to_str();
      isect << " after intersecting " << (*s_flow)->processed_hs->to_str();
      isect << " with " << next->pipe_array->to_str();
#else
      char *tmp = hs_to_str(&h);
      isect << " with " << std::string(tmp);
      free(tmp); tmp = hs_to_str((*s_flow)->processed_hs);
      isect << " after intersecting " << std::string(tmp);
      free(tmp); tmp = array_to_str(next->pipe_array, this->length, false);
      isect << " with " << std::string(tmp);
      free(tmp);
#endif
      LOG4CXX_TRACE(this->logger, isect.str());
    }

    if (has_isect) {
      if (tracing) {
        stringstream cont;
        cont << "Node::repropagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
        cont << " not empty -> create new flow item and process on pipeline.";
        LOG4CXX_TRACE(this->logger, cont.str());
      }

      // create a new flow struct to pass to next node in pipeline
      Flow<T1, T2> *next_flow = (Flow<T1, T2> *)malloc(sizeof *next_flow);
      next_flow->node = (*next->r_pipeline)->node;
      next_flow->source = (*s_flow)->source;
#ifdef GENERIC_PS
      next_flow->hs_object = new T1(this->length);
      next_flow->hs_object->hs.list = h.hs.list;
      h.hs.list = {0, 0, 0, 0};
#else
      next_flow->hs_object = hs_create(this->length);
      next_flow->hs_object->list = h.list;
      h.list = {0, 0, 0, 0};
#endif
      next_flow->in_port = (*next->r_pipeline)->local_port;
      next_flow->pipe = next;
      next_flow->p_flow = s_flow;
      next_flow->n_flows = nullptr;
      // request next node to process this flow
      (*next->r_pipeline)->node->process_src_flow(next_flow);
    } else {

        if (tracing) {
          stringstream cont;
          cont << "Node::repropagate_src_flow_on_pipes(): id 0x" << std::hex << this->node_id;
          cont << " empty -> stop propagation on this pipe.";
          LOG4CXX_TRACE(this->logger, cont.str());
        }
    }
  }
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
#ifdef GENERIC_PS
    delete (*s_flow)->hs_object;
    if ((*s_flow)->processed_hs) delete (*s_flow)->processed_hs;
#else
    hs_free((*s_flow)->hs_object);
    if ((*s_flow)->processed_hs) hs_free((*s_flow)->processed_hs);
#endif
    free(*s_flow);
    this->source_flow.erase(s_flow);
  }
}

#ifdef GENERIC_PS
template class Node <HeaderspacePacketSet, ArrayPacketSet>;
#ifdef USE_BDD
template class Node <BDDPacketSet, BDDPacketSet>;
#endif
#else
template class Node <hs, array_t>;
#endif
