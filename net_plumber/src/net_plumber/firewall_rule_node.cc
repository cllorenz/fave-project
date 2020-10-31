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

#include <stdio.h>
#include "firewall_rule_node.h"
#include "net_plumber_utils.h"
#include <sstream>
#include <string>
#include "net_plumber.h"
#include <set>
#include <typeinfo>

using namespace std;
using namespace net_plumber;

FirewallRuleNode::FirewallRuleNode(void *n, int length, uint64_t node_id, uint32_t table,
                   List_t in_ports, List_t out_ports,
                   hs *fw_match) :
                    RuleNode(n,length,node_id,table,in_ports,out_ports,
                      array_create(length,BIT_X),NULL,NULL),
                    fw_match(fw_match) {
  this->node_type = FIREWALL_RULE;
  this->inv_match = NULL;// hs_copy_a(this->fw_match);
}

FirewallRuleNode::FirewallRuleNode(void *n, int length, uint64_t node_id, uint32_t table,
                   uint64_t group, List_t in_ports, List_t out_ports,
                   hs* fw_match) :
                    RuleNode(n,length,node_id,table,group,in_ports,out_ports,
                      array_create(length,BIT_X),NULL,NULL),
                    fw_match(fw_match) {
  this->node_type = FIREWALL_RULE;
  this->inv_match = NULL;//hs_copy(this->fw_match);
}

FirewallRuleNode::~FirewallRuleNode() {
  this->remove_flows();
  this->remove_pipes();
  // remove itself from all rules influencing on it and free its
  // influenced_by struct. In case of group rules, only o this for the lead.
  if (group == 0 || group == node_id) {
    list<struct Influence*>::iterator inf_it;
    for (inf_it = influenced_by->begin(); inf_it != influenced_by->end(); ) {//inf_it++){
      list<struct Effect*>::iterator effect = (*inf_it)->effect;
      list<struct Influence*>::iterator tmp;
      Effect *f = *effect;
      (*effect)->node->effect_on->erase(effect);
      hs_free((*inf_it)->comm_hs);
      if (!(*inf_it)->ports.shared) free((*inf_it)->ports.list);
      free(*inf_it);
      tmp = inf_it++;
      influenced_by->erase(tmp);
      free(f);
    }
    // remove itself from all rules influenced by this rule and their flows
    list<Effect *>::iterator eff_it;
    list<Flow*>::iterator src_it;
    for (eff_it = effect_on->begin(); eff_it != effect_on->end(); ) {
      list<struct Influence*>::iterator influence = (*eff_it)->influence;
      list<struct Effect*>::iterator tmp;
      FirewallRuleNode *n = (FirewallRuleNode *)(*influence)->node;
      hs *comm_hs = (*influence)->comm_hs;
      List_t ports = (*influence)->ports;
      free(*influence);
      n->influenced_by->erase(influence);
      for (src_it = n->source_flow.begin(); src_it != n->source_flow.end();
          src_it++) {
        if (elem_in_sorted_list((*src_it)->in_port, ports)) {
          n->process_src_flow_at_location(src_it,(array_t *)NULL);
        }
      }
      hs_free(comm_hs);
      if (!ports.shared) free(ports.list);
      free(*eff_it);
      tmp = eff_it++;
      effect_on->erase(tmp);
    }
  }
}

string FirewallRuleNode::rule_to_str() {
  stringstream result;
  char *s;
  s = hs_to_str(fw_match);
  result << "Match: " << s;
  free(s);
  result << ", iPorts: " << list_to_string(input_ports);
  result << ", oPorts: " << list_to_string(output_ports);
  if (group != 0) {
    char buf[70];
    sprintf(buf,"0x%lx",group);
    result << " (group with " << buf << ")";
  }
  return result.str();
}

string FirewallRuleNode::influence_to_str() {
  stringstream result;
  char buf[70];
  char *s;
  result << "Effect On:\n";
  list<Effect *>::iterator eff_it;
  for (eff_it = effect_on->begin(); eff_it != effect_on->end(); eff_it++) {
    list<struct Influence*>::iterator influence = (*eff_it)->influence;
    sprintf(buf,"0x%lx",(*influence)->node->node_id);
    result << "\tRule " << buf << "\n";
  }
  result << "Influenced By:\n";
  list<Influence *>::iterator inf_it;
  for (inf_it = influenced_by->begin(); inf_it != influenced_by->end(); inf_it++) {
    list<struct Effect*>::iterator effect = (*inf_it)->effect;
    sprintf(buf,"0x%lx",(*effect)->node->node_id);
    s = hs_to_str((*inf_it)->comm_hs);
    result << "\tRule " << buf << " (h,p) = [" << s << " , " <<
    list_to_string((*inf_it)->ports) << "]\n";
    free(s);
  }
  return result.str();
}

string FirewallRuleNode::to_string() {
  stringstream result;
  char buf[70];
  result << string(40, '=') << "\n";
  sprintf(buf,"0x%x",table);
  result << string(4, ' ') << "Table: " << buf;
  sprintf(buf,"0x%lx",node_id);
  result << " Firewall Rule: " << buf << "\n";
  result << string(40, '=') << "\n";
  result << rule_to_str() << "\n";
  result << influence_to_str();
  result << pipeline_to_string();
  result << src_flow_to_string();
  return result.str();
}

void FirewallRuleNode::process_src_flow_at_location(list<struct Flow*>::iterator loc,
                                            array_t *change) {
  Flow *f = *loc;
  if (change) {
    if (f->processed_hs == NULL) return;
    hs tmp = {length,{0}};
    hs_add(&tmp,change);
    hs_minus(f->processed_hs, &tmp);
    hs_destroy(&tmp);
  } else {
    if (f->processed_hs) hs_free(f->processed_hs);
    // diff higher priority rules
    list<struct Influence*>::iterator it;
    f->processed_hs = hs_copy_a(f->hs_object);
    for (it = influenced_by->begin(); it != influenced_by->end(); it++) {
      if (!elem_in_sorted_list(f->in_port, (*it)->ports)) continue;
      hs_minus(f->processed_hs, (*it)->comm_hs);
    }
  }
  // compress h.
  // if compress to empty, free f. else process it.
  if (!hs_compact(f->processed_hs)) {
    f->node->absorb_src_flow(loc,true);
    hs_free(f->processed_hs);
    f->processed_hs = NULL;
  } else {
    if (!f->n_flows) f->n_flows = new list< list<struct Flow*>::iterator >();
    repropagate_src_flow_on_pipes(loc,change);
  }
}

void FirewallRuleNode::process_src_flow_at_location(list<struct Flow*>::iterator loc,
                                            hs *change) {
  Flow *f = *loc;
  if (change) {
    if (f->processed_hs == NULL) return;
    hs_minus(f->processed_hs, change);
  } else {
    if (f->processed_hs) hs_free(f->processed_hs);
    // diff higher priority rules
    list<struct Influence*>::iterator it;
    f->processed_hs = hs_copy_a(f->hs_object);
    for (it = influenced_by->begin(); it != influenced_by->end(); it++) {
      if (!elem_in_sorted_list(f->in_port, (*it)->ports)) continue;
      hs_minus(f->processed_hs, (*it)->comm_hs);
    }
  }
  // compress h.
  // if compress to empty, free f. else process it.
  if (!hs_compact(f->processed_hs)) {
    f->node->absorb_src_flow(loc,true);
    hs_free(f->processed_hs);
    f->processed_hs = NULL;
  } else {
    if (!f->n_flows) f->n_flows = new list< list<struct Flow*>::iterator >();
    repropagate_src_flow_on_pipes(loc,change);
  }
}

void FirewallRuleNode::subtract_infuences_from_flows() {
  /*
   * when a new rule is added, this function is called to updat the lower
   * priority flows.
   */
  list<Effect*>::iterator eff_it;
  list<Flow*>::iterator src_it;
  for (eff_it = effect_on->begin(); eff_it != effect_on->end(); eff_it++) {
    FirewallRuleNode *n = (FirewallRuleNode *)(*(*eff_it)->influence)->node;
    for (src_it = n->source_flow.begin(); src_it != n->source_flow.end();
        src_it++) {
      if (elem_in_sorted_list((*src_it)->in_port,
                              (*(*eff_it)->influence)->ports)) {
        n->process_src_flow_at_location(src_it,
                                        (*(*eff_it)->influence)->comm_hs);
      }
    }
  }
}

list<struct Influence*>::iterator FirewallRuleNode::set_influence_by(Influence *inf) {
  this->influenced_by->push_front(inf);
  return this->influenced_by->begin();
}

list<struct Effect*>::iterator FirewallRuleNode::set_effect_on(Effect *eff) {
  this->effect_on->push_front(eff);
  return this->effect_on->begin();
}

int FirewallRuleNode::count_effects() {
  return this->effect_on->size();
}

int FirewallRuleNode::count_influences() {
  return this->influenced_by->size();
}

void FirewallRuleNode::repropagate_src_flow_on_pipes(list<struct Flow*>::iterator s_flow,
    array_t *change) {

//  hs *chg = (hs *)change;

  set<Pipeline*> pipe_hash_set;
  list<std::list<struct Flow*>::iterator>::iterator nit,tmp_nit;
  hs *h = NULL;
  if ((*s_flow)->n_flows) {
    for (nit = (*s_flow)->n_flows->begin();
        nit != (*s_flow)->n_flows->end(); /*do nothing */) {
      Flow *next_flow = **nit;
      if (change) {
        array_t *piped = array_isect_a(  //change through pipe
              next_flow->pipe->pipe_array,change,length);
        if (piped) {
          hs_diff(next_flow->hs_object, piped);
          next_flow->node->process_src_flow_at_location(*nit,piped);
          free(piped);
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
          h = NULL;
          nit++;
        } else { // then this flow no longer propagate on this path. absorb it.
          next_flow->node->absorb_src_flow(*nit,false);
          tmp_nit = nit;
          nit++;
          (*s_flow)->n_flows->erase(tmp_nit);
        }
      }
    }
  }
  if (change) return;

  list<Pipeline *>::iterator it;
  for (it = next_in_pipeline.begin(); it != next_in_pipeline.end(); it++) {
    if (pipe_hash_set.count(*it) > 0) continue;  //skip pipes visited above.
    if (is_output_layer && should_block_flow(*s_flow,(*it)->local_port))
      continue;
    if (!h) h = (hs *)malloc(sizeof *h);
    if (hs_isect_arr(h, (*s_flow)->processed_hs, (*it)->pipe_array)) {
      // create a new flow struct to pass to next node in pipeline
      Flow *next_flow = (Flow *)malloc(sizeof *next_flow);
      next_flow->node = (*(*it)->r_pipeline)->node;
      next_flow->hs_object = h;
      next_flow->in_port = (*(*it)->r_pipeline)->local_port;
      next_flow->pipe = *it;
      next_flow->p_flow = s_flow;
      next_flow->n_flows = NULL;
      // request next node to process this flow
      (*(*it)->r_pipeline)->node->process_src_flow(next_flow);
      h = NULL;
    }
  }
  free(h);
}

void FirewallRuleNode::repropagate_src_flow_on_pipes(list<struct Flow*>::iterator s_flow,
    hs *change) {

  set<Pipeline*> pipe_hash_set;
  list<std::list<struct Flow*>::iterator>::iterator nit,tmp_nit;
  hs *h = NULL;
  if ((*s_flow)->n_flows) {
    for (nit = (*s_flow)->n_flows->begin();
        nit != (*s_flow)->n_flows->end(); /*do nothing */) {
      Flow *next_flow = **nit;
      if (change) {
        hs tmp = {length,{0}};
        hs_add(&tmp,next_flow->pipe->pipe_array);
        hs *piped = hs_isect_a(  //change through pipe
              &tmp,change);
        hs_destroy(&tmp);
        if (piped && piped->list.used == 1 && piped->list.diff->used == 0) {
          hs_minus(next_flow->hs_object, piped);
          next_flow->node->process_src_flow_at_location(*nit,piped->list.elems[0]);
          free(piped);
        }
        if (next_flow->node->get_type() == FIREWALL_RULE)
            ((FirewallRuleNode *)next_flow->node)->process_src_flow_at_location(*nit,change);
        else {
            // TODO: stabilize and proper error handling... look if this really works in all cases
            next_flow->node->process_src_flow_at_location(*nit,change->list.elems[0]);
        }
        nit++;
      } else {
        pipe_hash_set.insert(next_flow->pipe);
        if (!h) h = (hs *)malloc(sizeof *h);
        if (hs_isect_arr(
            h, (*s_flow)->processed_hs, next_flow->pipe->pipe_array)
            ){  // update the hs_object of next flow and ask it to reprocess it.
          hs_free(next_flow->hs_object);
          next_flow->hs_object = h;
          if (next_flow->node->get_type() == FIREWALL_RULE)
            ((FirewallRuleNode *)next_flow->node)->process_src_flow_at_location(*nit,change);
          else
            // TODO: same as above
            next_flow->node->process_src_flow_at_location(*nit,change->list.elems[0]);
          h = NULL;
          nit++;
        } else { // then this flow no longer propagate on this path. absorb it.
          next_flow->node->absorb_src_flow(*nit,false);
          tmp_nit = nit;
          nit++;
          (*s_flow)->n_flows->erase(tmp_nit);
        }
      }
    }
  }
  if (change) return;

  list<Pipeline *>::iterator it;
  for (it = next_in_pipeline.begin(); it != next_in_pipeline.end(); it++) {
    if (pipe_hash_set.count(*it) > 0) continue;  //skip pipes visited above.
    if (is_output_layer && should_block_flow(*s_flow,(*it)->local_port))
      continue;
    if (!h) h = (hs *)malloc(sizeof *h);
    if (hs_isect_arr(h, (*s_flow)->processed_hs, (*it)->pipe_array)) {
      // create a new flow struct to pass to next node in pipeline
      Flow *next_flow = (Flow *)malloc(sizeof *next_flow);
      next_flow->node = (*(*it)->r_pipeline)->node;
      next_flow->hs_object = h;
      next_flow->in_port = (*(*it)->r_pipeline)->local_port;
      next_flow->pipe = *it;
      next_flow->p_flow = s_flow;
      next_flow->n_flows = NULL;
      // request next node to process this flow
      (*(*it)->r_pipeline)->node->process_src_flow(next_flow);
      h = NULL;
    }
  }
  free(h);
}
