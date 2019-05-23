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
extern "C" {
  #include "../headerspace/hs.h"
#include "../headerspace/array.h"
}
#include <set>

//#ifdef PIPE_SLICING
#include "net_plumber.h"
using namespace net_plumber;
//#endif

using namespace std;


bool is_flow_looped(Flow *flow) {
  Flow *f = flow;
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

Node::Node(void *p, int l, uint64_t n) :
    node_type(BASE), node_id(n), length(l), plumber(p),
    match(nullptr), inv_match(nullptr),
    is_input_layer(false), is_output_layer(false)
{
  //do nothing
}

void Node::remove_flows() {
  for (auto f_it = source_flow.begin(); f_it != source_flow.end(); f_it++) {
    hs_free((*f_it)->hs_object);
    if ((*f_it)->processed_hs) hs_free((*f_it)->processed_hs);
    this->absorb_src_flow(f_it,true);
    if ((*f_it)->p_flow != this->source_flow.end()) {
      (*(*f_it)->p_flow)->n_flows->remove(f_it);
    }
    free(*f_it);
  }
  source_flow.clear();
}

void Node::remove_pipes() {
  for (auto &next: this->next_in_pipeline) {
    auto r = next->r_pipeline;
    array_free(next->pipe_array);
    Node* other_n = (*r)->node;
    free(*r);
    other_n->prev_in_pipeline.erase(r);
    auto r_pipeline = next->r_pipeline;
    array_free((*r_pipeline)->pipe_array);
    other_n->prev_in_pipeline.erase(r_pipeline);
#ifdef PIPE_SLICING
    ((NetPlumber *)plumber)->remove_pipe_from_slices(next);
#endif
    free(next);
  }
  next_in_pipeline.clear();
  for (auto &prev: this->prev_in_pipeline) {
    auto r = prev->r_pipeline;
    array_free(prev->pipe_array);
    Node* other_n = (*r)->node;
    free(*r);
    other_n->next_in_pipeline.erase(r);
    auto r_pipeline = prev->r_pipeline;
    array_free((*r_pipeline)->pipe_array);
    other_n->next_in_pipeline.erase(r_pipeline);
    free(prev);
  }
  prev_in_pipeline.clear();
}

Node::~Node() {
  this->remove_flows();
  this->remove_pipes();
  if (!input_ports.shared) free(input_ports.list);
  if (!output_ports.shared) free(output_ports.list);
  array_free(this->match);
  array_free(this->inv_match);
}

NODE_TYPE Node::get_type() {
  return this->node_type;
}

list<struct Pipeline*>::iterator Node::add_fwd_pipeline(Pipeline *p) {
  this->next_in_pipeline.push_front(p);
  return this->next_in_pipeline.begin();
}

list<struct Pipeline*>::iterator Node::add_bck_pipeline(Pipeline *p) {
  this->prev_in_pipeline.push_front(p);
  return this->prev_in_pipeline.begin();
}

string Node::pipeline_to_string() {
  stringstream result;
  char buf[70];
  char *s;
  result << "Pipelined TO:\n";
  for (auto const &next: next_in_pipeline) {
    auto r = next->r_pipeline;
    sprintf(buf, "0x%lx", (*r)->node->node_id);
    s = array_to_str(next->pipe_array, length, false);
    result << "\tNode " << buf << " Pipe HS: " << s << " [" <<
        next->local_port << "-->" << (*r)->local_port << "]\n";
    free(s);
  }
  result << "Pipelined FROM:\n";
  for (auto const &prev: prev_in_pipeline) {
    auto r = prev->r_pipeline;
    sprintf(buf, "0x%lx", (*r)->node->node_id);
    s = array_to_str(prev->pipe_array, length, false);
    result << "\tNode " << buf << " Pipe HS: " << s << " [" << (*r)->local_port
        << "-->" << prev->local_port << "]\n";
    free(s);
  }
  return result.str();
}

string Node::src_flow_to_string() {
  stringstream result;
  result << "Source Flow:\n";
  char *s;
  for (auto const &flow: source_flow) {
    s = hs_to_str(flow->hs_object);
    result << "\tHS: " <<  s << " --> ";
    free(s);
    if (flow->processed_hs) {
      s = hs_to_str((flow)->processed_hs);
      result << s;
      free(s);
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

void Node::remove_link_pipes(uint32_t local_port,uint32_t remote_port) {
  for (auto it = next_in_pipeline.begin(); it != next_in_pipeline.end(); ) {
    auto r = (*it)->r_pipeline;
    if ((*it)->local_port == local_port && (*r)->local_port == remote_port) {
      (*r)->node->remove_src_flows_from_pipe(*it);
      (*it)->node->remove_sink_flow_from_pipe(*r);
      array_free((*it)->pipe_array);
      auto tmp = r;
      struct Pipeline *pipe = *r;
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

void Node::remove_src_flows_from_pipe(Pipeline *fwd_p) {
  for (auto it = source_flow.begin(); it != source_flow.end(); /*none*/) {
    if ((*it)->pipe == fwd_p) {
      this->absorb_src_flow(it,true);
      (*(*it)->p_flow)->n_flows->remove(it);
      if ((*it)->processed_hs) hs_free((*it)->processed_hs);
      hs_free((*it)->hs_object);
      free(*it);
      auto tmp = it;
      it++;
      source_flow.erase(tmp);
    } else {
      it++;
    }
  }
}

void Node::enlarge(uint32_t length) {
	if (length <= this->length) {
		return;
	}
	if (this->match)
		this->match = array_resize(this->match,this->length, length);
	if (this->inv_match)
		this->inv_match = array_resize(this->inv_match,this->length, length);
	for (auto const &next: next_in_pipeline) {
		if (length > next->len) {
            next->pipe_array = array_resize(next->pipe_array,this->length,length);
            next->len = length;
        }
	}
	for (auto const &prev: prev_in_pipeline) {
        if (length > prev->len) {
            prev->pipe_array = array_resize(prev->pipe_array,this->length,length);
            prev->len = length;
        }
	}
	for (auto const &flow: source_flow) {
		hs_enlarge(flow->hs_object, length);
		hs_enlarge(flow->processed_hs, length);
	}

	this->length = length;
}

void Node::remove_sink_flow_from_pipe(Pipeline* /*bck_p*/) {

}

int Node::count_fwd_pipeline() {
  return this->next_in_pipeline.size();
}

int Node::count_bck_pipeline() {
  return this->prev_in_pipeline.size();
}

void Node::count_src_flow(int &inc, int &exc) {
  inc = 0;
  exc = 0;
  for (auto const &flow: source_flow) {
    if (flow->processed_hs) {
      inc += hs_count(flow->processed_hs);
      exc += hs_count_diff(flow->processed_hs);
    }
  }
}

bool Node::should_block_flow(Flow *f, uint32_t out_port) {
  if (is_input_layer) {
    return f->in_port == out_port;
  } else {
    return (*f->p_flow)->node->should_block_flow(*f->p_flow, out_port);
  }

}

void Node::propagate_src_flow_on_pipes(list<struct Flow*>::iterator s_flow) {
  hs *h = NULL;
  for (auto const &next: next_in_pipeline) {
    if (is_output_layer && should_block_flow(*s_flow, next->local_port))
      continue;
    if (!h) h = (hs *)malloc(sizeof *h);
    if (hs_isect_arr(h, (*s_flow)->processed_hs, next->pipe_array)) {

      // TODO: fix blackhole check
      if (hs_is_sub(h,(*s_flow)->processed_hs) && ((NetPlumber*)plumber)->blackhole_callback) {
        /*
        ((NetPlumber*)plumber)->blackhole_callback(
          (NetPlumber*)plumber,
          *s_flow,
          ((NetPlumber*)plumber)->blackhole_callback_data
        )
         */;
      }

      // create a new flow struct to pass to next node in pipeline
      Flow *next_flow = (Flow *)malloc(sizeof *next_flow);
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
  if (h) free(h);
}

void Node::propagate_src_flows_on_pipe(list<Pipeline *>::iterator pipe) {
  hs *h = nullptr;
  for (auto it = source_flow.begin(); it != source_flow.end(); it++) {
    if (is_output_layer && should_block_flow(*it,(*pipe)->local_port))
      continue;
    if ((*it)->processed_hs == nullptr) continue;
    if (!h) h = (hs *)malloc(sizeof *h);

    if (hs_isect_arr(h, (*it)->processed_hs, (*pipe)->pipe_array)) {

      struct hs p_arr = {this->length, {0, 0, 0, 0}};
      hs_add(&p_arr,array_copy((*pipe)->pipe_array,this->length));

      // TODO: fix blackhole check
      if (hs_is_sub(h,&p_arr) && ((NetPlumber*)plumber)->blackhole_callback) {
        /*
        ((NetPlumber*)plumber)->blackhole_callback(
          (NetPlumber*)plumber,
          (*it),
          ((NetPlumber*)plumber)->blackhole_callback_data
        )
         */;
      }

      Flow *next_flow = (Flow *)malloc(sizeof *next_flow);
      next_flow->node = (*(*pipe)->r_pipeline)->node;
      next_flow->hs_object = h;
      next_flow->in_port = (*(*pipe)->r_pipeline)->local_port;
      next_flow->pipe = *pipe;
      next_flow->p_flow = it;
      next_flow->n_flows = nullptr;
      next_flow->processed_hs = nullptr;
      (*(*pipe)->r_pipeline)->node->process_src_flow(next_flow);
      h = nullptr;
      hs_destroy(&p_arr);
    }
  }
  if (h) free(h);
}

void Node::repropagate_src_flow_on_pipes(list<struct Flow*>::iterator s_flow,
    array_t *change) {

  set<Pipeline*> pipe_hash_set;
  hs *h = nullptr;
  if ((*s_flow)->n_flows) {
    for (auto nit = (*s_flow)->n_flows->begin();
        nit != (*s_flow)->n_flows->end(); /*do nothing */) {
      Flow *next_flow = **nit;
      if (change) {
        array_t *piped = array_isect_a(  //change through pipe
              change,next_flow->pipe->pipe_array,length);
        if (piped) {
          hs_diff(next_flow->hs_object, piped);
          next_flow->node->process_src_flow_at_location(*nit,piped);
          array_free(piped);
        }
        next_flow->node->process_src_flow_at_location(*nit,change);
        nit++;
      } else {
        pipe_hash_set.insert(next_flow->pipe);
        if (!h) h = (hs *)malloc(sizeof *h);
        if (hs_isect_arr(
            h, (*s_flow)->processed_hs, next_flow->pipe->pipe_array)
            ){  // update the hs_object of next flow and ask it to reprocess it.
          hs_free(next_flow->hs_object);
          next_flow->hs_object = h;
          next_flow->node->process_src_flow_at_location(*nit,change);
          h = nullptr;
          nit++;
        } else { // then this flow no longer propagate on this path. absorb it.
          next_flow->node->absorb_src_flow(*nit,false);
          auto tmp_nit = nit;
          nit++;
          (*s_flow)->n_flows->erase(tmp_nit);
        }
      }
    }
  }
  if (change) return;

  for (auto const &next: next_in_pipeline) {
    if (pipe_hash_set.count(next) > 0) continue;  //skip pipes visited above.
    if (is_output_layer && should_block_flow(*s_flow, next->local_port))
      continue;
    if (!h) h = (hs *)malloc(sizeof *h);
    if (hs_isect_arr(h, (*s_flow)->processed_hs, next->pipe_array)) {
      // create a new flow struct to pass to next node in pipeline
      Flow *next_flow = (Flow *)malloc(sizeof *next_flow);
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
  free(h); // must not be hs_free()! leads to memory corruption
}

void Node::absorb_src_flow(list<struct Flow*>::iterator s_flow, bool first) {
  if ((*s_flow)->n_flows) {
    for (auto const &flow: *(*s_flow)->n_flows) {
      (*flow)->node->absorb_src_flow(flow, false);
    }
    delete (*s_flow)->n_flows;
    (*s_flow)->n_flows = nullptr;
  }
  if (!first) {
    hs_free((*s_flow)->hs_object);
    if ((*s_flow)->processed_hs) hs_free((*s_flow)->processed_hs);
    free(*s_flow);
    this->source_flow.erase(s_flow);
  }
}

