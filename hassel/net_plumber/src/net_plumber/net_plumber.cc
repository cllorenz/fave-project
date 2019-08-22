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
	   jan@sohre.eu (Jan Sohre)
*/

#include "net_plumber.h"
#include <stdio.h>
#include <assert.h>
#include <stdlib.h>
#include <sstream>
#include <fstream>
#include <climits>
#include "net_plumber_utils.h"
#include "../jsoncpp/json/json.h"
extern "C" {
  #include "../headerspace/array.h"
}

using namespace std;
using namespace log4cxx;
using namespace net_plumber;

LoggerPtr NetPlumber::logger(Logger::getLogger("NetPlumber"));
LoggerPtr loop_logger(Logger::getLogger("DefaultLoopDetectionLogger"));
#ifdef CHECK_BLACKHOLES
LoggerPtr blackhole_logger(Logger::getLogger("DefaultBlackholeDetectionLogger"));
#endif
#ifdef CHECK_REACH_SHADOW
LoggerPtr unreach_logger(Logger::getLogger("DefaultUnreachDetectionLogger"));
LoggerPtr shadow_logger(Logger::getLogger("DefaultShadowDetectionLogger"));
#endif
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

void default_loop_callback(NetPlumber *N, Flow *f, void* /*data*/) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Loop Detected: after event " << get_event_name(e.type) <<
      " (ID1: " << e.id1 << ")" << endl << flow_to_str(f);
  LOG4CXX_FATAL(loop_logger,error_msg.str());
}

#ifdef CHECK_BLACKHOLES
void default_blackhole_callback(NetPlumber *N, Flow* /*f*/, void* /*data*/) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Black Hole Detected: after event " << get_event_name(e.type) <<
      " (ID1: " << e.id1 << ")";
  LOG4CXX_FATAL(blackhole_logger,error_msg.str());
}
#endif

#ifdef CHECK_REACH_SHADOW
void default_rule_unreach_callback(NetPlumber *N, Flow *f, void *data) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Unreachable Rule Detected: after event " <<
    get_event_name(e.type) << " (ID1: " << e.id1 << ")";
  LOG4CXX_FATAL(unreach_logger,error_msg.str());
}
#endif

#ifdef CHECK_REACH_SHADOW
void default_rule_shadow_callback(NetPlumber *N, Flow *f, void *data) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Shadowed Rule Detected: after event " <<
    get_event_name(e.type) << " (ID1: " << e.id1 << ")";
  LOG4CXX_FATAL(shadow_logger,error_msg.str());
}
#endif

#ifdef PIPE_SLICING
void default_slice_overlap_callback(NetPlumber *N, Flow* /*f*/, void* /*data*/) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Slice Overlap Detected: after event " << get_event_name(e.type) <<
      " (ID1: " << e.id1 << ")";
  LOG4CXX_FATAL(slice_logger,error_msg.str());
}
#endif

#ifdef PIPE_SLICING
void default_slice_leakage_callback(NetPlumber *N, Flow* /*f*/, void *data) {
  Event e = N->get_last_event();
  stringstream error_msg;
  error_msg << "Slice Leakage Detected: after event " << get_event_name(e.type) <<
    " (ID1: " << e.id1 << "), " << *(std::string*)data;
  LOG4CXX_FATAL(slice_logger,error_msg.str());
}
#endif

string get_event_name(EVENT_TYPE t) {
  switch (t) {
    case(ADD_RULE)           : return "Add Rule";
    case(REMOVE_RULE)        : return "Remove Rule";
    case(ADD_LINK)           : return "Add Link";
    case(REMOVE_LINK)        : return "Remove Link";
    case(ADD_SOURCE)         : return "Add Source";
    case(REMOVE_SOURCE)      : return "Remove Source";
    case(ADD_SINK)           : return "Add Sink";
    case(REMOVE_SINK)        : return "Remove Sink";
    case(START_SOURCE_PROBE) : return "Start Source Probe";
    case(STOP_SOURCE_PROBE)  : return "Stop Source Probe";
    case(START_SINK_PROBE)   : return "Start Sink Probe";
    case(STOP_SINK_PROBE)    : return "Stop Sink Probe";
    case(ADD_TABLE)          : return "Add Table";
    case(REMOVE_TABLE)       : return "Remove Table";
#ifdef PIPE_SLICING
    case(ADD_SLICE)          : return "Add Slice";
    case(REMOVE_SLICE)       : return "Remove Slice";
    case(ADD_SLICE_MATRIX)   : return "Add Slice Matrix";
    case(REMOVE_SLICE_MATRIX): return "Remove Slice Matrix";
    case(ADD_SLICE_ALLOW)    : return "Add Slice Allow";
    case(REMOVE_SLICE_ALLOW) : return "Remove Slice Allow";
    case(PRINT_SLICE_MATRIX) : return "Print Slice Matrix";
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
  auto rules_list = table_to_nodes[table];
  for (auto it = rules_list->begin() ; it != rules_list->end(); ) {
    if ((*it)->group == group) {
      free_rule_memory(*it, false);
      auto tmp = it; it++;
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
    for (auto &rule: *rules_list) {
      free_rule_memory(rule, false);
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
  bool seen_rule = false;
#ifdef CHECK_REACH_SHADOW
  bool checked_rs = false;

  struct hs all_hs = {this->length,{0}};
  hs_add(&all_hs,array_create(this->length,BIT_X));

  struct hs aggr_hs = {this->length,{0}};
#endif

  for (auto const &rule: *rules_list) {
    if (rule->node_id == r->node_id) {

#ifdef CHECK_REACH_SHADOW
      // check reachability and shadowing
      struct hs rule_hs = {this->length,{0}};
      hs_add(&rule_hs, array_copy(rule->match, this->length));

      if (hs_is_equal(&all_hs,&aggr_hs)) {
        this->rule_unreach_callback(this,NULL,this->rule_unreach_callback_data);
      } else if (hs_is_sub(&rule_hs,&aggr_hs)) {
        this->rule_shadow_callback(this,NULL,this->rule_shadow_callback_data);
      }

      hs_destroy(&rule_hs);
      checked_rs = true;
#endif

      seen_rule = true;
    } else if (rule->group != 0 && rule->node_id != rule->group){
      // escape rule, if rule belongs to a group and is not the lead of the group.
      continue;
    } else {
      // find common input ports
      List_t common_ports = intersect_sorted_lists(r->input_ports,
                                                  rule->input_ports);
      if (common_ports.size == 0) continue;
      // find common headerspace
      array_t *common_hs = array_isect_a(r->match,rule->match,this->length);

#ifdef CHECK_REACH_SHADOW
      if (!checked_rs) hs_add(&aggr_hs,array_copy(rule->match,this->length));
#endif

      if (common_hs == NULL) {
        if (!common_ports.shared) free(common_ports.list);
        continue;
      }
      // add influence
      Influence *inf = (Influence *)malloc(sizeof *inf);
      inf->len = this->length;
      Effect *eff = (Effect *)malloc(sizeof *eff);
      inf->comm_arr = common_hs;
      inf->ports = common_ports;

      if (seen_rule) {
        inf->node = rule;
        eff->node = r;
        eff->influence = rule->set_influence_by(inf);
        inf->effect = r->set_effect_on(eff);
      } else {
        inf->node = r;
        eff->node = rule;
        eff->influence = r->set_influence_by(inf);
        inf->effect = rule->set_effect_on(eff);
      }
    }
  }

#ifdef CHECK_REACH_SHADOW
  hs_destroy(&aggr_hs);
  hs_destroy(&all_hs);
#endif
}

void NetPlumber::set_node_pipelines(Node *n) {
  // set n's forward pipelines.
  for (size_t i = 0; i < n->output_ports.size; i++) {
    vector<uint32_t> *end_ports = get_dst_ports(n->output_ports.list[i]);
    if (!end_ports) continue;
    for (size_t j = 0; j < end_ports->size(); j++) {
      list<Node*> *potential_next_rules =
          get_nodes_with_inport(end_ports->at(j));
      if (!potential_next_rules) continue;
      for (auto const &n_rule: *potential_next_rules) {
        array_t *pipe_arr;
        pipe_arr = array_isect_a(n_rule->match,n->inv_match,length);
        if (pipe_arr) {
          Pipeline *fp = (Pipeline *)malloc(sizeof *fp);
          Pipeline *bp = (Pipeline *)malloc(sizeof *bp);
          fp->local_port = n->output_ports.list[i];
          bp->local_port = end_ports->at(j);
          fp->pipe_array = pipe_arr;
          fp->len = length;
          bp->pipe_array = array_copy(pipe_arr,length);
          bp->len = length;
          fp->node = n;
          bp->node = n_rule;
          bp->r_pipeline = n->add_fwd_pipeline(fp);
          fp->r_pipeline = n_rule->add_bck_pipeline(bp);
#ifdef PIPE_SLICING
    add_pipe_to_slices(fp);
    add_pipe_to_slices(bp);
#endif
        }
      }
    }
  }
  // set n's backward pipelines.
  for (size_t i = 0; i < n->input_ports.size; i++) {
    vector<uint32_t> *orig_ports = get_src_ports(n->input_ports.list[i]);
    if (!orig_ports) continue;
    for (size_t j = 0; j < orig_ports->size(); j++) {
      list<Node*> *potential_prev_rules =
          get_nodes_with_outport(orig_ports->at(j));
      if (!potential_prev_rules) continue;
      for (auto const &p_rule: *potential_prev_rules) {
        array_t *pipe_arr;
        pipe_arr = array_isect_a(p_rule->inv_match,n->match,length);

        if (pipe_arr) {
          Pipeline *fp = (Pipeline *)malloc(sizeof *fp);
          Pipeline *bp = (Pipeline *)malloc(sizeof *bp);
          fp->local_port = orig_ports->at(j);
          bp->local_port = n->input_ports.list[i];
          fp->pipe_array = pipe_arr;
          fp->len = length;
          bp->pipe_array = array_copy(pipe_arr,length);
          bp->len = length;
          fp->node = p_rule;
          bp->node = n;
          bp->r_pipeline = p_rule->add_fwd_pipeline(fp);
          fp->r_pipeline = n->add_bck_pipeline(bp);
#ifdef PIPE_SLICING
    add_pipe_to_slices(fp);
    add_pipe_to_slices(bp);
#endif
        }
      }
    }
  }
#ifdef PIPE_SLICING
  check_node_for_slice_leakage(n);
#endif /* PIPE_SLICING */
}

#ifdef PIPE_SLICING
void NetPlumber::add_pipe_to_slices(Pipeline *pipe) {
  /* determine net space of pipe */
  struct hs *pipe_space = hs_create(this->length);
  hs_add(pipe_space, array_copy(pipe->pipe_array, this->length));
  bool match = false;

  /* find slice matching net space */
  for (auto &slice: slices) {
    if (hs_is_sub_eq(pipe_space, slice.second.net_space)) {
      /* update slice and pipe information */
      pipe->net_space_id = slice.first;
      slice.second.pipes.push_front(pipe);
      pipe->r_slice = slice.second.pipes.begin();
      match = true;
      break;
    }
  }

  if (!match) {
    pipe->net_space_id = 0;
    slices.at(0).pipes.push_front(pipe);
    pipe->r_slice = slices.at(0).pipes.begin();
  }

  hs_free(pipe_space);
}
#endif

#ifdef PIPE_SLICING
void NetPlumber::check_node_for_slice_leakage(Node *node) {
  /* base case: check prev pipes against next pipes */
  for (auto const &prev: node->prev_in_pipeline) {
    for (auto const &next: node->next_in_pipeline) {
      check_pipe_for_slice_leakage((*prev->r_pipeline), (*next->r_pipeline));
    }
  }

  /* node only has outgoing pipes */
  if (node->prev_in_pipeline.empty()) {
    for (auto const &prev: node->next_in_pipeline) {
      for (auto const &next: (*prev->r_pipeline)->node->next_in_pipeline) {
        check_pipe_for_slice_leakage((*prev->r_pipeline), (*next->r_pipeline));
      }
    }
  }

  /* node only has incoming pipes */
  if (node->next_in_pipeline.empty()) {
    for (auto const &next: node->prev_in_pipeline) {
      for (auto const &prev: (*next->r_pipeline)->node->prev_in_pipeline) {
        check_pipe_for_slice_leakage((*prev->r_pipeline), (*next->r_pipeline));
      }
    }
  }

  // from the point of view of a node there are incoming pipes and outgoing
  // pipes
  // i.e. table 7 has 6 outgoing pipes each representing a net space
  // i.e. table 1 has 1 outgoing pipe to a probe_node
  // so if a node has changed, either it's incoming or outgoing pipes have
  // changed
  // we can not compute on the pipe level, as the pipes are in flux when
  // assigned in set_node_pipes with respect to their netspace assignment
  // we can compute pipes against pipes in a cross-product fashion when
  // a pipe has changed
  // there probably is rooom for improvement in this approach

  // object is to aggregate all pipes flowing in and all pipes flowing out
  // then we can cross compare

  // in the example demo_leak1 this isnt too bad
  // in more complex scenarios this would fall short probably --> measure

  // approach is to collect all incoming pipes and all outgoing pipes, then compare
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
void NetPlumber::check_pipe_for_slice_leakage(Pipeline *in, Pipeline *out) {
  if (in == out) return;
  uint64_t inspace = in->net_space_id;
  uint64_t outspace = out->net_space_id;

  if (inspace != outspace) {
    if (!check_leak_exception(inspace, outspace)) {
      std::stringstream es;
      es << "(node " << std::hex << in->node->node_id
	 << std::dec << ", space " << inspace
	 << ", node " << std::hex << out->node->node_id
	 << std::dec << ", space " << outspace << ")";
      std::string *e = new std::string(es.str());
      slice_leakage_callback(this, NULL, e);
      delete e;
    }
  }
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
bool NetPlumber::check_leak_exception(uint64_t in, uint64_t out) {
  try {
    auto inref = matrix.at(in);
    auto outref = inref.find(out);

    if (outref != inref.end()) {
      return true;
    }
  } catch (const std::out_of_range& oor) {}
  return false;
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
void NetPlumber::remove_pipe_from_slices(struct Pipeline *pipe) {
  try {
    auto &slice = slices.at(pipe->net_space_id);
    slice.pipes.erase(pipe->r_slice);
  } catch (const std::out_of_range& oor) { return; }
}
#endif /* PIPE_SLICING */

/*
 * * * * * * * * * * * * *
 * Public Class Members  *
 * * * * * * * * * * * * *
 */

NetPlumber::NetPlumber(size_t length) : length(length), last_ssp_id_used(0) {
  this->last_event.type = None;
  this->loop_callback = default_loop_callback;
  this->loop_callback_data = NULL;
#ifdef CHECK_BLACKHOLES
  this->blackhole_callback = default_blackhole_callback;
  this->blackhole_callback_data = NULL;
#endif
#ifdef CHECK_REACH_SHADOW
  this->rule_unreach_callback = default_rule_unreach_callback;
  this->rule_unreach_callback_data = NULL;
  this->rule_shadow_callback = default_rule_shadow_callback;
  this->rule_shadow_callback_data = NULL;
#endif
#ifdef PIPE_SLICING
  struct hs *net_space = hs_create(this->length);
  hs_add(net_space, array_create(this->length, BIT_X));
  slices = { {0, {net_space, {}}} };
  this->slice_overlap_callback = default_slice_overlap_callback;
  this->slice_overlap_callback_data = NULL;
  this->slice_leakage_callback = default_slice_leakage_callback;
  this->slice_leakage_callback_data = NULL;
#endif
}

NetPlumber::~NetPlumber() {
  for (auto &probe: this->probes) {
    if (probe->get_type() == SOURCE_PROBE) {
      ((SourceProbeNode*)probe)->stop_probe();
    }
    clear_port_to_node_maps(probe);
    delete probe;
  }
  for (auto &link: this->topology) {
    delete link.second;
  }
  for (auto &link: this->inv_topology) {
    delete link.second;
  }
  for (auto it = table_to_nodes.begin(); it != table_to_nodes.end(); ){
    auto tmp = it;
    tmp++;
    free_table_memory((*it).first);
    it = tmp;
  }
  for (auto &flow_node: this->flow_nodes) {
    clear_port_to_node_maps(flow_node);
    delete flow_node;
  }
#ifdef PIPE_SLICING
  for (auto const &slice: slices) {
    hs_free(slice.second.net_space);
  }
#endif /* PIPE_SLICING */
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
  if (src_rules && dst_rules) {
    for (auto const &src_rule: *src_rules) {
      for (auto const &dst_rule: *dst_rules) {
        array_t *pipe_arr = array_isect_a(
          src_rule->inv_match,
          dst_rule->match,
          length
        );
        if (pipe_arr) {
          Pipeline *fp = (Pipeline *)malloc(sizeof *fp);
          Pipeline *bp = (Pipeline *)malloc(sizeof *bp);
          fp->local_port = from_port;
          bp->local_port = to_port;
          fp->pipe_array = pipe_arr;
          fp->len = length;
          bp->pipe_array = array_copy(pipe_arr,length);
          bp->len = length;
          fp->node = src_rule;
          bp->node = dst_rule;
          bp->r_pipeline = src_rule->add_fwd_pipeline(fp);
          fp->r_pipeline = dst_rule->add_bck_pipeline(bp);
          src_rule->propagate_src_flows_on_pipe(bp->r_pipeline);
#ifdef PIPE_SLICING
          add_pipe_to_slices(fp);
          add_pipe_to_slices(bp);
          check_node_for_slice_leakage(fp->node);
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
    if (src_rules && dst_rules) {
      for (auto const &src_rule: *src_rules) {
        src_rule->remove_link_pipes(from_port, to_port);
      }
    }

    // update topology and inv_topology
    vector<uint32_t> *v = topology[from_port];
    vector<uint32_t> *v_inv = inv_topology[to_port];
    for (auto it = v->begin(); it != v->end(); it++) {
      if ((*it) == to_port) {
        v->erase(it);
        break;
      }
    }
    for (auto it = v_inv->begin(); it != v_inv->end(); it++) {
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
  for (auto const &link: topology) {
//  for (auto it = topology.begin(); it != topology.end(); it++ ){
    printf("%u --> ( ", link.first);
    for (size_t i = 0; i < link.second->size(); i++) {
      printf("%u ", link.second->at(i));
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

void NetPlumber::print_node(Node *node) {
    printf("%s\n", node->to_string().c_str());
}

void NetPlumber::print_node(const uint64_t id) {
    print_node(id_to_node[id]);
}

void NetPlumber::print_table(const uint32_t id) {
  printf("%s\n", string(40,'@').c_str());
  printf("%sTable: 0x%x\n", string(4, ' ').c_str(),id);
  printf("%s\n", string(40,'@').c_str());
  list<RuleNode*>* rules_list = table_to_nodes[id];
  List_t ports = this->table_to_ports[id];
  printf("Ports: %s\n", list_to_string(ports).c_str());
  printf("Rules:\n");
  for (auto const &rule: *rules_list) {
    print_node(rule);
  }
}

uint64_t NetPlumber::_add_rule(uint32_t table,int index,
                               bool group, uint64_t gid,
                               List_t in_ports, List_t out_ports,
                               array_t* match, array_t *mask, array_t* rw) {
  if (table_to_nodes.count(table) > 0) {
    List_t table_ports = table_to_ports[table];

    for (uint32_t i = 0; i < in_ports.size; ++i) // sanity check
        if (!elem_in_sorted_list(in_ports.list[i], table_ports)) return 0;

    for (uint32_t i = 0; i < out_ports.size; ++i) // sanity check
        if (!elem_in_sorted_list(out_ports.list[i], table_ports)) return 0;

    if (in_ports.size == 0) in_ports = table_ports;

    table_to_last_id[table] += 1;
    uint64_t id = table_to_last_id[table] + ((uint64_t)table << 32) ;

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
        auto it = table_to_nodes[table]->begin();
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
      auto node_it = table_to_nodes[table]->begin();
      for (; (*node_it)->node_id != gid; node_it++);
      this->table_to_nodes[table]->insert(++node_it,r);
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
      free(in_ports.list);free(out_ports.list);array_free(match);array_free(mask);array_free(rw);
      stringstream error_msg;
      error_msg << "Group " << group << " does not exist. Can't add rule to it."
          << "Ignoring add new rule request.";
      LOG4CXX_WARN(logger,error_msg.str());
      return 0;
    }
    return id;
  } else {
    free(in_ports.list);free(out_ports.list);array_free(match);array_free(mask);array_free(rw);
    stringstream error_msg;
    error_msg << "trying to add a rule to a non-existing table (id: " << table
        << "). Ignored.";
    LOG4CXX_ERROR(logger,error_msg.str());
    return 0;
  }
}


uint64_t NetPlumber::add_rule(uint32_t table,int index, List_t in_ports,
            List_t out_ports, array_t* match, array_t *mask, array_t* rw) {

  return _add_rule(table,index,false,0,in_ports,out_ports,match,mask,rw);
}

uint64_t NetPlumber::add_rule_to_group(uint32_t table,int index, List_t in_ports
                           ,List_t out_ports, array_t* match, array_t *mask,
                           array_t* rw, uint64_t group) {

  return _add_rule(table,index,true,group,in_ports,out_ports,match,mask,rw);
}

//expand(int length); length is the number if octets of the vector.
//"xxxxxxxx" is length 1
//"xxxxxxxx xxxxxxxx" is length 2 and so on
//|| z=00 1=10 0=01 x=11
//length of n equals 2n bytes of memory
size_t NetPlumber::expand(size_t length) {
  if (length > this->length) {
    for (auto const &node: id_to_node) {//should contain all flows, probes and rules
      node.second->enlarge(length);
    }

#ifdef PIPE_SLICING
    for (auto const &slice: slices) {
      hs_enlarge(slice.second.net_space, length);
    }
#endif //PIPE_SLICING

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
  s->process_src_flow(nullptr);
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

#ifdef USE_DEPRECATED
SourceProbeNode *NetPlumber::get_source_probe(uint64_t id) {
  if (id_to_node.count(id) > 0) {
    Node *n = id_to_node[id];
    if (n->get_type() == SOURCE_PROBE) {
      return (SourceProbeNode *)n;
    }
  }
  return NULL;
}
#endif

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
  for (auto const &node: table_to_nodes) {
    this->print_table(node.first);
  }
  printf("%s\n", string(40,'@').c_str());
  printf("%sSources and Sinks\n", string(4, ' ').c_str());
  printf("%s\n", string(40,'@').c_str());
  for (auto const &flow_node: flow_nodes) {
    printf("%s\n", flow_node->to_string().c_str());
  }
  printf("%s\n", string(40,'@').c_str());
  printf("%sProbes\n", string(4, ' ').c_str());
  printf("%s\n", string(40,'@').c_str());
  for (auto const &probe: probes) {
    printf("%s\n", (*probe).to_string().c_str());
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

void NetPlumber::save_dependency_graph(const string file_name) {
  Json::Value root(Json::objectValue);
  Json::Value nodes(Json::arrayValue);
  Json::Value links(Json::arrayValue);
  map<uint64_t,int> ordering;
  int count = 0;
  root["nodes"] = nodes;
  root["links"] = links;
  for (auto const &node: id_to_node) {
    stringstream s;
    s << node.first;
    Json::Value jnode(Json::objectValue);
    Json::Value name(Json::stringValue);
    name = s.str();
    jnode["name"] = name;
    root["nodes"].append(jnode);
    ordering[node.first] = count;
    count++;
  }
  for (auto const &s_node: id_to_node) {// = id_to_node.begin(); it != id_to_node.end(); it++) {
    stringstream s1,s2;
    s1 << s_node.first;
    Node *n = s_node.second;
    for (
        auto const d_node: n->next_in_pipeline) {
      Node *other_n = (*d_node->r_pipeline)->node;
      s2 << other_n->node_id;
      Json::Value link(Json::objectValue);
      Json::Value source(Json::intValue);
      Json::Value target(Json::intValue);
      source = ordering[s_node.first];
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

void NetPlumber::dump_net_plumber(const string dir) {
    dump_plumbing_network(dir);
    dump_flow_trees(dir);
    dump_pipes(dir);
#ifdef PIPE_SLICING
    dump_slices(dir);
    dump_slices_pipes(dir);
#endif
}

void NetPlumber::dump_plumbing_network(const string dir) {

    /*
     *  {
     *      "topology" : [...]
     *  }
     */
    Json::Value topology_wrapper(Json::objectValue);
    Json::Value topology(Json::arrayValue);

    for (auto const &s_node: this->topology) {
        for (auto const &d_node: *s_node.second) {
            /*
             * { "src" : 1, "dst" : 2 }
             */
            Json::Value link(Json::objectValue);
            link["src"] = s_node.first;
            link["dst"] = d_node;

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
        auto const &node: this->table_to_nodes) {
        /*
         *  {
         *      "id" : 1,
         *      "ports" : [...],
         *      "rules" : [...]
         *  }
         */
        Json::Value table(Json::objectValue);
        const uint64_t id = node.first;
        table["id"] = (Json::UInt64)id;

        Json::Value ports(Json::arrayValue);
        ports = list_to_json(table_to_ports[id]);

        table["ports"] = ports;

        uint32_t position = 0;
        Json::Value rules(Json::arrayValue);
        for (auto const &r_node: *node.second) {
            /*
             *  {
             *      "id" : 123...
             *      "action" : "fwd"|"rw",
             *      "in_ports" : [...],
             *      "out_ports" : [...],
             *      "match" : "01x1...",
             *      "mask" : "01x1...",
             *      "rewrite" : "01x1..."
             *      "influences" : "01x1... + 111x... + ..."
             *  }
             */
            Json::Value rule(Json::objectValue);

            rule["id"] = (Json::UInt64)r_node->node_id;
            rule["position"] = (Json::UInt64)position++;
            rule["action"] = r_node->rewrite ? "rw" : "fwd";
            rule["in_ports"] = list_to_json(r_node->input_ports);
            rule["out_ports"] = list_to_json(r_node->output_ports);

            char *match = array_to_str(r_node->match, this->length, false);
            rule["match"] = (Json::StaticString)match;
            free(match);

            if (r_node->mask) {
                char *mask =  array_to_str(r_node->mask, this->length, false);
                rule["mask"] = (Json::StaticString)mask;
                free(mask);
            }

            if (r_node->rewrite) {
                char *rw = array_to_str(r_node->rewrite, this->length, false);
                rule["rewrite"] = (Json::StaticString)rw;
                free(rw);
            }

#ifdef NEW_HS
            hs tmp = {this->length, {0, 0, 0}, {0, 0, 0}};
#else
            hs tmp = {this->length, {0, 0, 0, 0}};
#endif
            for (auto const &influence: *r_node->influenced_by) {
                hs_add(&tmp, array_copy(influence->comm_arr, this->length));
            }

            if (!hs_is_empty(&tmp)) {
                char *influences = hs_to_str(&tmp);
                rule["influences"] = (Json::StaticString)influences;
                free(influences);
            }
            hs_destroy(&tmp);

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
        auto const &flow_node: this->flow_nodes) {
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
        hs_to_json(hs, flow_node->source_flow.back()->hs_object);
        params["hs"] = hs;
        params["ports"] = list_to_json(flow_node->output_ports);

        command["params"] = params;

        commands.append(command);
    }

    for (auto const &probe: this->probes) {
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
        params["ports"] = list_to_json(probe->input_ports);

        Json::Value mode;
        ((SourceProbeNode *)probe)->mode_to_json(mode);
        params["mode"] = mode;


        Json::Value filter(Json::objectValue);
        ((SourceProbeNode *)probe)->filter_to_json(filter);
        params["filter"] = filter;

        Json::Value test(Json::objectValue);
        ((SourceProbeNode *)probe)->test_to_json(test);
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


void NetPlumber::_traverse_flow(list<list<uint64_t>*> *flows, struct Flow *flow) {
    if (flow->n_flows && !flow->n_flows->empty()) { // traverse flows to their end
        for (auto const &n_flow: *flow->n_flows) {
            _traverse_flow(flows, *n_flow);
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


void NetPlumber::_traverse_flow_tree(
    Json::Value& res,
    list<list<struct Flow *>::iterator> *n_flows,
    size_t depth
) {
    for (auto const &n_flow: *n_flows) {
        Json::Value node(Json::objectValue);

        node["node"] = (Json::Value::UInt64) (*n_flow)->node->node_id;

        char *flow = hs_to_str((*n_flow)->hs_object);
        node["flow"] = (Json::StaticString) flow;

        if (logger->isTraceEnabled()) {
            stringstream trace_msg;
            trace_msg << "traverse_flow_tree(): pass ";
            for (size_t i = 0; i < depth; i++) trace_msg << "  ";
            trace_msg << (*n_flow)->node->node_id;
            trace_msg << " with " << flow;
            trace_msg << "; children at " << (*n_flow)->n_flows;
            if ((*n_flow)->n_flows) {
                trace_msg << "; size: " << (*n_flow)->n_flows->size();
                trace_msg << "; is empty: " << ((*n_flow)->n_flows->empty() ? "true" : "false");
            }
            LOG4CXX_TRACE(logger, trace_msg.str());
        }

        free (flow);

        if ((*n_flow)->n_flows && !(*n_flow)->n_flows->empty()) {
            Json::Value children(Json::arrayValue);

            _traverse_flow_tree(children, (*n_flow)->n_flows, depth+1);
            node["children"] = children;
        }

        res.append(node);
    }
}


void NetPlumber::_traverse_flow_tree(Json::Value& res, list<list<struct Flow *>::iterator> *n_flows) {
    NetPlumber::_traverse_flow_tree(res, n_flows, 0);
}


void NetPlumber::dump_flow_trees(const string dir) {
    Json::Value flows_wrapper(Json::objectValue);
    Json::Value flows(Json::arrayValue);

    for (auto const &flow_node: flow_nodes) {
        for (auto const &s_flow: flow_node->source_flow) {
            Json::Value flow_tree(Json::objectValue);

            flow_tree["node"] = (Json::Value::UInt64) flow_node->node_id;
            char *flow = hs_to_str(s_flow->hs_object);
            flow_tree["flow"] = (Json::StaticString) flow;
            free(flow);

            if (s_flow->n_flows) {
                Json::Value children(Json::arrayValue);

                _traverse_flow_tree(children, s_flow->n_flows);

                flow_tree["children"] = children;
            }

            flows.append(flow_tree);
        }
    }

    flows_wrapper["flows"] = flows;

    stringstream tmp_flows;
    tmp_flows << dir << "/flow_trees.json";
    string flow_trees_file_name = tmp_flows.str();

    ofstream flow_file(flow_trees_file_name.c_str());
    flow_file << flows_wrapper;
    flow_file.close();
}


void NetPlumber::dump_flows(string dir) {
    Json::Value flows_wrapper(Json::objectValue);
    Json::Value flows(Json::arrayValue);

    for (auto const &flow_node: this->flow_nodes) {
        /*
         *  [
         *      [1,3,4] <- flow
         *  ]
         */

        list<list<uint64_t>*> *path = new list<list<uint64_t>*>();

        for (auto const &s_flow: flow_node->source_flow) {
            _traverse_flow(path, s_flow);
        }

        for (auto const &p_node: *path) {
            Json::Value flow(Json::arrayValue);
            for (auto const &p_flow: *p_node) {
                flow.append((Json::UInt64) p_flow);
            }

            flows.append(flow);

            p_node->clear();
            delete p_node;
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


void NetPlumber::dump_pipes(const string dir) {
    Json::Value pipes_wrapper(Json::objectValue);
    Json::Value pipes(Json::arrayValue);

    for (auto const &node: id_to_node) {
        Json::Value pipe(Json::arrayValue);

        list<struct Pipeline*> n_pipes = node.second->next_in_pipeline;

        if (!n_pipes.empty()) pipe.append((Json::UInt64) node.first);

        for (auto const &n_pipe: n_pipes) {
            Json::Value dest(Json::objectValue);

            dest["node"] = (Json::UInt64) (*n_pipe->r_pipeline)->node->node_id;
            char *filter = array_to_str((
                *n_pipe->r_pipeline)->pipe_array, length, false
            );
            dest["filter"] = (Json::StaticString) filter;
            free(filter);

            pipe.append(dest);
        }

        if (!n_pipes.empty()) pipes.append(pipe);
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
void NetPlumber::dump_slices(const string dir) {
  Json::Value slices_wrapper(Json::objectValue);
  Json::Value jslices(Json::arrayValue);
  
  for (auto const &s: slices) {
    // skips the default slice
    if (!s.first) continue;
    Json::Value slice(Json::objectValue);
    slice["id"] = (Json::UInt64) s.first;

    size_t len = s.second.net_space->len;
    const struct hs_vec *v = &s.second.net_space->list;
    if (v->used==1 && !v->diff[0].used) {
      slice["space"] = (Json::StaticString)array_to_str(v->elems[0], len, false);
    } else {
      Json::Value space(Json::objectValue);
      Json::Value lpos(Json::arrayValue);
      Json::Value lneg(Json::arrayValue);
      for (size_t i=0; i<v->used; i++) {
	bool diff = v->diff && v->diff[i].used;
	Json::Value arr = std::string(array_to_str(v->elems[i], len, false));
	lpos.append(arr);
	if (diff) {
	  for (size_t j=0; j<v->diff->used; j++) {
	    arr = std::string(array_to_str(v->diff->elems[i], len, false));
	    lneg.append(arr);
	  }
	}
	space["list"] = lpos;
	space["diff"] = lneg;
        slice["space"] = space;
      }
    }
    jslices.append(slice);
  }

  slices_wrapper["slices"] = jslices;

  stringstream tmp_slices;
  tmp_slices << dir << "/slices.json";
  string slice_file_name = tmp_slices.str();

  ofstream slice_file(slice_file_name.c_str());
  slice_file << slices_wrapper;
  slice_file.close();
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
bool NetPlumber::add_slice(uint64_t id, struct hs *net_space) {
  this->last_event.type = ADD_SLICE;
  this->last_event.id1 = id;

  /* if net space id is already present, replace old entry */
  if (slices.find(id) != slices.end()) {
    remove_slice(id);
  }

  /* if slice does not fit in free network space */
  if (!hs_is_sub_eq(net_space, slices[0].net_space)) {
    this->slice_overlap_callback(this, NULL, this->slice_overlap_callback_data);
    return false;
  }

  /* allocate new slice */
  Slice slice = {net_space, {}};

  /* remove slice from free network space */
  hs_minus(slices[0].net_space, net_space);

  /* add free pipelines to slice */
  struct hs *pipe_space;
  std::list<std::list<struct Pipeline*>::iterator> changed;
  auto it = slices[0].pipes.begin();

  for (auto const &pipe: slices[0].pipes) {
    pipe_space = hs_create(this->length);
    hs_add(pipe_space, array_copy(pipe->pipe_array, this->length));

    /* check if pipe's netspace belongs to slice's netspace */
    /* if so, add pipe to new slice and mark pipe as changed */
    if (hs_is_sub_eq(pipe_space, net_space)) {
      pipe->net_space_id = id;
      slice.pipes.push_front(pipe);
      changed.push_back(it);
    }
    hs_free(pipe_space);
    ++it;
  }

  for (auto const &pipe: changed) {
    slices[0].pipes.erase(pipe);
  }

  slices[id] = slice;
  return true;
}
#endif

#ifdef PIPE_SLICING
void NetPlumber::remove_slice(uint64_t id) {
  this->last_event.type = REMOVE_SLICE;
  this->last_event.id1 = id;

  if (id == 0) return;

  auto slice = slices.find(id);
  if (slice == slices.end()) return;
  
  /* remove pipelines from slice and add to free space */
  for (const auto &pipe: slice->second.pipes) {
    pipe->net_space_id = 0;
    slices[0].pipes.push_front(pipe);
    pipe->r_slice = slices[0].pipes.begin();
  }

  /* free network space */
  hs_add_hs(slices[0].net_space, slice->second.net_space);
  hs_free(slice->second.net_space);
  slices.erase(slice);
}
#endif

#ifdef PIPE_SLICING
bool NetPlumber::add_slice_matrix(std::string matrix) {
  this->last_event.type = ADD_SLICE_MATRIX;

  std::set<uint64_t> ids;
  std::set<uint64_t> row_ids;
  std::string line;
  std::string sub;
  const char *x;
  char *end;
  uint64_t id;
    
  if (matrix.empty()) { return false; }

  errno = 0;

  auto ss = std::stringstream(matrix);
  if (getline(ss, line)) {
    if (line.back() == ',') { return false; }
    auto sl = std::stringstream(line);
    getline(sl, sub, ',');
    if (!sub.empty()) { return false; }
    while (getline(sl, sub, ',')) {
      x = sub.c_str();
      id = std::strtoul(x, &end, 10);
      if ((id == 0 && end == x) ||
	  (id == ULLONG_MAX && errno) ||
	  (*end)) { 
	return false;
      }
      if (!ids.insert(id).second) return false;
    }

    while (getline(ss, line)) {
      if (((size_t)std::count(line.begin(), line.end(), ',')) != ids.size()) {
	this->matrix.clear();
	return false;
      }

      auto sl = std::stringstream(line);

      getline(sl, sub, ',');
      x = sub.c_str();
      id = std::strtoul(x, &end, 10);
      if ((id == 0 && end == x) ||
	  (id == ULLONG_MAX && errno) ||
	  (*end)) {
	this->matrix.clear();
	return false;
      }
      if (!row_ids.insert(id).second) {
	this->matrix.clear();
	return false;
      }

      for (auto const &sid: ids) {
	getline(sl, sub, ',');
	if (sub == "x") { this->matrix[id].insert(sid); }
      }
    }
    if (ids != row_ids) {
      this->matrix.clear();
      return false;
    }
  }
  return true;
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
void NetPlumber::remove_slice_matrix(void) {
    this->last_event.type = REMOVE_SLICE_MATRIX;
    this->matrix.clear();
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
bool NetPlumber::add_slice_allow(uint64_t id1, uint64_t id2) {
    this->last_event.type = ADD_SLICE_ALLOW;
    this->matrix[id1].insert(id2);
    return true;
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
void NetPlumber::remove_slice_allow(uint64_t id1, uint64_t id2) {
    this->last_event.type = REMOVE_SLICE_ALLOW;

    try {
      auto &set = matrix.at(id1);
      set.erase(id2);
      if (set.empty()) matrix.erase(id1);
    } catch (const std::out_of_range& oor) { return; }
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
void NetPlumber::print_slice_matrix(void) {
  this->last_event.type = PRINT_SLICE_MATRIX;
  std::stringstream ss;

  if (matrix.empty()) {
    ss << "slice matrix is empty";
  }
  ss << std::endl;

  for (auto const &line: matrix) {
    ss << line.first << ": ";
    auto &last = *(--line.second.end());
    for (auto const &id: line.second) {
      ss << id;
      if (&id != &last) ss << ",";
    }
    ss << std::endl;
  }
  LOG4CXX_INFO(slice_logger,ss.str());
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
void NetPlumber::dump_slices_pipes(const std::string dir) {
    Json::Value pipes_wrapper(Json::objectValue);
    Json::Value pipes(Json::arrayValue);

    for (auto const &node: id_to_node) {
      Json::Value pipe(Json::arrayValue);

      list<struct Pipeline*> n_pipes = node.second->next_in_pipeline;
      if (!n_pipes.empty()) pipe.append((Json::UInt64) node.first);

      for (auto const &prev: n_pipes) {
        Json::Value fpipe(Json::objectValue);
        fpipe["node_id"] = (Json::UInt64) (*prev->r_pipeline)->node->node_id;
        fpipe["slice_id"] = (Json::UInt64) prev->net_space_id;
        pipe.append(fpipe);
      }
      if (!n_pipes.empty()) pipes.append(pipe);
    }
    
    pipes_wrapper["pipes"] = pipes;
    
    stringstream tmp_pipe_network;
    tmp_pipe_network << dir << "/pipes_slices.json";
    string pipe_network_file_name = tmp_pipe_network.str();

    ofstream pipe_network_file(pipe_network_file_name.c_str());
    pipe_network_file << pipes_wrapper;
    pipe_network_file.close();
}
#endif /*PIPE_SLICING */
