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

#include "policy_probe_node.h"
#include "net_plumber_utils.h"
#include <sstream>
#include <string>
#include "net_plumber.h"
#include <assert.h>

using namespace std;
using namespace log4cxx;
using namespace net_plumber;

LoggerPtr policy_probe_def_logger(Logger::getLogger("DefaultProbeLogger"));

void default_probe_callback(void *caller, PolicyProbeNode *p, Flow *f,void *data) {
  NetPlumber *N = (NetPlumber *)caller;
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Probe " << p->node_id << " Activated after event " <<
      get_event_name(e.type) << ": Policy Violation!";
  LOG4CXX_WARN(policy_probe_def_logger,error_msg.str());
}

PolicyProbeNode::PolicyProbeNode(void *n, int length, uint64_t node_id,
                                 List_t ports,
                                 PolicyChecker *checker,
                                 policy_probe_callback_t probe_callback, void* d)
: Node(n,length,node_id), state(STOPPED), checker(checker), probe_callback_data(d)
{
  this->node_type = POLICY_PROBE;
  this->match = array_create(length, BIT_X);
  this->inv_match = NULL;
  this->input_ports = ports;
  this->output_ports = make_sorted_list(0);
  if (probe_callback) this->probe_callback = probe_callback;
  else this->probe_callback = default_probe_callback;
  this->registrant = this->checker->register_probe(this);
}

PolicyProbeNode::~PolicyProbeNode() {
    this->checker->unregister_probe(this->registrant);
}

// TODO: modify if necessary
void PolicyProbeNode::process_src_flow(Flow *f) {
  if (f) {
    list<struct Flow*>::iterator f_it;
    source_flow.push_front(f);
    f_it = source_flow.begin();
    (*f->p_flow)->n_flows->push_front(f_it);
    f->processed_hs = hs_copy_a(f->hs_object);
    hs_comp_diff(f->processed_hs);
    if (state == RUNNING) update_check(f,FLOW_ADD);
  } else {
    list<struct Pipeline*>::iterator it;
    for (it = prev_in_pipeline.begin(); it != prev_in_pipeline.end(); it++) {
      (*(*it)->r_pipeline)->node->
          propagate_src_flows_on_pipe((*it)->r_pipeline);
    }
  }
}

// TODO: modify if necessary
void PolicyProbeNode::process_src_flow_at_location(
     list<struct Flow*>::iterator loc, array_t* change) {
  Flow *f = *loc;
  if (change) {
    if (f->processed_hs->list.used == 0) return;
    hs_diff(f->processed_hs, change);
  } else {
    hs_free(f->processed_hs);
    f->processed_hs = hs_copy_a(f->hs_object);
    hs_comp_diff(f->processed_hs);
  }
  if (state == RUNNING) update_check(f,FLOW_MODIFY);
}

void PolicyProbeNode::absorb_src_flow(list<struct Flow*>::iterator s_flow,
    bool first) {
  if (state == RUNNING) update_check(*s_flow,FLOW_DELETE);
  Node::absorb_src_flow(s_flow, first);
}

void PolicyProbeNode::update_check(Flow *f, PROBE_FLOW_ACTION action) {
  /*
   * 0: add
   * 1: modified
   * 2: deleted
   */

  bool c;
  switch(action) {
    case FLOW_ADD:
        c = checker->check_path(f->hs_object,f->processed_hs);
        check_results[f] = c;
        if (!c) probe_callback(this->plumber,this,f,probe_callback_data);
    case FLOW_MODIFY:
        c = checker->check_path(f->hs_object,f->processed_hs);
        check_results[f] = c;
        if (!c) probe_callback(this->plumber,this,f,probe_callback_data);
    case FLOW_DELETE:
        map<Flow*,bool>::iterator it = check_results.find(f);
        if (it != check_results.end()) check_results.erase(it);
  }
}

void PolicyProbeNode::reprocess_flows() {
    std::list<struct Flow*>::iterator s;
    for (s = source_flow.begin(); s != source_flow.end(); s++)
        update_check(*s,FLOW_MODIFY);
}

void PolicyProbeNode::start_probe() {
  NetPlumber* n = (NetPlumber*)this->plumber;
#ifdef POLICY_PROBES // TODO: this is really crappy
  Event e = {START_POLICY_PROBE,node_id,0};
#else
  Event e = {START_SOURCE_PROBE,node_id,0};
#endif
  n->set_last_event(e);
  this->state = STARTED;

  list<Flow *>::iterator it;
  for (it = source_flow.begin(); it != source_flow.end(); it++) {
    Flow *f = *it;

    bool c = checker->check_path(f->hs_object,f->processed_hs);

    check_results[f] = c;
    if (!c) probe_callback(this->plumber,this,f,probe_callback_data);
  }

  this->state = RUNNING;
}

void PolicyProbeNode::stop_probe() {
  NetPlumber* n = (NetPlumber*)this->plumber;
#ifdef POLICY_PROBES // TODO: this is really crappy
  Event e = {STOP_POLICY_PROBE,node_id,0};
#else
  Event e = {STOP_SOURCE_PROBE,node_id,0};
#endif
  n->set_last_event(e);
  this->state = STOPPED;
  check_results.clear();
}

list<Flow*>::iterator PolicyProbeNode::get_source_flow_iterator() {
  return source_flow.begin();
}

string PolicyProbeNode::to_string() {
  stringstream result;
  char buf[70];
  result << string(40, '=') << "\n";
  sprintf(buf,"0x%lx",node_id);
  result << "Probe: Policy Probe" << buf << "\n";
  result << string(40, '=') << "\n";
  result << pipeline_to_string();
  result << src_flow_to_string();
  return result.str();
}


