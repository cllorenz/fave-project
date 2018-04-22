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

#include "net_plumber.h"
#include <stdio.h>
#include <assert.h>
#include <stdlib.h>
#include <sstream>
#include <fstream>
#include "net_plumber_utils.h"
#include "../jsoncpp/json/json.h"
#include "policy_checker.h"
extern "C" {
  #include "../headerspace/array.h"
}

using namespace std;
using namespace log4cxx;
using namespace net_plumber;

LoggerPtr NetPlumber::logger(Logger::getLogger("NetPlumber"));
LoggerPtr loop_logger(Logger::getLogger("DefaultLoopDetectionLogger"));
LoggerPtr blackhole_logger(Logger::getLogger("DefaultBlackholeDetectionLogger"));
LoggerPtr unreach_logger(Logger::getLogger("DefaultUnreachDetectionLogger"));
LoggerPtr shadow_logger(Logger::getLogger("DefaultShadowDetectionLogger"));
#ifdef PIPE_SLICING
LoggerPtr slice_logger(Logger::getLogger("DefaultSliceLogger"));
#endif

string flow_to_str(Flow *f) {
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

void default_loop_callback(NetPlumber *N, Flow *f, void *data) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Loop Detected: after event " << get_event_name(e.type) <<
      " (ID1: " << e.id1 << ")" << endl << flow_to_str(f);
  LOG4CXX_FATAL(loop_logger,error_msg.str());
}

void default_blackhole_callback(NetPlumber *N, Flow *f, void *data) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Black Hole Detected: after event " << get_event_name(e.type) <<
      " (ID1: " << e.id1 << ")";
  LOG4CXX_FATAL(blackhole_logger,error_msg.str());
}

void default_rule_unreach_callback(NetPlumber *N, Flow *f, void *data) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Unreachable Rule Detected: after event " <<
    get_event_name(e.type) << " (ID1: " << e.id1 << ")";
  LOG4CXX_FATAL(unreach_logger,error_msg.str());
}

void default_rule_shadow_callback(NetPlumber *N, Flow *f, void *data) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Shadowed Rule Detected: after event " <<
    get_event_name(e.type) << " (ID1: " << e.id1 << ")";
  LOG4CXX_FATAL(shadow_logger,error_msg.str());
}

#ifdef PIPE_SLICING
void default_slice_overlap_callback(NetPlumber *N, Flow *f, void *data) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Slice Overlap Detected: after event " << get_event_name(e.type) <<
      " (ID1: " << e.id1 << ")";
  LOG4CXX_FATAL(slice_logger,error_msg.str());
}
#endif

#ifdef PIPE_SLICING
void default_slice_leakage_callback(NetPlumber *N, Flow *f, void *data) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Slice Leakage Detected: after event " << get_event_name(e.type) <<
      " (ID1: " << e.id1 << ")";
  LOG4CXX_FATAL(slice_logger,error_msg.str());
}
#endif

string get_event_name(EVENT_TYPE t) {
  switch (t) {
    case(ADD_RULE)          : return "Add Rule";
    case(REMOVE_RULE)       : return "Remove Rule";
    case(ADD_LINK)          : return "Add Link";
    case(REMOVE_LINK)       : return "Remove Link";
    case(ADD_SOURCE)        : return "Add Source";
    case(REMOVE_SOURCE)     : return "Remove Source";
    case(ADD_SINK)          : return "Add Sink";
    case(REMOVE_SINK)       : return "Remove Sink";
    case(START_SOURCE_PROBE): return "Start Source Probe";
    case(STOP_SOURCE_PROBE) : return "Stop Source Probe";
    case(START_SINK_PROBE)  : return "Start Sink Probe";
    case(STOP_SINK_PROBE)   : return "Stop Sink Probe";
    case(ADD_TABLE)         : return "Add Table";
    case(REMOVE_TABLE)      : return "Remove Table";
#ifdef PIPE_SLICING
    case(ADD_SLICE)         : return "Add Slice";
    case(REMOVE_SLICE)      : return "Remove Slice";
#endif
    case(EXPAND): return "Expand"; // not implemented but maybe needed?
    default: return "None";
  }
}

/*
 * * * * * * * * * * * * * *
 * Private Helper Members  *
 * * * * * * * * * * * * * *
 */

void NetPlumber::free_group_memory(uint32_t table, uint64_t group) {
  list<RuleNode*>* rules_list = table_to_nodes[table];
  list<RuleNode*>::iterator it,tmp;
  for ( it=rules_list->begin() ; it != rules_list->end(); ) {
    if ((*it)->group == group) {
      free_rule_memory(*it,false);
      tmp = it; it++;
      rules_list->erase(tmp);
    } else it++;
  }
}

void NetPlumber::free_rule_memory(RuleNode *r, bool remove_from_table) {
  if (remove_from_table) table_to_nodes[r->table]->remove(r);
  id_to_node.erase(r->node_id);
  clear_port_to_node_maps(r);
  delete r;
}

void NetPlumber::free_table_memory(uint32_t table) {
  if (table_to_nodes.count(table) > 0) {
    table_to_last_id.erase(table);
    list<RuleNode*>* rules_list = table_to_nodes[table];
    list<RuleNode*>::iterator it;
    for ( it=rules_list->begin() ; it != rules_list->end(); it++ ) {
      free_rule_memory(*it,false);
    }
    table_to_nodes.erase(table);
    delete rules_list;
    free(table_to_ports[table].list);
    table_to_ports.erase(table);
  } else {
    stringstream error_msg;
    error_msg << "Table " << table << " does not exist. Can't delete it.";
    LOG4CXX_WARN(logger,error_msg.str());
  }
}

void NetPlumber::set_port_to_node_maps(Node *n) {
  for (uint32_t i = 0; i < n->input_ports.size; i++) {
    if (inport_to_nodes.count(n->input_ports.list[i]) == 0) {
      inport_to_nodes[n->input_ports.list[i]] = new list<Node*>(1,n);
    } else {
      inport_to_nodes[n->input_ports.list[i]]->push_back(n);
    }
  }

  for (uint32_t i = 0; i < n->output_ports.size; i++) {
    if (outport_to_nodes.count(n->output_ports.list[i]) == 0) {
      outport_to_nodes[n->output_ports.list[i]] = new list<Node*>(1,n);
    } else {
      outport_to_nodes[n->output_ports.list[i]]->push_back(n);
    }
  }
}

void NetPlumber::clear_port_to_node_maps(Node *n) {
  for (uint32_t i = 0; i < n->input_ports.size; i++) {
    inport_to_nodes[n->input_ports.list[i]]->remove(n);
    if (inport_to_nodes[n->input_ports.list[i]]->size() == 0) {
      delete inport_to_nodes[n->input_ports.list[i]];
      inport_to_nodes.erase(n->input_ports.list[i]);
    }
  }
  for (uint32_t i = 0; i < n->output_ports.size; i++) {
    outport_to_nodes[n->output_ports.list[i]]->remove(n);
    if (outport_to_nodes[n->output_ports.list[i]]->size() == 0) {
      delete outport_to_nodes[n->output_ports.list[i]];
      outport_to_nodes.erase(n->output_ports.list[i]);
    }
  }
}

void NetPlumber::set_table_dependency(RuleNode *r) {
  if (r->group != 0 && r->group != r->node_id) return; //escape non-group-lead
  list<RuleNode*>* rules_list = table_to_nodes[r->table];
  list<RuleNode*>::iterator it;
  bool seen_rule = false;
  bool checked_rs = false;

  struct hs all_hs = {this->length,{0}};
  hs_add(&all_hs,array_create(this->length,BIT_X));

  struct hs aggr_hs = {this->length,{0}};

  for (it=rules_list->begin() ; it != rules_list->end(); it++) {
    if ((*it)->node_id == r->node_id) {

      // check reachability and shadowing
      struct hs rule_hs = {this->length,{0}};
      hs_add(&rule_hs,array_copy((*it)->match,this->length));

      if (hs_is_equal(&all_hs,&aggr_hs)) {
        this->rule_unreach_callback(this,NULL,this->rule_unreach_callback_data);
      } else if (hs_is_sub(&rule_hs,&aggr_hs)) {
        this->rule_shadow_callback(this,NULL,this->rule_shadow_callback_data);
      }

      hs_destroy(&rule_hs);
      checked_rs = true;

      seen_rule = true;
    } else if ((*it)->group != 0 && (*it)->node_id != (*it)->group){
      // escape *it, if *it belongs to a group and is not the lead of the group.
      continue;
    } else {
      // find common input ports
      List_t common_ports = intersect_sorted_lists(r->input_ports,
                                                  (*it)->input_ports);
      if (common_ports.size == 0) continue;
      // find common headerspace
#ifdef FIREWALL_RULES
      hs *common_hs;
      array_t *common_arr;
      bool is_fw = r->get_type() == FIREWALL_RULE;

      if (is_fw)
        common_hs = hs_isect_a(
          ((FirewallRuleNode *)r)->fw_match,
          ((FirewallRuleNode *)(*it))->fw_match
        );
      else
        common_arr = array_isect_a(r->match,(*it)->match,this->length);

      if (!checked_rs && is_fw)
        hs_add_hs(&aggr_hs,hs_copy_a(((FirewallRuleNode *)(*it))->fw_match));
      else if (!checked_rs && !is_fw) hs_add(&aggr_hs,array_copy((*it)->match,this->length));

      if ((is_fw && common_hs == NULL) || (!is_fw && common_arr == NULL)) {
        if (!common_ports.shared) free(common_ports.list);
        continue;
      }
#else
      array_t *common_hs = array_isect_a(r->match,(*it)->match,this->length);

      if (!checked_rs) hs_add(&aggr_hs,array_copy((*it)->match,this->length));

      if (common_hs == NULL) {
        if (!common_ports.shared) free(common_ports.list);
        continue;
      }
#endif
      // add influence
      Influence *inf = (Influence *)malloc(sizeof *inf);
      Effect *eff = (Effect *)malloc(sizeof *eff);
#ifdef FIREWALL_RULES
      if (is_fw)
        inf->comm_hs = common_hs;
      else
        inf->comm_arr = common_arr;
#else
      inf->comm_arr = common_hs;
#endif
      inf->ports = common_ports;

      if (seen_rule) {
        inf->node = (*it);
        eff->node = r;
        eff->influence = (*it)->set_influence_by(inf);
        inf->effect = r->set_effect_on(eff);
      } else {
        inf->node = r;
        eff->node = (*it);
        eff->influence = r->set_influence_by(inf);
        inf->effect = (*it)->set_effect_on(eff);
      }
    }
  }

  hs_destroy(&aggr_hs);
  hs_destroy(&all_hs);
}

void NetPlumber::set_node_pipelines(Node *n) {
  // set n's forward pipelines.
  for (uint32_t i = 0; i < n->output_ports.size; i++) {
    vector<uint32_t> *end_ports = get_dst_ports(n->output_ports.list[i]);
    if (!end_ports) continue;
    for (size_t j = 0; j < end_ports->size(); j++) {
      list<Node*> *potential_next_rules =
          get_nodes_with_inport(end_ports->at(j));
      if (!potential_next_rules) continue;
      list<Node*>::iterator it;
      for (it = potential_next_rules->begin();
           it != potential_next_rules->end(); it++) {
        array_t *pipe_arr;
#ifdef FIREWALL_RULES
        if (n->get_type() == FIREWALL_RULE) {
            hs tmp = {length,{0}};
            if ((*it)->get_type() == FIREWALL_RULE)
                hs_add_hs(&tmp,((FirewallRuleNode *)(*it))->fw_match);
            else
                hs_add(&tmp,array_copy((*it)->match,length));

            hs_isect(&tmp,((FirewallRuleNode *)n)->fw_match);

            if (tmp.list.used == 1)
                pipe_arr = array_copy(tmp.list.elems[0],length);
            else
                pipe_arr = array_create(length,BIT_Z);
            hs_destroy(&tmp);
        }
        else pipe_arr = array_isect_a((*it)->match, n->inv_match, length);
#else
        pipe_arr = array_isect_a((*it)->match,n->inv_match,length);
#endif
        if (pipe_arr) {
          Pipeline *fp = (Pipeline *)malloc(sizeof *fp);
          Pipeline *bp = (Pipeline *)malloc(sizeof *bp);
          fp->local_port = n->output_ports.list[i];
          bp->local_port = end_ports->at(j);
          fp->pipe_array = pipe_arr;
          bp->pipe_array = pipe_arr;
          fp->node = n;
          bp->node = *it;
          bp->r_pipeline = n->add_fwd_pipeline(fp);
          fp->r_pipeline = (*it)->add_bck_pipeline(bp);
#ifdef PIPE_SLICING
          if (!this->add_pipe_to_slices(fp,*it))
            this->slice_leakage_callback(this,NULL,this->slice_leakage_callback_data);
#endif
        }
      }
    }
  }
  // set n's backward pipelines.
  for (uint32_t i = 0; i < n->input_ports.size; i++) {
    vector<uint32_t> *orig_ports = get_src_ports(n->input_ports.list[i]);
    if (!orig_ports) continue;
    for (size_t j = 0; j < orig_ports->size(); j++) {
      list<Node*> *potential_prev_rules =
          get_nodes_with_outport(orig_ports->at(j));
      if (!potential_prev_rules) continue;
      list<Node*>::iterator it;
      for (it = potential_prev_rules->begin();
           it != potential_prev_rules->end(); it++) {
        array_t *pipe_arr;
#ifdef FIREWALL_RULES
        if (n->get_type() == FIREWALL_RULE) {
            hs tmp = {length,{0}};
            if ((*it)->get_type() == FIREWALL_RULE)
                hs_add_hs(&tmp,((FirewallRuleNode *)(*it))->fw_match);
            else
                hs_add(&tmp,array_copy((*it)->match,length));

            hs_isect(&tmp,((FirewallRuleNode *)n)->fw_match);

            if (tmp.list.used == 1)
                pipe_arr = array_copy(tmp.list.elems[0],length);
            else
                pipe_arr = array_create(length,BIT_Z);
            hs_destroy(&tmp);
        }
        else pipe_arr = array_isect_a((*it)->inv_match, n->match, length);
#else
        pipe_arr = array_isect_a((*it)->inv_match,n->match,length);
#endif

        if (pipe_arr) {
          Pipeline *fp = (Pipeline *)malloc(sizeof *fp);
          Pipeline *bp = (Pipeline *)malloc(sizeof *bp);
          fp->local_port = orig_ports->at(j);
          bp->local_port = n->input_ports.list[i];
          fp->pipe_array = pipe_arr;
          bp->pipe_array = pipe_arr;
          fp->node = *it;
          bp->node = n;
          bp->r_pipeline = (*it)->add_fwd_pipeline(fp);
          fp->r_pipeline = n->add_bck_pipeline(bp);
#ifdef PIPE_SLICING
          if (!this->add_pipe_to_slices(fp,n))
            this->slice_leakage_callback(this,NULL,this->slice_leakage_callback_data);
#endif
        }
      }
    }
  }
}
#ifdef PIPE_SLICING
/* returns whether no leak is detected */
bool NetPlumber::check_pipe_for_slice_leakage(struct Pipeline *pipe, Node *next) {
    std::list<struct Pipeline *> n = next->next_in_pipeline;
    std::list<struct Pipeline *>::const_iterator p;
    for (p = n.begin(); p != n.end(); p++)
        if ((*p)->net_space_id != pipe->net_space_id) return false;

    return true;
}

#endif

#ifdef PIPE_SLICING
/* returns whether the pipe is successfully to a slice (without leakage) */
bool NetPlumber::add_pipe_to_slices(struct Pipeline *pipe, Node *next) {
    std::map<uint64_t,struct Slice*>::iterator s;

    struct hs *tmp = hs_create(this->length);
    hs_add(tmp,array_copy(pipe->pipe_array,this->length));

    for (s = this->slices.begin(); s != this->slices.end(); s++) {
        uint64_t net_space_id = s->first;
        struct Slice *slice = s->second;

        // if the pipe belongs to a slice update the pipe and add it to the slice
        if (hs_is_sub_eq(tmp,slice->net_space)) {
            hs_free(tmp);
            pipe->net_space_id = net_space_id;
            slice->pipes->push_front(pipe);
            pipe->r_slice = slice->pipes->begin();
            return check_pipe_for_slice_leakage(pipe, next);
        }
    }
    hs_free(tmp);
    return false;
}
#endif

#ifdef PIPE_SLICING
void NetPlumber::remove_pipe_from_slices(struct Pipeline *pipe) {
    if (!this->slices[pipe->net_space_id]) return;
    struct Slice *slice = this->slices[pipe->net_space_id];
    slice->pipes->erase(pipe->r_slice);
}
#endif

/*
 * * * * * * * * * * * * *
 * Public Class Members  *
 * * * * * * * * * * * * *
 */

NetPlumber::NetPlumber(size_t length) : length(length), last_ssp_id_used(0) {
  this->last_event.type = None;
  this->loop_callback = default_loop_callback;
  this->loop_callback_data = NULL;
  this->blackhole_callback = default_blackhole_callback;
  this->blackhole_callback_data = NULL;
  this->rule_unreach_callback = default_rule_unreach_callback;
  this->rule_unreach_callback_data = NULL;
  this->rule_shadow_callback = default_rule_shadow_callback;
  this->rule_shadow_callback_data = NULL;
#ifdef PIPE_SLICING
  struct Slice *slice = (struct Slice *)malloc(sizeof(*slice));
  slice->net_space_id = 0;
  slice->net_space = hs_create(length);
  hs_add(slice->net_space,array_create(this->length,BIT_X));
  slice->pipes = new std::list<struct Pipeline *>();
  this->slices[0] = slice;
  this->slice_overlap_callback = default_slice_overlap_callback;
  this->slice_overlap_callback_data = NULL;
  this->slice_leakage_callback = default_slice_leakage_callback;
  this->slice_leakage_callback_data = NULL;
#endif
#ifdef POLICY_PROBES
  this->policy_checker = new PolicyChecker(length);
#endif
}

NetPlumber::~NetPlumber() {
  list<Node*>::iterator p_it;
  for (p_it = probes.begin(); p_it != probes.end(); p_it++) {
    if ((*p_it)->get_type() == SOURCE_PROBE) {
      ((SourceProbeNode*)(*p_it))->stop_probe();
    } else if ((*p_it)->get_type() == POLICY_PROBE) {
      ((PolicyProbeNode*)(*p_it))->stop_probe();
    }
    clear_port_to_node_maps(*p_it);
    delete *p_it;
  }
  map< uint32_t, std::vector<uint32_t>* >::iterator it;
  for (it = topology.begin(); it != topology.end(); it++ ){
    delete (*it).second;
  }
  for (it = inv_topology.begin(); it != inv_topology.end(); it++ ){
    delete (*it).second;
  }
  map< uint32_t,std::list<RuleNode*>* >::iterator it2,tmp2;
  for (it2 = table_to_nodes.begin(); it2 != table_to_nodes.end(); ){
    tmp2 = it2;
    tmp2++;
    free_table_memory((*it2).first);
    it2 = tmp2;
  }
  list<Node*>::iterator s_it;
  for (s_it = flow_nodes.begin(); s_it != flow_nodes.end(); s_it++) {
    clear_port_to_node_maps(*s_it);
    delete *s_it;
  }
#ifdef POLICY_PROBES
  delete policy_checker;
#endif
}

Event NetPlumber::get_last_event() {
  return this->last_event;
}

void NetPlumber::set_last_event(Event e) {
  this->last_event = e;
}

void NetPlumber::add_link(uint32_t from_port, uint32_t to_port) {
  this->last_event.type = ADD_LINK;
  this->last_event.id1 = from_port;
  this->last_event.id2 = to_port;
  // topology update
  if (topology.count(from_port) == 0) {
    topology[from_port] = new vector<uint32_t>(1,to_port);
  } else {
    topology[from_port]->push_back(to_port);
  }
  if (inv_topology.count(to_port) == 0) {
    inv_topology[to_port] = new vector<uint32_t>(1,from_port);
  } else {
    inv_topology[to_port]->push_back(from_port);
  }

  // pipeline update
  list<Node*> *src_rules = this->get_nodes_with_outport(from_port);
  list<Node*> *dst_rules = this->get_nodes_with_inport(to_port);
  list<Node*>::iterator src_it,dst_it;
  if (src_rules && dst_rules) {
    for (src_it = src_rules->begin(); src_it != src_rules->end(); src_it++) {
      for (dst_it = dst_rules->begin(); dst_it != dst_rules->end(); dst_it++) {
        array_t *pipe_arr = array_isect_a((*src_it)->inv_match,
                                         (*dst_it)->match,
                                         length);
        if (pipe_arr) {
          Pipeline *fp = (Pipeline *)malloc(sizeof *fp);
          Pipeline *bp = (Pipeline *)malloc(sizeof *bp);
          fp->local_port = from_port;
          bp->local_port = to_port;
          fp->pipe_array = pipe_arr;
          bp->pipe_array = pipe_arr;
          fp->node = *src_it;
          bp->node = *dst_it;
          bp->r_pipeline = (*src_it)->add_fwd_pipeline(fp);
          fp->r_pipeline = (*dst_it)->add_bck_pipeline(bp);
          (*src_it)->propagate_src_flows_on_pipe(bp->r_pipeline);
#ifdef PIPE_SLICING
          if (!this->add_pipe_to_slices(fp,*dst_it))
            this->slice_leakage_callback(this,NULL,this->slice_leakage_callback_data);
#endif
        }
      }
    }
  }
}

void NetPlumber::remove_link(uint32_t from_port, uint32_t to_port) {
  this->last_event.type = REMOVE_LINK;
  this->last_event.id1 = from_port;
  this->last_event.id2 = to_port;
  if (topology.count(from_port) == 0 || inv_topology.count(to_port) == 0) {
    stringstream error_msg;
    error_msg << "Link " << from_port << "-->" << to_port <<
        " does not exist. Can't remove it.";
    LOG4CXX_ERROR(logger,error_msg.str());
  } else {
    // remove plumbing
    list<Node*> *src_rules = this->get_nodes_with_outport(from_port);
    list<Node*> *dst_rules = this->get_nodes_with_inport(to_port);
    list<Node*>::iterator src_it;
    if (src_rules && dst_rules) {
      for (src_it = src_rules->begin(); src_it != src_rules->end(); src_it++) {
        (*src_it)->remove_link_pipes(from_port,to_port);
      }
    }

    // update topology and inv_topology
    vector<uint32_t>::iterator it;
    vector<uint32_t> *v = topology[from_port];
    vector<uint32_t> *v_inv = inv_topology[to_port];
    for (it = v->begin(); it != v->end(); it++) {
      if ((*it) == to_port) {
        v->erase(it);
        break;
      }
    }
    for (it = v_inv->begin(); it != v_inv->end(); it++) {
      if ((*it) == to_port) {
        v->erase(it);
        break;
      }
    }
  }
}

vector<uint32_t> *NetPlumber::get_dst_ports(uint32_t src_port) {
  if (topology.count(src_port) == 0) {
    return NULL;
  } else {
    return topology[src_port];
  }
}

vector<uint32_t> *NetPlumber::get_src_ports(uint32_t dst_port) {
  if (inv_topology.count(dst_port) == 0) {
    return NULL;
  } else {
    return inv_topology[dst_port];
  }
}

void NetPlumber::print_topology() {
  map< uint32_t, std::vector<uint32_t>* >::iterator it;
  for (it = topology.begin(); it != topology.end(); it++ ){
    printf("%u --> ( ",(*it).first);
    for (size_t i = 0; i < (*it).second->size(); i++) {
      printf("%u ",(*it).second->at(i));
    }
    printf(")\n");
  }
}

void NetPlumber::add_table(uint32_t id, List_t ports) {
  this->last_event.type = ADD_TABLE;
  this->last_event.id1 = id;
  assert(table_to_nodes.count(id) == table_to_last_id.count(id));
  if (table_to_nodes.count(id) == 0 && id > 0) {
    ports.shared = true;

    table_to_nodes[id] = new list<RuleNode*>();
    table_to_ports[id] = ports;
    table_to_last_id[id] = 0l;
    return;
  } else if (id == 0) {
    LOG4CXX_ERROR(logger,"Can not create table with ID 0. ID should be > 0.");
  } else {
    stringstream error_msg;
    error_msg << "Table " << id << " already exist. Can't add it again.";
    LOG4CXX_ERROR(logger,error_msg.str());
  }
  free(ports.list);
}

void NetPlumber::remove_table(uint32_t id) {
  this->last_event.type = REMOVE_TABLE;
  this->last_event.id1 = id;
  free_table_memory(id);
}

List_t NetPlumber::get_table_ports(uint32_t id) {
  return this->table_to_ports[id];
}

void NetPlumber::print_table(uint32_t id) {
  printf("%s\n",string(40,'@').c_str());
  printf("%sTable: 0x%x\n",string(4, ' ').c_str(),id);
  printf("%s\n",string(40,'@').c_str());
  list<RuleNode*>* rules_list = table_to_nodes[id];
  list<RuleNode*>::iterator it;
  List_t ports = this->table_to_ports[id];
  printf("Ports: %s\n",list_to_string(ports).c_str());
  printf("Rules:\n");
  for ( it=rules_list->begin() ; it != rules_list->end(); it++ ) {
    printf("%s\n",(*it)->to_string().c_str());
  }
}

uint64_t NetPlumber::_add_rule(uint32_t table,int index,
                               bool group, uint64_t gid,
                               List_t in_ports, List_t out_ports,
                               array_t* match, array_t *mask, array_t* rw) {
  if (table_to_nodes.count(table) > 0) {
    table_to_last_id[table] += 1;
    uint64_t id = table_to_last_id[table] + ((uint64_t)table << 32) ;
    if (in_ports.size == 0) in_ports = table_to_ports[table];
    RuleNode *r;
    if (!group || !gid) { //first rule in group or no group
      if (!group) r = new RuleNode(this, length, id, table, in_ports, out_ports,
                                   match, mask, rw);
      else r = new RuleNode(this, length, id, table, id, in_ports, out_ports,
                            match, mask, rw);
      this->id_to_node[id] = r;
      if (index < 0 || index >= (int)this->table_to_nodes[table]->size()) {
        this->table_to_nodes[table]->push_back(r);
      } else {
        list<RuleNode*>::iterator it = table_to_nodes[table]->begin();
        for (int i=0; i < index; i++, it++);
        this->table_to_nodes[table]->insert(it,r);
      }
      this->last_event.type = ADD_RULE;
      this->last_event.id1 = id;
      this->set_port_to_node_maps(r);
      this->set_table_dependency(r);
      this->set_node_pipelines(r);
      r->subtract_infuences_from_flows();
      r->process_src_flow(NULL);

    } else if (id_to_node.count(gid) > 0 &&
          ((RuleNode*)id_to_node[gid])->group == gid) {

      RuleNode *rg = (RuleNode*)this->id_to_node[gid];
      table = rg->table;
      r = new RuleNode(this, length, id, table, gid, in_ports, out_ports,
                       match, mask, rw);
      this->id_to_node[id] = r;
      // insert rule after its lead group rule
      list<RuleNode*>::iterator it = table_to_nodes[table]->begin();
      for (; (*it)->node_id != gid; it++);
      this->table_to_nodes[table]->insert(++it,r);
      this->last_event.type = ADD_RULE;
      this->last_event.id1 = id;
      // set port maps
      this->set_port_to_node_maps(r);
      //The influences of this rule is the same as lead rule in the group.
      r->effect_on = rg->effect_on;
      r->influenced_by = rg->influenced_by;
      this->set_node_pipelines(r);
      // no need to subtract influences. it has already taken care of
      r->process_src_flow(NULL);

    } else {
      free(in_ports.list);free(out_ports.list);free(match);free(mask);free(rw);
      stringstream error_msg;
      error_msg << "Group " << group << " does not exist. Can't add rule to it."
          << "Ignoring add new rule request.";
      LOG4CXX_WARN(logger,error_msg.str());
      return 0;
    }
    return id;
  } else {
    free(in_ports.list);free(out_ports.list);free(match);free(mask);free(rw);
    stringstream error_msg;
    error_msg << "trying to add a rule to a non-existing table (id: " << table
        << "). Ignored.";
    LOG4CXX_ERROR(logger,error_msg.str());
    return 0;
  }
}

#ifdef FIREWALL_RULES
uint64_t NetPlumber::_add_fw_rule(uint32_t table,int index,
                               bool group, uint64_t gid,
                               List_t in_ports, List_t out_ports,
                               hs *fw_match) {
  if (table_to_nodes.count(table) > 0) {
    table_to_last_id[table] += 1;
    uint64_t id = table_to_last_id[table] + ((uint64_t)table << 32) ;
    if (in_ports.size == 0) in_ports = table_to_ports[table];
    FirewallRuleNode *r;
    if (!group || !gid) { //first rule in group or no group
      if (!group) r = new FirewallRuleNode(this, length, id, table, in_ports, out_ports,
                                   fw_match);
      else r = new FirewallRuleNode(this, length, id, table, id, in_ports, out_ports,
                            fw_match);
      this->id_to_node[id] = r;
      if (index < 0 || index >= (int)this->table_to_nodes[table]->size()) {
        this->table_to_nodes[table]->push_back(r);
      } else {
        list<RuleNode*>::iterator it = table_to_nodes[table]->begin();
        for (int i=0; i < index; i++, it++);
        this->table_to_nodes[table]->insert(it,r);
      }
      this->last_event.type = ADD_FW_RULE;
      this->last_event.id1 = id;
      this->set_port_to_node_maps(r);
      this->set_table_dependency(r);
      this->set_node_pipelines(r);
      r->subtract_infuences_from_flows();
      r->process_src_flow(NULL);

    } else if (id_to_node.count(gid) > 0 &&
          ((FirewallRuleNode*)id_to_node[gid])->group == gid) {

      FirewallRuleNode *rg = (FirewallRuleNode*)this->id_to_node[gid];
      table = rg->table;
      r = new FirewallRuleNode(this, length, id, table, gid, in_ports, out_ports,
                       fw_match);
      this->id_to_node[id] = r;
      // insert rule after its lead group rule
      list<RuleNode*>::iterator it = table_to_nodes[table]->begin();
      for (; (*it)->node_id != gid; it++);
      this->table_to_nodes[table]->insert(++it,r);
      this->last_event.type = ADD_FW_RULE;
      this->last_event.id1 = id;
      // set port maps
      this->set_port_to_node_maps(r);
      //The influences of this rule is the same as lead rule in the group.
      r->effect_on = rg->effect_on;
      r->influenced_by = rg->influenced_by;
      this->set_node_pipelines(r);
      // no need to subtract influences. it has already taken care of
      r->process_src_flow(NULL);

    } else {
      free(in_ports.list);free(out_ports.list);free(fw_match);
      stringstream error_msg;
      error_msg << "Group " << group << " does not exist. Can't add rule to it."
          << "Ignoring add new rule request.";
      LOG4CXX_WARN(logger,error_msg.str());
      return 0;
    }
    return id;
  } else {
    free(in_ports.list);free(out_ports.list);free(fw_match);
    stringstream error_msg;
    error_msg << "trying to add a rule to a non-existing table (id: " << table
        << "). Ignored.";
    LOG4CXX_ERROR(logger,error_msg.str());
    return 0;
  }
}

uint64_t NetPlumber::add_fw_rule(uint32_t table,int index, List_t in_ports,
            List_t out_ports, hs *fw_match) {

  if (table_is_firewall.find(table) != table_is_firewall.end() &&
      !table_is_firewall[table] &&
      table_to_nodes[table]->size() > 0)
  {
      stringstream error_msg;
      error_msg << "trying to add a firewall rule to a non-firewall table (id: "
        << table << "). Ignored.";
      LOG4CXX_ERROR(logger,error_msg.str());
      return 0;
  }

  table_is_firewall[table] = true;

  return _add_fw_rule(table,index,false,0,in_ports,out_ports,fw_match);
}

uint64_t NetPlumber::add_fw_rule_to_group(uint32_t table,int index, List_t in_ports
                           ,List_t out_ports,hs *fw_match, uint64_t group) {
  if (table_is_firewall.find(table) != table_is_firewall.end() &&
      !table_is_firewall[table] &&
      table_to_nodes[table]->size() > 0)
  {
      stringstream error_msg;
      error_msg << "trying to add a firewall rule to a non-firewall table (id: "
        << table << "). Ignored.";
      LOG4CXX_ERROR(logger,error_msg.str());
      return 0;
  }

  table_is_firewall[table] = true;

  return _add_fw_rule(table,index,true,group,in_ports,out_ports,fw_match);
}

void NetPlumber::remove_fw_rule(uint64_t rule_id) {
  if (id_to_node.count(rule_id) > 0 && id_to_node[rule_id]->get_type() == FIREWALL_RULE){
    this->last_event.type = REMOVE_FW_RULE;
    this->last_event.id1 = rule_id;
    FirewallRuleNode *r = (FirewallRuleNode *)id_to_node[rule_id];
    if (r->group == 0) free_rule_memory(r);
    else free_group_memory(r->table,r->group);
  } else {
    stringstream error_msg;
    error_msg << "Rule " << rule_id << " does not exist. Can't delete it.";
    LOG4CXX_WARN(logger,error_msg.str());
  }
}
#endif

uint64_t NetPlumber::add_rule(uint32_t table,int index, List_t in_ports,
            List_t out_ports, array_t* match, array_t *mask, array_t* rw) {
#ifdef FIREWALL_RULES
  if (table_is_firewall.find(table) != table_is_firewall.end() &&
      table_is_firewall[table] &&
      table_to_nodes[table]->size() > 0)
  {
      stringstream error_msg;
      error_msg << "trying to add a non-firewall rule to a firewall table (id: "
        << table << "). Ignored.";
      LOG4CXX_ERROR(logger,error_msg.str());
      return 0;
  }

  table_is_firewall[table] = false;
#endif

  return _add_rule(table,index,false,0,in_ports,out_ports,match,mask,rw);
}

uint64_t NetPlumber::add_rule_to_group(uint32_t table,int index, List_t in_ports
                           ,List_t out_ports, array_t* match, array_t *mask,
                           array_t* rw, uint64_t group) {
#ifdef FIREWALL_RULES
  if (table_is_firewall.find(table) != table_is_firewall.end() &&
      table_is_firewall[table] &&
      table_to_nodes[table]->size() > 0)
  {
      stringstream error_msg;
      error_msg << "trying to add a non-firewall rule to a firewall table (id: "
        << table << "). Ignored.";
      LOG4CXX_ERROR(logger,error_msg.str());
      return 0;
  }

  table_is_firewall[table] = false;
#endif
  return _add_rule(table,index,true,group,in_ports,out_ports,match,mask,rw);
}

//expand(int length); length is the number if octets of the vector.
//"xxxxxxxx" is length 1
//"xxxxxxxx xxxxxxxx" is length 2 and so on
//|| z=00 1=10 0=01 x=11
//length of n equals 2n bytes of memory
size_t NetPlumber::expand(size_t length) {
	if (length > this->length) {
		for (
            std::map<uint64_t,Node*>::iterator it_nodes = id_to_node.begin() ;
            it_nodes != id_to_node.end();
            ++it_nodes
        ) {//should contain all flows, probes and rules
            it_nodes->second->enlarge(length);
		}
		this->length = length;
	}
	return this->length;
}

void NetPlumber::remove_rule(uint64_t rule_id) {
  if (id_to_node.count(rule_id) > 0 && id_to_node[rule_id]->get_type() == RULE){
    this->last_event.type = REMOVE_RULE;
    this->last_event.id1 = rule_id;
    RuleNode *r = (RuleNode *)id_to_node[rule_id];
    if (r->group == 0) free_rule_memory(r);
    else free_group_memory(r->table,r->group);
  } else {
    stringstream error_msg;
    error_msg << "Rule " << rule_id << " does not exist. Can't delete it.";
    LOG4CXX_WARN(logger,error_msg.str());
  }
}

uint64_t NetPlumber::add_source(hs *hs_object, List_t ports) {
  uint64_t node_id = (uint64_t)(++last_ssp_id_used);
  SourceNode *s = new SourceNode(this, length, node_id, hs_object, ports);
  this->id_to_node[node_id] = s;
  this->flow_nodes.push_back(s);
  this->last_event.type = ADD_SOURCE;
  this->last_event.id1 = node_id;
  this->set_port_to_node_maps(s);
  this->set_node_pipelines(s);
  s->process_src_flow(NULL);
  return node_id;
}

void NetPlumber::remove_source(uint64_t id) {
  if (id_to_node.count(id) > 0 && id_to_node[id]->get_type() == SOURCE) {
    this->last_event.type = REMOVE_SOURCE;
    this->last_event.id1 = id;
    SourceNode *s = (SourceNode *)id_to_node[id];
    id_to_node.erase(s->node_id);
    flow_nodes.remove(s);
    clear_port_to_node_maps(s);
    delete s;
  } else {
    stringstream error_msg;
    error_msg << "Source Node " << id << " does not exist. Can't delete it.";
    LOG4CXX_WARN(logger,error_msg.str());
  }
}

uint64_t NetPlumber::
add_source_probe(List_t ports, PROBE_MODE mode, Condition *filter,
                 Condition *condition, src_probe_callback_t probe_callback,
                 void *callback_data){
  uint64_t node_id = (uint64_t)(++last_ssp_id_used);
  SourceProbeNode* p = new SourceProbeNode(this, length, node_id, mode,ports,
                                           filter, condition,
                                           probe_callback, callback_data);
  this->id_to_node[node_id] = p;
  this->probes.push_back(p);
  this->last_event.type = START_SOURCE_PROBE;
  this->last_event.id1 = node_id;
  this->set_port_to_node_maps(p);
  this->set_node_pipelines(p);
  p->process_src_flow(NULL);
  p->start_probe();
  return node_id;
}

void NetPlumber::remove_source_probe(uint64_t id) {
  if (id_to_node.count(id) > 0 && id_to_node[id]->get_type() == SOURCE_PROBE) {
    this->last_event.type = STOP_SOURCE_PROBE;
    this->last_event.id1 = id;
    SourceProbeNode *p = (SourceProbeNode *)id_to_node[id];
    p->stop_probe();
    id_to_node.erase(p->node_id);
    probes.remove(p);
    clear_port_to_node_maps(p);
    delete p;
  } else {
    stringstream error_msg;
    error_msg << "Probe Node " << id << " does not exist. Can't delete it.";
    LOG4CXX_WARN(logger,error_msg.str());
  }
}

SourceProbeNode *NetPlumber::get_source_probe(uint64_t id) {
  if (id_to_node.count(id) > 0) {
    Node *n = id_to_node[id];
    if (n->get_type() == SOURCE_PROBE) {
      return (SourceProbeNode *)n;
    }
  }
  return NULL;
}

list<Node*>* NetPlumber::get_nodes_with_outport(uint32_t outport) {
  if (outport_to_nodes.count(outport) == 0) {
    return NULL;
  } else {
    return outport_to_nodes[outport];
  }
}

list<Node*>* NetPlumber::get_nodes_with_inport(uint32_t inport) {
  if (inport_to_nodes.count(inport) == 0) {
    return NULL;
  } else {
    return inport_to_nodes[inport];
  }
}

void NetPlumber::print_plumbing_network() {
  map<uint32_t,std::list<RuleNode*>* >::iterator it;
  for (it = table_to_nodes.begin(); it != table_to_nodes.end(); it++) {
    this->print_table((*it).first);
  }
  printf("%s\n",string(40,'@').c_str());
  printf("%sSources and Sinks\n",string(4, ' ').c_str());
  printf("%s\n",string(40,'@').c_str());
  list<Node *>::iterator it2;
  for (it2 = flow_nodes.begin(); it2 != flow_nodes.end(); it2++) {
    printf("%s\n",(*it2)->to_string().c_str());
  }
  printf("%s\n",string(40,'@').c_str());
  printf("%sProbes\n",string(4, ' ').c_str());
  printf("%s\n",string(40,'@').c_str());
  for (it2 = probes.begin(); it2 != probes.end(); it2++) {
    printf("%s\n",(*it2)->to_string().c_str());
  }
}

void NetPlumber::get_pipe_stats(uint64_t node_id,int &fwd_pipeline,
                int &bck_pipeline,int &influence_on, int &influenced_by) {
  if (id_to_node.count(node_id) == 0){
    fwd_pipeline = 0;
    bck_pipeline = 0;
    influence_on = 0;
    influenced_by = 0;
    stringstream error_msg;
    error_msg << "Requested pipe stats for a non-existing node " << node_id
        << ".";
    LOG4CXX_ERROR(logger,error_msg.str());
  } else {
    Node *n = id_to_node[node_id];
    if (n->get_type() == RULE) {
      RuleNode *r = (RuleNode *)n;
      fwd_pipeline = r->count_fwd_pipeline();
      bck_pipeline = r->count_bck_pipeline();
      influence_on = r->count_effects();
      influenced_by = r->count_influences();
    } else if (n->get_type() == SOURCE || n->get_type() == SINK) {
      fwd_pipeline = n->count_fwd_pipeline();
      bck_pipeline = n->count_bck_pipeline();
      influence_on = 0;
      influenced_by = 0;
    } else if (n->get_type() == SOURCE_PROBE || n->get_type() == SINK_PROBE) {
      fwd_pipeline = n->count_fwd_pipeline();
      bck_pipeline = n->count_bck_pipeline();
      influence_on = 0;
      influenced_by = 0;
    } else {
      fwd_pipeline = 0;
      bck_pipeline = 0;
      influence_on = 0;
      influenced_by = 0;
      stringstream error_msg;
      error_msg << "Node with type " << n->get_type() << " doesn't have stats.";
      LOG4CXX_WARN(logger,error_msg.str());
    }
  }
}

void NetPlumber::get_source_flow_stats(uint64_t node_id, int &inc, int &exc) {
  if (id_to_node.count(node_id) == 0){
    inc = 0;
    exc = 0;
    stringstream error_msg;
    error_msg << "Requested source flow stats for a non-existing node " <<
        node_id << ".";
    LOG4CXX_ERROR(logger,error_msg.str());
  } else {
    Node *n = id_to_node[node_id];
    n->count_src_flow(inc,exc);
  }
}

void NetPlumber::save_dependency_graph(string file_name) {
  map<uint64_t,Node*>::iterator it;
  Json::Value root(Json::objectValue);
  Json::Value nodes(Json::arrayValue);
  Json::Value links(Json::arrayValue);
  map<uint64_t,int> ordering;
  int count = 0;
  root["nodes"] = nodes;
  root["links"] = links;
  for (it = id_to_node.begin(); it != id_to_node.end(); it++) {
    stringstream s;
    s << (*it).first;
    Json::Value node(Json::objectValue);
    Json::Value name(Json::stringValue);
    name = s.str();
    node["name"] = name;
    root["nodes"].append(node);
    ordering[(*it).first] = count;
    count++;
  }
  for (it = id_to_node.begin(); it != id_to_node.end(); it++) {
    stringstream s1,s2;
    s1 << (*it).first;
    Node *n = (*it).second;
    list<struct Pipeline*>::iterator pit;
    for (pit = n->next_in_pipeline.begin(); pit != n->next_in_pipeline.end();
         pit++){
      Node *other_n = (*(*pit)->r_pipeline)->node;
      s2 << other_n->node_id;
      Json::Value link(Json::objectValue);
      Json::Value source(Json::intValue);
      Json::Value target(Json::intValue);
      source = ordering[(*it).first];
      target = ordering[other_n->node_id];
      link["source"] = source;
      link["target"] = target;
      root["links"].append(link);
    }
  }

  ofstream jsfile(file_name.c_str());
  jsfile << root;
  jsfile.close();
}

void NetPlumber::dump_plumbing_network(const string dir) {

    /*
     *  {
     *      "topology" : [...]
     *  }
     */
    Json::Value topology_wrapper(Json::objectValue);
    Json::Value topology(Json::arrayValue);

    for (
            std::map< uint32_t, std::vector<uint32_t>* >::iterator s_it = this->topology.begin();
            s_it != this->topology.end();
            s_it++
    ) {
        for (
                std::vector<uint32_t>::iterator d_it = (*s_it).second->begin();
                d_it != (*s_it).second->end();
                d_it++
        ) {
            /*
             * { "src" : 1, "dst" : 2 }
             */
            Json::Value link(Json::objectValue);
            link["src"] = (*s_it).first;
            link["dst"] = *d_it;

            topology.append(link);
        }
    }

    topology_wrapper["topology"] = topology;

    stringstream tmp_topo;
    tmp_topo << dir << "/topology.json";
    string topo_file_name = tmp_topo.str();

    ofstream topo_file(topo_file_name.c_str());
    topo_file << topology_wrapper;
    topo_file.close();

    for (
        std::map<uint32_t,std::list<RuleNode*>* >::iterator t_it = this->table_to_nodes.begin();
        t_it != this->table_to_nodes.end();
        t_it++
    ) {
        /*
         *  {
         *      "id" : 1,
         *      "ports" : [...],
         *      "rules" : [...]
         *  }
         */
        Json::Value table(Json::objectValue);
        const uint64_t id = (*t_it).first;
        table["id"] = (Json::UInt64)id;

        Json::Value ports(Json::arrayValue);
        ports = list_to_json(table_to_ports[id]);

        table["ports"] = ports;

        Json::Value rules(Json::arrayValue);
        for (
            list<RuleNode*>::iterator r_it = (*t_it).second->begin();
            r_it != (*t_it).second->end();
            r_it++
        ) {
            /*
             *  {
             *      "action" : "fwd"|"rw",
             *      "in_ports" : [...],
             *      "out_ports" : [...],
             *      "match" : "01x1...",
             *      "mask" : "01x1...",
             *      "rewrite" : "01x1..."
             *  }
             */
            Json::Value rule(Json::objectValue);

            rule["action"] = (*r_it)->rewrite ? "rw" : "fwd";
            rule["in_ports"] = list_to_json((*r_it)->input_ports);
            rule["out_ports"] = list_to_json((*r_it)->output_ports);

            rule["match"] = (Json::StaticString)array_to_str(
                (*r_it)->match,this->length,false
            );

            if ((*r_it)->mask) {
                rule["mask"] = (Json::StaticString) array_to_str(
                    (*r_it)->mask,this->length,false
                );
            }

            if ((*r_it)->rewrite) {
                rule["rewrite"] = (Json::StaticString) array_to_str(
                    (*r_it)->rewrite,this->length,false
                );
            }

            rules.append(rule);
        }
        table["rules"] = rules;

        stringstream tmp_table;
        tmp_table << dir << "/" << id << ".tf.json";
        string table_file_name = tmp_table.str();

        ofstream table_file(table_file_name.c_str());
        table_file << table;
        table_file.close();
    }

    /*
     *  {
     *      "policy" : [...]
     *  }
     */
    Json::Value commands(Json::arrayValue);

    for (
        std::list<Node *>::iterator it = this->flow_nodes.begin();
        it != this->flow_nodes.end();
        it++
    ) {
        /*
         *  {
         *      "method" : "add_source",
         *      "params" : {
         *          "hs" : { "list" : [...], "diff" : [...] },
         *          "ports" : [...]
         *      }
         *  }
         */
        Json::Value command(Json::objectValue);
        command["method"] = "add_source";

        Json::Value params(Json::objectValue);
        Json::Value hs(Json::objectValue);
        hs_to_json(hs, (*it)->source_flow.back()->hs_object);
        params["hs"] = hs;
        params["ports"] = list_to_json((*it)->output_ports);

        command["params"] = params;

        commands.append(command);
    }

    for (
        std::list<Node *>::iterator it = this->probes.begin();
        it != this->probes.end();
        it++
    ) {
        /*
         *  {
         *      "method" : "add_source_probe",
         *      "params" : {
         *          "ports" : [...],
         *          "mode" : "existential"|"universal",
         *          "filter" : {...},
         *          "test" : {...}
         *      }
         *  }
         */
        Json::Value command(Json::objectValue);

        command["method"] = "add_source_probe";

        Json::Value params(Json::objectValue);
        params["ports"] = list_to_json((*it)->input_ports);

        Json::Value mode;
        ((SourceProbeNode *)(*it))->mode_to_json(mode);
        params["mode"] = mode;


        Json::Value filter(Json::objectValue);
        ((SourceProbeNode *)(*it))->filter_to_json(filter);
        params["filter"] = filter;

        Json::Value test(Json::objectValue);
        ((SourceProbeNode *)(*it))->test_to_json(test);
        params["test"] = test;

        command["params"] = params;

        commands.append(command);
    }

    Json::Value policy(Json::objectValue);
    policy["commands"] = commands;

    stringstream tmp_policy;
    tmp_policy << dir << "/policy.json";
    string policy_file_name = tmp_policy.str();

    ofstream policy_file(policy_file_name.c_str());
    policy_file << policy;
    policy_file.close();
}


void traverse_flow(list<list<uint64_t>*> *flows, struct Flow *flow) {
    if (flow->n_flows && !flow->n_flows->empty()) { // traverse flows to their end
        for (
            list<list<struct Flow*>::iterator>::iterator n_flow = flow->n_flows->begin();
            n_flow != flow->n_flows->end();
            n_flow++
        ) {
            traverse_flow(flows,*(*n_flow));
        }
    } else { // reached eof: create a list and go back to source collecting all nodes
        list<uint64_t> *f_list = new list<uint64_t>();
        flows->push_back(f_list);
        struct Flow *f = flow;
        while (f->p_flow != f->node->get_EOSFI()) {
            f_list->push_front(f->node->node_id);
            f = *f->p_flow;
        }
        f_list->push_front(f->node->node_id);
    }
}


void NetPlumber::dump_flows(string dir) {
    Json::Value flows_wrapper(Json::objectValue);
    Json::Value flows(Json::arrayValue);

    for (
        std::list<Node *>::iterator it = this->flow_nodes.begin();
        it != this->flow_nodes.end();
        it++
    ) {
        /*
         *  [
         *      [1,3,4] <- flow
         *  ]
         */

        list<list<uint64_t>*> *path = new list<list<uint64_t>*>();

        for (
            list<Flow *>::iterator f_it = (*it)->source_flow.begin();
            f_it != (*it)->source_flow.end();
            f_it++
        ) {
            traverse_flow(path,*f_it);
        }

        for (
            list<list<uint64_t>*>::iterator p_it = path->begin();
            p_it != path->end();
            p_it++
        ) {
            Json::Value flow(Json::arrayValue);
            for (
                list<uint64_t>::iterator f_it = (*p_it)->begin();
                f_it != (*p_it)->end();
                f_it++
            ) {
                flow.append((Json::UInt64) (*f_it));
            }

            flows.append(flow);

            (*p_it)->clear();
        }

        path->clear();
        delete path;
    }

    flows_wrapper["flows"] = flows;

    stringstream tmp_flows;
    tmp_flows << dir << "/flows.json";
    string flows_file_name = tmp_flows.str();

    ofstream flow_file(flows_file_name.c_str());
    flow_file << flows_wrapper;
    flow_file.close();
}


void NetPlumber::dump_pipes(string dir) {
    Json::Value pipes_wrapper(Json::objectValue);
    Json::Value pipes(Json::arrayValue);

    for (
            map<uint64_t,Node*>::iterator n_it = id_to_node.begin();
            n_it != id_to_node.end();
            n_it++
        ) {
        Json::Value pipe(Json::arrayValue);
        pipe.append((Json::UInt64) (*n_it).first);

        for (
            list<struct Pipeline*>::iterator p_it = (*n_it).second->next_in_pipeline.begin();
            p_it != (*n_it).second->next_in_pipeline.end();
            p_it++
        ) {
            pipe.append((Json::UInt64) (*p_it)->node);
        }
    }

    pipes_wrapper["pipes"] = pipes;

    stringstream tmp_pipe_network;
    tmp_pipe_network << dir << "/pipes.json";
    string pipe_network_file_name = tmp_pipe_network.str();

    ofstream pipe_network_file(pipe_network_file_name.c_str());
    pipe_network_file << pipes_wrapper;
    pipe_network_file.close();
}

#ifdef PIPE_SLICING
bool NetPlumber::add_slice(uint64_t id, struct hs *net_space) {
    this->last_event.type = ADD_SLICE;
    this->last_event.id1 = id;

    /* if net space id is already present, replace old entry */
    if (slices[id]) remove_slice(id);

    /* if slice does not fit in free network space */
    if (!hs_is_sub_eq(net_space,slices[0]->net_space)) {
        this->slice_overlap_callback(this,NULL,this->slice_overlap_callback_data);
        return false;
    }

    struct Slice *slice = (struct Slice *)malloc(sizeof(*slice));
    slice->net_space_id = id;
    slice->net_space = net_space;
    slice->pipes = new std::list<struct Pipeline*>();

    /* remove slice from free network space */
    hs_minus(slices[0]->net_space,net_space);

    /* add free pipelines to slice */
    std::list<struct Pipeline *> *pipes = slices[0]->pipes;
    std::list<struct Pipeline *>::iterator p;
    struct Pipeline *pipe;
    struct hs *tmp;

    std::list<std::list<struct Pipeline *>::iterator> rem;

    for (p = pipes->begin(); p != pipes->end(); p++) {
        pipe = *p;

        tmp = hs_create(this->length);
        hs_add(tmp,array_copy(pipe->pipe_array,this->length));

        if (hs_is_sub_eq(tmp,net_space)) {
            pipe->net_space_id = slice->net_space_id;
            slice->pipes->push_front(pipe);
            pipe->r_slice = pipes->begin();
            rem.push_back(p);
        }

        hs_free(tmp);
    }


    std::list<std::list<struct Pipeline *>::iterator>::iterator p2;
    for (p2= rem.begin(); p2 != rem.end(); p2++) pipes->erase(*p2);

    // TODO: is it necessary to destruct the pipeline list?
    if(slices[id]) free(slices[id]);
    slices[id] = slice;

    return true;
}
#endif

#ifdef PIPE_SLICING
void NetPlumber::remove_slice(uint64_t id) {
    this->last_event.type = REMOVE_SLICE;
    this->last_event.id1 = id;

    if (id == 0) return;

    std::map<uint64_t,struct Slice *>::iterator slice;
    struct Slice *s = NULL;

    /* select slice if present */
    if (slices[id]) s = slices[id];
    else return;

    /* remove pipelines from slice and add to free space */
    std::list<struct Pipeline *> *pipes = s->pipes;
    std::list<struct Pipeline *>::iterator p;
    struct Pipeline *pipe;
    for (p = pipes->begin(); p != pipes->end(); p++) {
        pipe = *p;
        pipe->net_space_id = 0;
        slices[0]->pipes->push_front(pipe);
        pipe->r_slice = pipes->begin();
    }

    delete pipes;

    /* free network space */
    hs_add_hs(slices[0]->net_space,s->net_space);

    slices.erase(id);
    free(s);
}
#endif

#ifdef POLICY_PROBES
void NetPlumber::add_policy_rule(uint32_t index, hs *match, ACTION_TYPE action) {
    policy_checker->add_policy_rule(index,match,action);
}
#endif

#ifdef POLICY_PROBES
void NetPlumber::remove_policy_rule(uint32_t index) {
    policy_checker->remove_policy_rule(index);
}
#endif

#ifdef POLICY_PROBES
uint64_t NetPlumber::add_policy_probe_node(List_t ports,
                               policy_probe_callback_t probe_callback,
                               void *probe_callback_data) {
  uint64_t node_id = (uint64_t)(++last_ssp_id_used);
  PolicyProbeNode* p = new PolicyProbeNode(this, length, node_id,
                                           ports, policy_checker,
                                           probe_callback, probe_callback_data);
  this->id_to_node[node_id] = p;
  this->probes.push_back(p);
  this->last_event.type = START_POLICY_PROBE;
  this->last_event.id1 = node_id;
  this->set_port_to_node_maps(p);
  this->set_node_pipelines(p);
  p->process_src_flow(NULL);
  p->start_probe();
  return node_id;
}
#endif

#ifdef POLICY_PROBES
void NetPlumber::remove_policy_probe_node(uint64_t id) {
  if (id_to_node.count(id) > 0 && id_to_node[id]->get_type() == POLICY_PROBE) {
    this->last_event.type = STOP_POLICY_PROBE;
    this->last_event.id1 = id;
    PolicyProbeNode *p = (PolicyProbeNode *)id_to_node[id];
    p->stop_probe();
    id_to_node.erase(p->node_id);
    probes.remove(p);
    clear_port_to_node_maps(p);
    delete p;
  } else {
    stringstream error_msg;
    error_msg << "Probe Node " << id << " does not exist. Can't delete it.";
    LOG4CXX_WARN(logger,error_msg.str());
  }
}
#endif
