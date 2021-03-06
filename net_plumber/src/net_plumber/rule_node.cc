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

#include <stdio.h>
#include "rule_node.h"
#include "net_plumber_utils.h"
#include <sstream>
#include <string>
#include "net_plumber.h"
#include "array_packet_set.h"
#include "hs_packet_set.h"
#ifdef USE_BDD
#include "bdd_packet_set.h"
#endif

using namespace std;
using namespace net_plumber;

template<class T1, class T2>
void RuleNode<T1, T2>::set_layer_flags() {
  if (this->plumber) {
    NetPlumber<T1, T2>* n = (NetPlumber<T1, T2> *)this->plumber;
    List_t table_ports = n->get_table_ports(this->table);
    this->is_input_layer = lists_has_intersection(table_ports, this->input_ports);
    this->is_output_layer = lists_has_intersection(table_ports, this->output_ports);
  } else {
    this->is_input_layer = false;
    this->is_output_layer = false;
  }
}

template<class T1, class T2>
#ifdef USE_GROUPS
RuleNode<T1, T2>::RuleNode(void *n, int length, uint64_t node_id, uint32_t table, uint32_t index,
                   List_t in_ports, List_t out_ports,
//                   T2 *match, Mask<T2> *mask, Rewrite<T2> *rewrite) :
                   T2 *match, T2 *mask, T2 *rewrite) :
                   Node<T1, T2>(n,length,node_id), table(table), index(index), group(0) {
#else
RuleNode<T1, T2>::RuleNode(void *n, int length, uint64_t node_id, uint32_t table, uint32_t index,
                   List_t in_ports, List_t out_ports,
//                   T2 *match, Mask<T2> *mask, Rewrite<T2> *rewrite) :
                   T2 *match, T2 *mask, T2 *rewrite) :
                   Node<T1, T2>(n,length,node_id), table(table), index(index) {
#endif
  this->node_type = RULE;
  this->match = match;
  this->mask = mask;
  this->rewrite = rewrite;
  this->input_ports = in_ports;
  this->output_ports = out_ports;
  if (this->mask && this->rewrite) {
#ifdef GENERIC_PS
    this->inv_match = new T2(*this->match);
    this->inv_match->rewrite(this->mask, this->rewrite);
#else
    this->inv_match = array_copy(this->match, this->length);
    array_rewrite(this->inv_match, this->mask, this->rewrite, this->length);
#endif
#ifdef USE_INV
#ifdef GENERIC_PS
    this->inv_rw = new T2(*this->mask);
    this->inv_rw->negate();
    this->inv_rw->psand(this->match);
#else
    this->inv_rw = array_not_a(this->mask, this->length);
    array_and(this->inv_rw, this->match, this->length, this->inv_rw);
#endif
#endif
  } else {
#ifdef USE_INV
    this->inv_rw = nullptr;
#endif
#ifdef GENERIC_PS
    this->inv_match = new T2(*this->match);
#else
    this->inv_match = array_copy(this->match, this->length);
#endif
  }
  effect_on = new list<struct Effect<T1, T2> *>();
  influenced_by = new list< Influence<T1, T2> *>();
  set_layer_flags();
}

#ifdef USE_GROUPS
template<class T1, class T2>
RuleNode<T1, T2>::RuleNode(void *n, int length, uint64_t node_id, uint32_t table, uint32_t index,
                   uint64_t group, List_t in_ports, List_t out_ports,
//                   T2 *match, Mask<T2> *mask, Rewrite<T2> *rewrite) :
                   T2 *match, T2 *mask, T2 *rewrite) :
                   Node<T1, T2>(n,length,node_id), table(table), index(index), group(group) {
  this->node_type = RULE;
  this->match = match;
  this->mask = mask;
  this->rewrite = rewrite;
  this->input_ports = in_ports;
  this->output_ports = out_ports;
  if (this->mask && this->rewrite) {
    this->inv_match = new T2(*this->match);
    this->inv_match->rewrite2(this->mask, this->rewrite);
#ifdef USE_INV
    this->inv_rw = new T2(*this->mask);
    this->inv_rw.negate();
    this->inv_rw.psand(this->match);
#endif
  } else {
#ifdef USE_INV
    this->inv_rw = nullptr;
#endif
    this->inv_match = new T2(*this->match);
  }
  if (group == node_id) {
    effect_on = new list<struct Effect<T1, T2> *>();
    influenced_by = new list< Influence<T1, T2> *>();
  }
  set_layer_flags();
}
#endif

template<class T1, class T2>
RuleNode<T1, T2>::~RuleNode() {
  this->remove_flows();
  this->remove_pipes();
  // remove itself from all rules influencing on it and free its
  // influenced_by struct. In case of group rules, only o this for the lead.
#ifdef USE_GROUPS
  if (group == 0 || group == this->node_id) {
#endif
    for (auto &inf: *influenced_by) {
      auto effect = inf->effect;
      Effect<T1, T2> *f = *effect;
      (*effect)->node->effect_on->erase(effect);
#ifdef GENERIC_PS
      delete inf->comm_arr;
#else
      array_free(inf->comm_arr);
#endif
      if (!inf->ports.shared) free(inf->ports.list);
      free(inf);
      free(f);
    }
    // remove itself from all rules influenced by this rule and their flows
    for (auto &eff: *effect_on) {
      typename list< Influence<T1, T2> *>::iterator influence = eff->influence;
      RuleNode<T1, T2> *n = (*influence)->node;
      T2 *comm_arr = (*influence)->comm_arr;
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
#ifdef GENERIC_PS
      delete comm_arr;
#else
      array_free(comm_arr);
#endif
      if (!ports.shared) free(ports.list);
      free(eff);
    }
    delete effect_on;
    delete influenced_by;
#ifdef USE_GROUPS
  }
#endif
#ifdef GENERIC_PS
  delete this->mask;
  delete this->rewrite;
#ifdef USE_INV
  delete this->inv_rw;
#endif
#else
  array_free(this->mask);
  array_free(this->rewrite);
#ifdef USE_INV
  array_free(this->inv_rw);
#endif
#endif
}

template<class T1, class T2>
string RuleNode<T1, T2>::rule_to_str() {
  stringstream result;
#ifdef GENERIC_PS
  result << "Match: " << this->match->to_str();
  if (mask) {
    result << ", Mask: " << this->mask->to_str();
  }
  if (rewrite) {
    result << ", Rewrite: " << this->rewrite->to_str();
  }
#else
  result << "Match: " << array_to_str(this->match, this->length, false);
  if (mask) {
    result << ", Mask: " << array_to_str(this->mask, this->length, false);
  }
  if (rewrite) {
    result << ", Rewrite: " << array_to_str(this->rewrite, this->length, false);
  }
#endif
  result << ", iPorts: " << list_to_string(this->input_ports);
  result << ", oPorts: " << list_to_string(this->output_ports);
#ifdef USE_GROUPS
  if (group != 0) {
    result << " (group with 0x" << std::hex << this->group << ")";
  }
#endif
  return result.str();
}

template<class T1, class T2>
string RuleNode<T1, T2>::influence_to_str() {
  stringstream result;
  result << "Effect On:\n";
  for (auto const &eff: *effect_on) {
    auto const influence = eff->influence;
    result << "\tRule " << std::hex << (*influence)->node->node_id << "\n";
  }
  result << "Influenced By:\n";
  for (auto const &inf: *influenced_by) {
    auto const &effect = inf->effect;
    result << "\tRule 0x" << std::hex << (*effect)->node->node_id << " (h,p) = [";
#ifdef GENERIC_PS
    result << inf->comm_arr->to_str();
#else
    result << array_to_str(inf->comm_arr, this->length, false);
#endif
    result << " , " << list_to_string(inf->ports) << "]\n";
  }
  return result.str();
}

template<class T1, class T2>
string RuleNode<T1, T2>::to_string() {
  stringstream result;
  result << string(40, '=') << "\n";
  result << string(4, ' ') << "Table: 0x" << std::hex << this->table;
  result << " Rule: 0x" << std::hex << this->node_id << "\n";
  result << string(40, '=') << "\n";
  result << this->rule_to_str() << "\n";
  result << this->influence_to_str();
  result << this->pipeline_to_string();
  result << this->src_flow_to_string();
  return result.str();
}

template<class T1, class T2>
string flow_to_str2(Flow<T1, T2> *f) {
  stringstream str;
  char buf[50];
  while(f->p_flow != f->node->get_EOSFI()) {
    str << f->hs_object->to_str() << " @ 0x" << std::hex << f->node->node_id << " <-- ";
    f = *f->p_flow;
  }
  str << f->hs_object->to_str();
  return str.str();
}

template<class T1, class T2>
void RuleNode<T1, T2>::process_src_flow(Flow<T1, T2> *f) {
  const bool tracing = this->logger->isTraceEnabled();

#ifdef NEW_HS
  /**
    Process an incoming flow by applying the following steps:

    (Rule processing)
    1. Subtract all influencing rules from the flow
    2. Rewrite the flow (if applying)
    3. Clear flow's diff from overfitting flows

    (Forward processing, cf. Node::propagate_src_flow_on_pipes())
    4. Filter and forward flow on outgoing pipelines
    5. Process flow in next nodes

    Example:
    rule.match     = 1xx11xxx
    rule.mask      = 11000000
    rule.rewrite   = 10xxxxxx
    rule.influnces = (10x11xxx)

    flow = (1xx11xxx)

    (1xx11xxx) - (10x11xxx) // apply diffs
    (11x11xxx + 10x11xxx) - (10x11xxx) // expand superset wildcards
    (11x11xxx) // compact flow
    (10x11xxx) // rewrite flow
   */
#endif

  if (f) { // flow routing case
    // add f to source_flow and add it to n_flows of previous flow
    typename list< Flow<T1, T2>* >::iterator f_it;

    this->source_flow.push_front(f);
    f_it = this->source_flow.begin();
    (*f->p_flow)->n_flows->push_front(f_it);

    // if this flow is in loop, stop propagating and return an error.
    if (is_flow_looped(f)) {
      if (((NetPlumber<T1, T2> *)this->plumber)->loop_callback)
        ((NetPlumber<T1, T2> *)this->plumber)->loop_callback((NetPlumber<T1, T2> *)this->plumber,
                    f,((NetPlumber<T1, T2> *)this->plumber)->loop_callback_data);
      return;
    }
    // diff higher priority rules
#ifdef GENERIC_PS
    f->processed_hs = new T1(*f->hs_object);
#else
    f->processed_hs = hs_copy_a(f->hs_object);
#endif

    if (tracing) {
      stringstream pre;
      pre << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
      pre << " with " << f->processed_hs->to_str();
#else
      char *tmp = hs_to_str(f->processed_hs);
      pre << " with " << std::string(tmp);
      free(tmp);
#endif
      pre << " before processing";
      LOG4CXX_TRACE(this->logger, pre.str());
    }

    for (auto const &inf: *influenced_by) {
      if (!elem_in_sorted_list(f->in_port, inf->ports)) continue;
#ifdef GENERIC_PS
//      f->processed_hs->diff2(inf->comm_arr);
      hs_diff(&f->processed_hs->hs, inf->comm_arr->array); // XXX
#else
      hs_diff(f->processed_hs, inf->comm_arr);
#endif

      if (tracing) {
        stringstream inter;
        inter << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
        inter << " with " << f->processed_hs->to_str();
        inter << " after diffing " << inf->comm_arr->to_str();
#else
        char *tmp = hs_to_str(f->processed_hs);
        inter << " with " << std::string(tmp);
        free(tmp); tmp = array_to_str(inf->comm_arr, this->length, false);
        inter << " after diffing " << std::string(tmp);
        free(tmp);
#endif
        LOG4CXX_TRACE(this->logger, inter.str());
      }
    }

    if (tracing) {
      stringstream after;
      after << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
      after << " with " << f->processed_hs->to_str();
#else
      char *tmp = hs_to_str(f->processed_hs);
      after << " with " << std::string(tmp);
      free(tmp);
#endif
      after << " after processing";
      LOG4CXX_TRACE(this->logger, after.str());
    }
#ifdef NEW_HS
    if (mask && rewrite) {
        hs influences = {0, {0, 0, 0}, {0, 0, 0}};

        for (auto const &inf: *influenced_by) {
            hs_vec_append(&influences.list, inf->comm_arr);
        }

        hs_unroll_superset(f->processed_hs, &influences);

        f->processed_hs->rewrite2(mask, rewrite);

        if (tracing) {
          stringstream rw;
          rw << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
          rw << " with " << f->processed_hs->to_str();
          rw << " after rewriting with mask " << mask->to_str();
          rw << " and rw " << rewrite->to_str();
#else
          char *tmp = hs_to_str(f->processed_hs);
          rw << " with " << std::string(tmp);
          free(tmp); tmp = array_to_str(mask, this->length, false);
          rw << " after rewriting with mask " << std::string(tmp);
          free(tmp); tmp = array_to_str(rewrite, this->length, false);
          rw << " and rw " << std::string(tmp);
          free(tmp);
#endif
          LOG4CXX_TRACE(this->logger, rw.str());
        }
    }

    const bool dead = hs_compact(f->processed_hs);

    if (tracing) {
      stringstream comp;
      comp << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
      comp << " compressed to " << f->processed_hs->to_str();
#else
      char *tmp = hs_to_str(f->processed_hs);
      comp << " compressed to " << std::string(tmp);
      free(tmp);
#endif
      comp << " which is " << (dead ? "dead" : "alive");
      LOG4CXX_TRACE(this->logger, comp.str());
    }

    if (dead) {
      if (tracing) LOG4CXX_TRACE(this->logger, "RuleNode::process_src_flow(): drop dead flow");
      hs_free(f->processed_hs);
      f->processed_hs = nullptr;
    } else {
      if (tracing) LOG4CXX_TRACE(this->logger, "RuleNode::process_src_flow(): propagate alive flow");
      f->n_flows = new list< typename list< Flow<T1, T2> *>::iterator >();
      this->propagate_src_flow_on_pipes(f_it);
    }

#else
    // compress h.
    // if compress to empty, free f. else process it.
#ifdef GENERIC_PS
//    f->processed_hs->compact2(mask);
//    const bool dead = f->processed_hs->is_empty();
    const bool dead = !hs_compact_m(&f->processed_hs->hs, this->mask ? this->mask->array : nullptr); // XXX
#else
    const bool dead = !hs_compact_m(f->processed_hs, this->mask);
#endif

    if (dead) {
#ifdef GENERIC_PS
      delete f->processed_hs;
#else
      hs_free(f->processed_hs);
#endif
      f->processed_hs = nullptr;

      if (tracing) {
        stringstream empty;
        empty << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
        empty << " compressed to empty set.";
        LOG4CXX_TRACE(this->logger, empty.str());
      }

    } else {
      f->n_flows = new list< typename list< Flow<T1, T2> *>::iterator >();
      if (mask == nullptr || rewrite == nullptr) {
        if (tracing) {
          stringstream no_rw;
          no_rw << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
          no_rw << " with " << f->processed_hs->to_str();
#else
          char *tmp = hs_to_str(f->processed_hs);
          no_rw << " with " << std::string(tmp);
          free(tmp);
#endif
          no_rw << " no rewriting";
          LOG4CXX_TRACE(this->logger, no_rw.str());
        }

        this->propagate_src_flow_on_pipes(f_it);
      } else {
#ifdef GENERIC_PS
//        f->processed_hs->rewrite2(mask, rewrite);
        hs_rewrite(&f->processed_hs->hs, mask->array, rewrite->array);
#else
        hs_rewrite(f->processed_hs, this->mask, this->rewrite);
#endif

        if (tracing) {
          stringstream rw;
          rw << "RuleNode::process_src_flow(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
          rw << " with " << f->processed_hs->to_str();
          rw << " after rewriting with mask " << mask->to_str();
          rw << " and rw " << rewrite->to_str();
#else
          char *tmp = hs_to_str(f->processed_hs);
          rw << " with " << std::string(tmp);
          free(tmp); tmp = array_to_str(mask, this->length, false);
          rw << " after rewriting with mask " << std::string(tmp);
          free(tmp); tmp = array_to_str(rewrite, this->length, false);
          rw << " and rw " << std::string(tmp);
          free(tmp);
#endif
          LOG4CXX_TRACE(this->logger, rw.str());
        }

        this->propagate_src_flow_on_pipes(f_it);
      }
    }
#endif

  } else { // fresh start case
    for (auto const &prev: this->prev_in_pipeline) {
      (*prev->r_pipeline)->node->propagate_src_flows_on_pipe(prev->r_pipeline);
    }
  }
}


template<class T1, class T2>
void RuleNode<T1, T2>::process_src_flow_at_location(typename list< Flow<T1, T2> *>::iterator loc,
                                            T2 *change) {
  const bool tracing = this->logger->isTraceEnabled();
  Flow<T1, T2> *f = *loc;

  if (tracing) {
    stringstream pre;
    pre << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
    pre << " with ";
#ifdef GENERIC_PS
    if (f && f->processed_hs) pre << f->processed_hs->to_str();
    else pre << "(nil)";
#else
    if (f && f->processed_hs) {
      char *tmp = hs_to_str(f->processed_hs);
      pre << std::string(tmp);
      free(tmp);
    }
    else pre << "(nil)";
#endif
    pre << " before processing";
    LOG4CXX_TRACE(this->logger, pre.str());
  }

#ifdef GENERIC_PS
  if (change && !change->is_empty() && (mask == nullptr || rewrite == nullptr)) {
    if (f->processed_hs == nullptr || f->processed_hs->is_empty()) return;
    f->processed_hs->diff2(change);
#else
  if (change && (this->mask == nullptr || this->rewrite == nullptr)) {
    if (f->processed_hs == nullptr) return;
    hs_diff(f->processed_hs, change);
#endif

    if (tracing) {
      stringstream after;
      after << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
      after << " with " << f->processed_hs->to_str();
      after << " after diffing" << change->to_str();
#else
      char *tmp = hs_to_str(f->processed_hs);
      after << " with " << std::string(tmp);
      free(tmp); tmp = array_to_str(change, this->length, false);
      after << " after diffing" << std::string(tmp);
      free(tmp);
#endif
      LOG4CXX_TRACE(this->logger, after.str());
    }

  } else {
    // diff higher priority rules
#ifdef GENERIC_PS
    if (f->processed_hs) delete f->processed_hs;
    f->processed_hs = new T1(*f->hs_object);
#else
    if (f->processed_hs) hs_destroy(f->processed_hs);
    else f->processed_hs = hs_create(this->length);
    hs_copy(f->processed_hs, f->hs_object);
#endif

    if (tracing) {
      stringstream inter;
      inter << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
      inter << " with " << f->processed_hs->to_str();
#else
      char *tmp = hs_to_str(f->processed_hs);
      inter << " with " << std::string(tmp);
      free(tmp);
#endif
      inter << " after (re)allocation of hs_object";
      LOG4CXX_TRACE(this->logger, inter.str());
    }

    for (auto const inf: *influenced_by) {
      if (!elem_in_sorted_list(f->in_port, inf->ports)) continue;
#ifdef GENERIC_PS
      f->processed_hs->diff2(inf->comm_arr);
#else
      hs_diff(f->processed_hs, inf->comm_arr);
#endif

      if (tracing) {
        stringstream loop;
        loop << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
        loop << " with " << f->processed_hs->to_str();
        loop << " after diffing " << inf->comm_arr->to_str();
#else
        char *tmp = hs_to_str(f->processed_hs);
        loop << " with " << std::string(tmp);
        free(tmp); tmp = array_to_str(inf->comm_arr, this->length, false);
        loop << " after diffing " << std::string(tmp);
        free(tmp);
#endif
        LOG4CXX_TRACE(this->logger, loop.str());
      }
    }
  }

  if (tracing) {
    stringstream after;
    after << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
    after << " with " << f->processed_hs->to_str();
#else
    char *tmp = hs_to_str(f->processed_hs);
    after << " with " << std::string(tmp);
    free(tmp);
#endif
    after << " after processing";
    LOG4CXX_TRACE(this->logger, after.str());
  }

#ifdef NEW_HS

  if (mask && rewrite) {
      f->processed_hs->rewrite2(mask, rewrite);

      if (tracing) {
        stringstream rw;
        rw << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
        after << " with " << f->processed_hs->to_str();
        rw << " after rewriting with mask " << mask->to_str();
        rw << " and rw " << rewrite->to_str();
#else
        char *tmp = hs_to_str(f->processed_hs);
        after << " with " << std::string(tmp);
        free(tmp); tmp = array_to_str(mask, this->length, false);
        rw << " after rewriting with mask " << std::string(tmp);
        free(tmp); tmp = array_to_str(rewrite, this->length, false);
        rw << " and rw " << std::string(tmp);
        free(tmp);
#endif

        LOG4CXX_TRACE(this->logger, rw.str());
      }
  }

  f->processed_hs->compact();
  const bool dead = f->processed_hs->is_empty();

  if (tracing) {
    stringstream comp;
    comp << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
    comp << " compressed to " << f->processed_hs->to_str();
#else
    char *tmp = hs_to_str(f->processed_hs);
    comp << " compressed to " << std::string(tmp);
    free(tmp);
#endif
    comp << " which is " << (dead ? "dead" : "alive");
    LOG4CXX_TRACE(this->logger, comp.str());
  }

  if (dead) {
    if (tracing) LOG4CXX_TRACE(this->logger, "RuleNode::process_src_flow_at_location(): drop dead flow");
    f->node->absorb_src_flow(loc, true);
    delete f->processed_hs;
    f->processed_hs = nullptr;
  } else {
    if (tracing) LOG4CXX_TRACE(this->logger, "RuleNode::process_src_flow_at_location(): propagate alive flow");
    if (!f->n_flows) f->n_flows = new list< typename list< Flow<T1, T2> *>::iterator >();
    this->repropagate_src_flow_on_pipes(loc, nullptr);
  }

#else
  // compress h.
  // if compress to empty, free f. else process it.

#ifdef GENERIC_PS
  f->processed_hs->compact2(mask);
  const bool dead = f->processed_hs->is_empty();
#else
  const bool dead = !hs_compact_m(f->processed_hs, this->mask);
#endif

  if (dead) {
    f->node->absorb_src_flow(loc, true);
#ifdef GENERIC_PS
    delete f->processed_hs;
#else
    hs_free(f->processed_hs);
#endif
    f->processed_hs = nullptr;

    if (tracing) {
      stringstream empty;
      empty << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
      empty << " compressed to empty set.";
      LOG4CXX_TRACE(this->logger, empty.str());
    }

  } else {
    if (!f->n_flows) f->n_flows = new list< typename list< Flow<T1, T2> *>::iterator >();
    if (this->mask == nullptr || this->rewrite == nullptr) {

      if (tracing) {
        stringstream no_rw;
        no_rw << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
        no_rw << " with " << f->processed_hs->to_str();
#else
        char *tmp = hs_to_str(f->processed_hs);
        no_rw << " with " << std::string(tmp);
        free(tmp);
#endif
        no_rw << " no rewriting";
        LOG4CXX_TRACE(this->logger, no_rw.str());
      }

      this->repropagate_src_flow_on_pipes(loc, change);

    } else {
#ifdef GENERIC_PS
      f->processed_hs->rewrite2(this->mask, this->rewrite);
#else
      hs_rewrite(f->processed_hs, this->mask, this->rewrite);
#endif

      if (tracing) {
        stringstream rw;
        rw << "RuleNode::process_src_flow_at_location(): id 0x" << std::hex << this->node_id;
#ifdef GENERIC_PS
        rw << " with " << f->processed_hs->to_str();
        rw << " after rewriting with mask " << mask->to_str();
        rw << " and rw " << rewrite->to_str();
#else
        char *tmp = hs_to_str(f->processed_hs);
        rw << " with " << std::string(tmp);
        free(tmp); tmp = array_to_str(mask, this->length, false);
        rw << " after rewriting with mask " << std::string(tmp);
        free(tmp); tmp = array_to_str(rewrite, this->length, false);
        rw << " and rw " << std::string(tmp);
        free(tmp);
#endif
        LOG4CXX_TRACE(this->logger, rw.str());
      }

      this->repropagate_src_flow_on_pipes(loc, nullptr);
    }
  }
#endif
}


template<class T1, class T2>
void RuleNode<T1, T2>::subtract_infuences_from_flows() {
  /*
   * when a new rule is added, this function is called to updat the lower
   * priority flows.
   */
  for (auto eff: *effect_on) {
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

template<class T1, class T2>
typename list< Influence<T1, T2> *>::iterator RuleNode<T1, T2>::set_influence_by(Influence<T1, T2> *inf) {
  this->influenced_by->push_front(inf);
  return this->influenced_by->begin();
}

template<class T1, class T2>
typename list< Effect<T1, T2> *>::iterator RuleNode<T1, T2>::set_effect_on(Effect<T1, T2> *eff) {
  this->effect_on->push_front(eff);
  return this->effect_on->begin();
}

template<class T1, class T2>
int RuleNode<T1, T2>::count_effects() {
  return this->effect_on->size();
}

template<class T1, class T2>
int RuleNode<T1, T2>::count_influences() {
  return this->influenced_by->size();
}

template<class T1, class T2>
void RuleNode<T1, T2>::enlarge(uint32_t length) {
    const bool tracing = this->logger->isTraceEnabled();
    const bool debug = this->logger->isDebugEnabled();
    if (tracing) {
      stringstream enl;
      enl << "RuleNode::enlarge(): id 0x" << std::hex << this->node_id;
      enl << " enlarge from " << std::dec << this->length << " to " << length;
      LOG4CXX_TRACE(this->logger, enl.str());
    }

    if (length <= this->length) {
        return;
    }
    if (debug) LOG4CXX_DEBUG(this->logger, "RuleNode::enlarge(): enlarge mask");
#ifdef GENERIC_PS
    if (this->mask)
        this->mask->enlarge2(length);
    if (debug) LOG4CXX_DEBUG(this->logger, "RuleNode::enlarge(): enlarge rewrite");
    if (this->rewrite)
        this->rewrite->enlarge(length);
//        this->rewrite->rewrite->enlarge(length);
#ifdef USE_INV
    if (debug) LOG4CXX_DEBUG(this->logger, "RuleNode::enlarge(): enlarge inverse rewrite");
    if (this->inv_rw)
        this->inv_rw->enlarge(length);
#endif
    //Effect should not matter
    if (debug) LOG4CXX_DEBUG(this->logger, "RuleNode::enlarge(): enlarge influences");
    for (auto const &inf: *influenced_by) {
        if (inf->comm_arr && (length > inf->len)) {
            inf->comm_arr->enlarge(length);
        }
    }
#else
    const size_t olen = this->length;
    T2 *tmp;
    if (this->mask) {
        tmp = array_generic_resize(this->mask, olen, length, BIT_0);
        this->mask = tmp;
    }
    if (debug) LOG4CXX_DEBUG(this->logger, "RuleNode::enlarge(): enlarge rewrite");
    if (this->rewrite) {
        tmp = array_resize(this->rewrite, olen, length);
        this->rewrite = tmp;
    }
#ifdef USE_INV
    if (debug) LOG4CXX_DEBUG(this->logger, "RuleNode::enlarge(): enlarge inverse rewrite");
    if (this->inv_rw) {
        tmp = array_resize(this->inv_rw, olen, length);
        this->inv_rw = tmp;
    }
#endif
    //Effect should not matter
    if (debug) LOG4CXX_DEBUG(this->logger, "RuleNode::enlarge(): enlarge influences");
    for (auto const &inf: *influenced_by) {
        if (inf->comm_arr && (length > inf->len)) {
            tmp = array_resize(inf->comm_arr, olen, length);
            inf->comm_arr = tmp;
        }
    }
#endif

    Node<T1, T2>::enlarge(length);
    if (debug) LOG4CXX_DEBUG(this->logger, "RuleNode::enlarge(): persist length\n");
    this->length = length;
}

#ifdef GENERIC_PS
template class RuleNode<HeaderspacePacketSet, ArrayPacketSet>;
#ifdef USE_BDD
template class RuleNode <BDDPacketSet, BDDPacketSet>;
#endif
#else
template class RuleNode <hs, array_t>;
#endif
