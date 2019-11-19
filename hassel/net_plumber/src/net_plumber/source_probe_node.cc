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

#include "source_probe_node.h"
#include "net_plumber_utils.h"
#include <sstream>
#include <string>
#include "net_plumber.h"
#include <assert.h>

using namespace std;
using namespace log4cxx;
using namespace net_plumber;

LoggerPtr probe_def_logger(Logger::getLogger("DefaultProbeLogger"));

string probe_transition(PROBE_TRANSITION t) {
  switch (t) {
  case UNKNOWN: return "Unknown";
  case STARTED_FALSE: return "Started in False State";
  case STARTED_TRUE: return "Started in True State";
  case TRUE_TO_FALSE: return "Failed Probe Condition";
  case FALSE_TO_TRUE: return "Met Probe Condition";
  case MORE_FALSE: return "More Flows Failed Probe Condition";
  case LESS_FALSE: return "Fewer Flows Failed Probe Condition";
  case MORE_TRUE: return "More Flows Met Probe Condition";
  case LESS_TRUE: return "Fewer Flows Met Probe Condition";
  default: return "Undefined";
  }
}

template<typename T1, typename T2>
void default_probe_callback(void *caller, SourceProbeNode<T1, T2> *p, Flow<T1, T2>* /*f*/,void* /*data*/,
                            PROBE_TRANSITION t) {
  NetPlumber<T1, T2> *N = (NetPlumber<T1, T2> *)caller;
  Event e = N->get_last_event();
  stringstream error_msg;
  if (p->get_mode() == EXISTENTIAL) error_msg << "Existential ";
  else error_msg << "Universal ";
  error_msg << "Probe " << p->node_id << " Activated after event " <<
      get_event_name(e.type) << ": " << probe_transition(t);
  LOG4CXX_WARN(probe_def_logger,error_msg.str());
}

template<class T1, class T2>
SourceProbeNode<T1, T2>::SourceProbeNode(void *n, int length, uint64_t node_id,
                                 PROBE_MODE mode, List_t ports,
                                 Condition<T1, T2> *filter, Condition<T1, T2> *test,
                                 src_probe_callback_t<T1, T2> probe_callback, void* d)
: Node<T1, T2>(n,length,node_id), state(STOPPED), mode(mode),
  filter(filter), test(test), cond_count(0), probe_callback_data(d)
{
  this->node_type = SOURCE_PROBE;
  this->match = array_create(length, BIT_X);
  this->inv_match = nullptr;
  this->input_ports = ports;
  this->output_ports = make_sorted_list(0);
  if (probe_callback) this->probe_callback = probe_callback;
  else this->probe_callback = default_probe_callback;
}

template<class T1, class T2>
SourceProbeNode<T1, T2>::~SourceProbeNode() {
  delete test;
  delete filter;
}

template<class T1, class T2>
void SourceProbeNode<T1, T2>::process_src_flow(Flow<T1, T2> *f) {
  if (f) {
    this->source_flow.push_front(f);
    auto f_it = this->source_flow.begin();
    (*f->p_flow)->n_flows->push_front(f_it);
    f->processed_hs = hs_copy_a(f->hs_object);
    // XXX: deactivate due to possible memory explosion when having meaningful diffs in flow
    //hs_comp_diff(f->processed_hs);
    if (state == RUNNING) update_check(f,FLOW_ADD);
  } else {
    for (auto const &prev: this->prev_in_pipeline) {
      (*prev->r_pipeline)->node->propagate_src_flows_on_pipe(prev->r_pipeline);
    }
  }
}

template<class T1, class T2>
void SourceProbeNode<T1, T2>::process_src_flow_at_location(
     typename list< Flow<T1, T2> *>::iterator loc, T2* change) {
  Flow<T1, T2> *f = *loc;
  if (change) {
    if (f->processed_hs->list.used == 0) return;
    hs_diff(f->processed_hs, change);
  } else {
    hs_free(f->processed_hs);
    f->processed_hs = hs_copy_a(f->hs_object);
    // XXX: deactivate due to possible memory explosion when having meaningful diffs in flow
    //hs_comp_diff(f->processed_hs);
  }
  if (state == RUNNING) update_check(f,FLOW_MODIFY);
}

template<class T1, class T2>
void SourceProbeNode<T1, T2>::absorb_src_flow(typename list< Flow<T1, T2> *>::iterator s_flow,
    bool first) {
  if (state == RUNNING) update_check(*s_flow,FLOW_DELETE);
  Node<T1, T2>::absorb_src_flow(s_flow, first);
}

template<class T1, class T2>
void SourceProbeNode<T1, T2>::update_check(Flow<T1, T2> *f, PROBE_FLOW_ACTION action) {
  /*
   * 0: add
   * 1: modified
   * 2: deleted
   */
  assert(cond_count >= 0);
  // if flow is empty, do nothing
  if (f->processed_hs->list.used == 0) return;

  // Delete flow
  if (action == FLOW_DELETE) {
    if (check_results.count(f) > 0) {
      if (mode == EXISTENTIAL && check_results[f]) {
        cond_count--;
        if (cond_count == 0) {
          probe_callback(this->plumber,this,f,probe_callback_data,TRUE_TO_FALSE);
        } else {
          probe_callback(this->plumber,this,f,probe_callback_data,LESS_TRUE);
        }
      } else if (mode == UNIVERSAL && !check_results[f]) {
        cond_count--;
        if (cond_count == 0) {
          probe_callback(this->plumber,this,f,probe_callback_data,FALSE_TO_TRUE);
        } else {
          probe_callback(this->plumber,this,f,probe_callback_data,LESS_FALSE);
        }
      }
      check_results.erase(f);
    }
    return;
  }

  bool m = filter->check(f);

  // Newly added flow
  if ((action == FLOW_ADD && m) |
      (action == FLOW_MODIFY && m && check_results.count(f) == 0)) {
    bool c = test->check(f);
    check_results[f] = c;
    if (mode == EXISTENTIAL && c) {
      cond_count++;
      if (cond_count == 1) {
        probe_callback(this->plumber,this,f,probe_callback_data,FALSE_TO_TRUE);
      } else {
        probe_callback(this->plumber,this,f,probe_callback_data,MORE_TRUE);
      }
    } else if (mode == UNIVERSAL && !c) {
      cond_count++;
      if (cond_count == 1) {
        probe_callback(this->plumber,this,f,probe_callback_data,TRUE_TO_FALSE);
      } else {
        probe_callback(this->plumber,this,f,probe_callback_data,MORE_FALSE);
      }
    }
  }

  // Updated flow
  else if (action == FLOW_MODIFY && m) {
    bool c = test->check(f);
    if (check_results[f] == c) return;
    check_results[f] = c;
    if (mode == EXISTENTIAL && c) {
      cond_count++;
      if (cond_count == 1) {
        probe_callback(this->plumber,this,f,probe_callback_data,FALSE_TO_TRUE);
      } else {
        probe_callback(this->plumber,this,f,probe_callback_data,MORE_TRUE);
      }
    } else if (mode == EXISTENTIAL && !c) {
      cond_count--;
      if (cond_count == 0) {
        probe_callback(this->plumber,this,f,probe_callback_data,TRUE_TO_FALSE);
      } else {
        probe_callback(this->plumber,this,f,probe_callback_data,LESS_TRUE);
      }
    } else if (mode == UNIVERSAL && !c) {
      cond_count++;
      if (cond_count == 1) {
        probe_callback(this->plumber,this,f,probe_callback_data,TRUE_TO_FALSE);
      } else {
        probe_callback(this->plumber,this,f,probe_callback_data,MORE_FALSE);
      }
    } else if (mode == UNIVERSAL && c) {
      cond_count--;
      if (cond_count == 0) {
        probe_callback(this->plumber,this,f,probe_callback_data,FALSE_TO_TRUE);
      } else {
        probe_callback(this->plumber,this,f,probe_callback_data,LESS_FALSE);
      }
    }
  }
}

template<class T1, class T2>
void SourceProbeNode<T1, T2>::start_probe() {
  NetPlumber<T1, T2>* n = (NetPlumber<T1, T2> *)this->plumber;
  Event e = {START_SOURCE_PROBE, this->node_id, 0};
  n->set_last_event(e);
  this->state = STARTED;
//  auto it = source_flow.begin();
//  for (; it != source_flow.end(); it++) {
  for (auto const &flow: this->source_flow) {
    if (!filter->check(flow)) continue;
    bool c = test->check(flow);
    check_results[flow] = c;
    if (mode == EXISTENTIAL && c) {
      cond_count++;
      probe_callback(this->plumber,this,flow,probe_callback_data,STARTED_TRUE);
    } else if (mode == UNIVERSAL && !c) {
      cond_count++;
      probe_callback(this->plumber,this,flow,probe_callback_data,STARTED_FALSE);
    }
  }
  if (mode == EXISTENTIAL && cond_count == 0)
    probe_callback(
      this->plumber, this, nullptr, probe_callback_data, STARTED_FALSE
    );
  else if (mode == UNIVERSAL && cond_count == 0)
    probe_callback(
      this->plumber, this, nullptr, probe_callback_data, STARTED_TRUE
    );
  this->state = RUNNING;
}

template<class T1, class T2>
void SourceProbeNode<T1, T2>::stop_probe() {
  NetPlumber<T1, T2>* n = (NetPlumber<T1, T2> *)this->plumber;
  Event e = {STOP_SOURCE_PROBE, this->node_id, 0};
  n->set_last_event(e);
  this->state = STOPPED;
  check_results.clear();
  cond_count = 0;
}

template<class T1, class T2>
typename list< Flow<T1, T2> *>::iterator SourceProbeNode<T1, T2>::get_source_flow_iterator() {
  return this->source_flow.begin();
}

template<class T1, class T2>
string SourceProbeNode<T1, T2>::to_string() {
  stringstream result;
  char buf[70];
  result << string(40, '=') << "\n";
  sprintf(buf,"0x%lx", this->node_id);
  if (mode == EXISTENTIAL) result << "  Existential ";
  else result << "  Universal ";
  result << "Probe: " << buf << "\n";
  result << string(40, '=') << "\n";
  result << "Filter: " << filter->to_string() << "\n";
  result << "Condition: " << test->to_string() << "\n";
  result << this->pipeline_to_string();
  result << this->src_flow_to_string();
  return result.str();
}

template<class T1, class T2>
void SourceProbeNode<T1, T2>::enlarge(uint32_t length) {
	if (length <= this->length) {
		return;
	}
	filter->enlarge(length);
	test->enlarge(length);
	Node<T1, T2>::enlarge(length);
	this->length = length;
}

template<class T1, class T2>
void SourceProbeNode<T1, T2>::mode_to_json(Json::Value& res) {
    res = (Json::StaticString)(
        (this->mode == UNIVERSAL) ? "universal" : "existential"
    );
}

template<class T1, class T2>
void SourceProbeNode<T1, T2>::filter_to_json(Json::Value& res) {
    filter->to_json(res);
}

template<class T1, class T2>
void SourceProbeNode<T1, T2>::test_to_json(Json::Value& res) {
    test->to_json(res);
}

template class SourceProbeNode <struct hs, array_t>;
