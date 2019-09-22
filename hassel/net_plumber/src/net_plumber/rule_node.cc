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

#include <stdio.h>
#include "rule_node.h"
#include "net_plumber_utils.h"
#include <sstream>
#include <string>
#include "net_plumber.h"

using namespace std;
using namespace net_plumber;

void RuleNode::set_layer_flags() {
  if (plumber) {
    NetPlumber* n = (NetPlumber*)plumber;
    List_t table_ports = n->get_table_ports(table);
    this->is_input_layer = lists_has_intersection(table_ports,input_ports);
    this->is_output_layer = lists_has_intersection(table_ports,output_ports);
  } else {
    this->is_input_layer = false;
    this->is_output_layer = false;
  }
}

RuleNode::RuleNode(void *n, int length, uint64_t node_id, uint32_t table,
                   List_t in_ports, List_t out_ports,
                   array_t* match, array_t *mask, array_t* rewrite) :
                   Node(n,length,node_id), table(table), group(0) {
  this->node_type = RULE;
  this->match = match;
  this->mask = mask;
  this->rewrite = rewrite;
  this->input_ports = in_ports;
  this->output_ports = out_ports;
  if (this->mask && this->rewrite) {
    this->inv_match = array_copy(this->match, length);
    array_rewrite( this->inv_match, this->mask, this->rewrite, length);
    this->inv_rw = array_not_a(this->mask,length);
    array_and(this->inv_rw,this->match,length,this->inv_rw);
  } else {
    this->inv_rw = nullptr;
    this->inv_match = array_copy(this->match, length);
  }
  effect_on = new list<struct Effect*>();
  influenced_by = new list<struct Influence*>();
  set_layer_flags();
}

RuleNode::RuleNode(void *n, int length, uint64_t node_id, uint32_t table,
                   uint64_t group, List_t in_ports, List_t out_ports,
                   array_t* match, array_t *mask, array_t* rewrite) :
                   Node(n,length,node_id), table(table), group(group) {
  this->node_type = RULE;
  this->match = match;
  this->mask = mask;
  this->rewrite = rewrite;
  this->input_ports = in_ports;
  this->output_ports = out_ports;
  if (this->mask && this->rewrite) {
    // inv_match = rw(mask(match))
    this->inv_match = array_copy(this->match, length);
    array_rewrite( this->inv_match, this->mask, this->rewrite, length);
    // inv_rw = not_mask(match)
    this->inv_rw = array_not_a(this->mask,length);
    array_and(this->inv_rw,this->match,length,this->inv_rw);
  } else {
    this->inv_rw = nullptr;
    this->inv_match = array_copy(this->match, length);
  }
  if (group == node_id) {
    effect_on = new list<struct Effect*>();
    influenced_by = new list<struct Influence*>();
  }
  set_layer_flags();
}

RuleNode::~RuleNode() {
  this->remove_flows();
  this->remove_pipes();
  // remove itself from all rules influencing on it and free its
  // influenced_by struct. In case of group rules, only o this for the lead.
  if (group == 0 || group == node_id) {
    for (auto &inf: *influenced_by) {
      auto effect = inf->effect;
      Effect *f = *effect;
      (*effect)->node->effect_on->erase(effect);
      array_free(inf->comm_arr);
      if (!inf->ports.shared) free(inf->ports.list);
      free(inf);
      free(f);
    }
    // remove itself from all rules influenced by this rule and their flows
    for (auto &eff: *effect_on) {
      list<struct Influence*>::iterator influence = eff->influence;
      RuleNode *n = (*influence)->node;
      array_t *comm_arr = (*influence)->comm_arr;
      List_t ports = (*influence)->ports;
      free(*influence);
      n->influenced_by->erase(influence);
      for (
        auto src_it = n->source_flow.begin();
        src_it != n->source_flow.end();
        src_it++
      ) {
        if (elem_in_sorted_list((*src_it)->in_port, ports)) {
          n->process_src_flow_at_location(src_it, nullptr);
        }
      }
      array_free(comm_arr);
      if (!ports.shared) free(ports.list);
      free(eff);
    }
    delete effect_on;
    delete influenced_by;
  }
  array_free(this->mask);
  array_free(this->rewrite);
  array_free(this->inv_rw);
}

string RuleNode::rule_to_str() {
  stringstream result;
  char *s;
  s = array_to_str(match,length,false);
  result << "Match: " << s;
  free(s);
  if (mask) {
    s = array_to_str(mask,length,false);
    result << ", Mask: " << s;
    free(s);
  }
  if (rewrite) {
    s = array_to_str(rewrite,length,false);
    result << ", Rewrite: " << s;
    free(s);
  }
  result << ", iPorts: " << list_to_string(input_ports);
  result << ", oPorts: " << list_to_string(output_ports);
  if (group != 0) {
    char buf[70];
    sprintf(buf,"0x%lx",group);
    result << " (group with " << buf << ")";
  }
  return result.str();
}

string RuleNode::influence_to_str() {
  stringstream result;
  char buf[70];
  char *s;
  result << "Effect On:\n";
  for (auto const &eff: *effect_on) {
    auto const influence = eff->influence;
    sprintf(buf, "0x%lx",(*influence)->node->node_id);
    result << "\tRule " << buf << "\n";
  }
  result << "Influenced By:\n";
  for (auto const &inf: *influenced_by) {
    auto const &effect = inf->effect;
    sprintf(buf, "0x%lx", (*effect)->node->node_id);
    s = array_to_str(inf->comm_arr, this->length, false);
    result << "\tRule " << buf << " (h,p) = [" << s << " , " <<
    list_to_string(inf->ports) << "]\n";
    free(s);
  }
  return result.str();
}

string RuleNode::to_string() {
  stringstream result;
  char buf[70];
  result << string(40, '=') << "\n";
  sprintf(buf,"0x%x",table);
  result << string(4, ' ') << "Table: " << buf;
  sprintf(buf,"0x%lx",node_id);
  result << " Rule: " << buf << "\n";
  result << string(40, '=') << "\n";
  result << rule_to_str() << "\n";
  result << influence_to_str();
  result << pipeline_to_string();
  result << src_flow_to_string();
  return result.str();
}

string flow_to_str2(Flow *f) {
  stringstream str;
  char buf[50];
  while(f->p_flow != f->node->get_EOSFI()) {
    char* h = hs_to_str(f->hs_object);
    sprintf(buf,"0x%lx",f->node->node_id);
    str << h << " @ " << buf << " <-- ";
    free(h);
    f = *f->p_flow;
  }
  char* h = hs_to_str(f->hs_object);
  str << h;
  free(h);
  return str.str();
}

void RuleNode::process_src_flow(Flow *f) {
  /**
    Process an incoming flow by applying the following steps:

    (Rule processing)
    1. Subtract all influencing rules from the flow
    2. Rewrite the flow (if applying)
    3. Clear flow's diff from overfitting flows

    (Forward processing, cf. Node::propagate_src_flow_on_pipes())
    4. Filter and forward flow on outgoing pipelines
    5. Process flow in next nodes
   */


  if (f) { // flow routing case
    //printf("at node %lx, processing flow: %s\n",node_id,flow_to_str2(f).c_str());
    // add f to source_flow and add it to n_flows of previous flow
    list<struct Flow*>::iterator f_it;

    source_flow.push_front(f);
    f_it = source_flow.begin();
    (*f->p_flow)->n_flows->push_front(f_it);

    // if this flow is in loop, stop propagating and return an error.
    if (is_flow_looped(f)) {
      if (((NetPlumber*)plumber)->loop_callback)
        ((NetPlumber*)plumber)->loop_callback((NetPlumber*)plumber,
                    f,((NetPlumber*)plumber)->loop_callback_data);
      return;
    }
    // diff higher priority rules
    f->processed_hs = hs_copy_a(f->hs_object);


    if (logger->isTraceEnabled()) {
      stringstream pre;
      pre << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
      pre << " with " << hs_to_str(f->processed_hs);
      pre << " before processing";
      LOG4CXX_TRACE(logger, pre.str());
    }

    for (auto const &inf: *influenced_by) {
      if (!elem_in_sorted_list(f->in_port, inf->ports)) continue;
      hs_diff(f->processed_hs, inf->comm_arr);

      if (logger->isTraceEnabled()) {
        stringstream inter;
        inter << "RuleNode::process_src_flow():   id 0x" << std::hex << this->node_id;
        inter << " with " << hs_to_str(f->processed_hs);
        inter << " after diffing " << array_to_str(inf->comm_arr, f->processed_hs->len, false);
        LOG4CXX_TRACE(logger, inter.str());
      }
    }

    if (logger->isTraceEnabled()) {
      stringstream after;
      after << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
      after << " with " << hs_to_str(f->processed_hs);
      after << " after processing";
      LOG4CXX_TRACE(logger, after.str());
    }
#ifdef NEW_HS
    if (mask && rewrite) {
        hs_rewrite(f->processed_hs, mask, rewrite);

        if (logger->isTraceEnabled()) {
          stringstream rw;
          rw << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
          rw << " with " << hs_to_str(f->processed_hs);
          rw << " after rewriting with mask " << array_to_str(mask, f->processed_hs->len, false);
          rw << " and rw " << array_to_str(rewrite, f->processed_hs->len, false);
          LOG4CXX_TRACE(logger, rw.str());
        }
    }

    const bool dead = hs_compact(f->processed_hs);

    if (logger->isTraceEnabled()) {
      stringstream comp;
      comp << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
      comp << " compressed to " << hs_to_str(f->processed_hs);
      comp << " which is " << (dead ? "dead" : "alive");
      LOG4CXX_TRACE(logger, comp.str());
    }

    if (dead) {
      LOG4CXX_TRACE(logger, "RuleNode::process_src_flow(): drop dead flow");
      hs_free(f->processed_hs);
      f->processed_hs = nullptr;
    } else {
      LOG4CXX_TRACE(logger, "RuleNode::process_src_flow(): propagate alive flow");
      f->n_flows = new list< list<struct Flow*>::iterator >();
      propagate_src_flow_on_pipes(f_it);
    }

#else
    // compress h.
    // if compress to empty, free f. else process it.
    if (!hs_compact_m(f->processed_hs,mask)) {
      hs_free(f->processed_hs);
      f->processed_hs = nullptr;
    } else {
      f->n_flows = new list< list<struct Flow*>::iterator >();
      if (mask == nullptr || rewrite == nullptr) {
        propagate_src_flow_on_pipes(f_it);
      } else {
        hs_rewrite(f->processed_hs, mask, rewrite);

        if (logger->isTraceEnabled()) {
          stringstream rw;
          rw << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
          rw << " with " << hs_to_str(f->processed_hs);
          rw << " after rewriting with mask " << array_to_str(mask, f->processed_hs->len, false);
          rw << " and rw " << array_to_str(rewrite, f->processed_hs->len, false);
          LOG4CXX_TRACE(logger, rw.str());
        }

        propagate_src_flow_on_pipes(f_it);
      }
    }
#endif

  } else { // fresh start case
    for (auto const &prev: prev_in_pipeline) {
      (*prev->r_pipeline)->node->propagate_src_flows_on_pipe(prev->r_pipeline);
    }
  }
}


void RuleNode::process_src_flow_at_location(list<struct Flow*>::iterator loc,
                                            array_t *change) {
  Flow *f = *loc;

  if (logger->isTraceEnabled()) {
    stringstream pre;
    pre << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
    pre << " with " << hs_to_str(f->processed_hs);
    pre << " before processing";
    LOG4CXX_TRACE(logger, pre.str());
  }

  if (change && (mask == nullptr || rewrite == nullptr)) {
    if (f->processed_hs == nullptr) return;
    hs_diff(f->processed_hs, change);

    if (logger->isTraceEnabled()) {
      stringstream after;
      after << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
      after << " with " << hs_to_str(f->processed_hs);
      after << " after processing";
      LOG4CXX_TRACE(logger, after.str());
    }

  } else {
    if (f->processed_hs) hs_free(f->processed_hs);
    // diff higher priority rules
    f->processed_hs = hs_copy_a(f->hs_object);

    if (logger->isTraceEnabled()) {
      stringstream inter;
      inter << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
      inter << " with " << hs_to_str(f->processed_hs);
      inter << " after (re)allocation";
      LOG4CXX_TRACE(logger, inter.str());
    }

    for (auto const inf: *influenced_by) {
      if (!elem_in_sorted_list(f->in_port, inf->ports)) continue;
      hs_diff(f->processed_hs, inf->comm_arr);

      if (logger->isTraceEnabled()) {
        stringstream loop;
        loop << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
        loop << " with " << hs_to_str(f->processed_hs);
        loop << " after diffing " << array_to_str(inf->comm_arr, f->processed_hs->len, false);
        LOG4CXX_TRACE(logger, loop.str());
      }
    }
  }

  if (logger->isTraceEnabled()) {
    stringstream after;
    after << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
    after << " with " << hs_to_str(f->processed_hs);
    after << " after processing";
    LOG4CXX_TRACE(logger, after.str());
  }

#ifdef NEW_HS

  if (mask && rewrite) {
      hs_rewrite(f->processed_hs, mask, rewrite);

      if (logger->isTraceEnabled()) {
        stringstream rw;
        rw << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
        rw << " with " << hs_to_str(f->processed_hs);
        rw << " after rewriting with mask " << array_to_str(mask, f->processed_hs->len, false);
        rw << " and rw " << array_to_str(rewrite, f->processed_hs->len, false);
        LOG4CXX_TRACE(logger, rw.str());
      }
  }

  const bool dead = hs_compact(f->processed_hs);

  if (logger->isTraceEnabled()) {
    stringstream comp;
    comp << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
    comp << " compressed to " << hs_to_str(f->processed_hs);
    comp << " which is " << (dead ? "dead" : "alive");
    LOG4CXX_TRACE(logger, comp.str());
  }

  if (dead) {
    LOG4CXX_TRACE(logger, "RuleNode::process_src_flow_at_location(): drop dead flow");
    f->node->absorb_src_flow(loc, true);
    hs_free(f->processed_hs);
    f->processed_hs = nullptr;
  } else {
    LOG4CXX_TRACE(logger, "RuleNode::process_src_flow_at_location(): propagate alive flow");
    if (!f->n_flows) f->n_flows = new list< list<struct Flow*>::iterator >();
    repropagate_src_flow_on_pipes(loc, nullptr);
  }

#else
  // compress h.
  // if compress to empty, free f. else process it.
  if (!hs_compact_m(f->processed_hs,mask)) {
    f->node->absorb_src_flow(loc, true);
    hs_free(f->processed_hs);
    f->processed_hs = nullptr;
  } else {
    if (!f->n_flows) f->n_flows = new list< list<struct Flow*>::iterator >();
    if (mask == nullptr || rewrite == nullptr) {
      repropagate_src_flow_on_pipes(loc, change);
    } else {
      hs_rewrite(f->processed_hs, mask, rewrite);

      if (logger->isTraceEnabled()) {
        stringstream rw;
        rw << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
        rw << " with " << hs_to_str(f->processed_hs);
        rw << " after rewriting with mask " << array_to_str(mask, f->processed_hs->len, false);
        rw << " and rw " << array_to_str(rewrite, f->processed_hs->len, false);
        LOG4CXX_TRACE(logger, rw.str());
      }

      repropagate_src_flow_on_pipes(loc, nullptr);
    }
  }
#endif
}


void RuleNode::subtract_infuences_from_flows() {
  /*
   * when a new rule is added, this function is called to updat the lower
   * priority flows.
   */
  for (auto eff: *effect_on) {
//  for (auto eff_it = effect_on->begin(); eff_it != effect_on->end(); eff_it++) {
    RuleNode *n = (RuleNode *)(*eff->influence)->node;

    for (
        auto src_it = n->source_flow.begin();
        src_it != n->source_flow.end();
        src_it++
    ) {
      if (elem_in_sorted_list(
        (*src_it)->in_port, (*eff->influence)->ports
      )) {
        n->process_src_flow_at_location(
            src_it, (*eff->influence)->comm_arr
        );
      }
    }
  }
}

list<struct Influence*>::iterator RuleNode::set_influence_by(Influence *inf) {
  this->influenced_by->push_front(inf);
  return this->influenced_by->begin();
}

list<struct Effect*>::iterator RuleNode::set_effect_on(Effect *eff) {
  this->effect_on->push_front(eff);
  return this->effect_on->begin();
}

int RuleNode::count_effects() {
  return this->effect_on->size();
}

int RuleNode::count_influences() {
  return this->influenced_by->size();
}

void RuleNode::enlarge(uint32_t length) {
	if (length <= this->length) {
		return;
	}
	if (this->mask)
		this->mask = array_resize(this->mask,this->length, length);
	if (this->rewrite)
		this->rewrite = array_resize(this->rewrite,this->length, length);
	if (this->inv_rw)
		this->inv_rw = array_resize(this->inv_rw,this->length, length);
	//Effect should not matter
	for (auto const &inf: *influenced_by) {
		if (inf->comm_arr && (length > inf->len)) {
            inf->comm_arr = array_resize(inf->comm_arr, inf->len, length);
            inf->len = length;
        }
	}

	Node::enlarge(length);
	this->length = length;
}
