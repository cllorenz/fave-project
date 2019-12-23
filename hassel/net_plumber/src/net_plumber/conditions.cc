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
           kiekhebe@uni-potsdam.de (Sebastian Kiekheben)
*/

#include "conditions.h"
#include "rule_node.h"
#include "array_packet_set.h"
#include "hs_packet_set.h"
#include <sstream>

using namespace std;
using namespace net_plumber;

template<class T1, class T2>
PathCondition<T1, T2>::~PathCondition() {
  for (auto& it: pathlets) {
    delete it;
  }
}

template<class T1, class T2>
void PathCondition<T1, T2>::add_pathlet(PathSpecifier<T1, T2> *pathlet) {
  pathlets.push_back(pathlet);
}

template<class T1, class T2>
bool PathCondition<T1, T2>::check(Flow<T1, T2> *f) {
/*
  list<PathSpecifier<T1, T2>*>::iterator it;
  for (it = pathlets.begin(); it != pathlets.end(); it++) {
    if (!(*it)->check_and_move(f)) return false;
  }
  return true;
*/
  stack<pair<typename list<PathSpecifier<T1, T2> * >::iterator, Flow<T1, T2> *> >decision_points;
  auto it = pathlets.begin();
  while (it != pathlets.end()) {
    // case 1: end of flow and no alternatives -> path does not meet spec, final decline
    if (!f && decision_points.empty()) {
      return false;

    // case 2: end of flow but still alternatives open -> jump to decision point and continue with next alternative
    } else if (!f && !decision_points.empty()) {
      auto dp = decision_points.top();
      decision_points.pop();
      it = dp.first;
      f = dp.second;
      decision_points.push(make_pair(it,*(f->p_flow)));

    // case 3: process flow and path
    } else {

      // case 1: normal pathlet
      if ((*it)->get_type() != PATHLET_SKIP_NEXT) {
        bool c = (*it)->check_and_move(f);

        // case: path does not meet spec and no decisions left -> final decline
        if (!c && decision_points.empty()) {
          return false;

        // case: path does not meet spec but still alternatives open -> jump to decision point, do one step, and retry
        } else if (!c && !decision_points.empty()) {
          auto dp = decision_points.top();
          decision_points.pop();
          it = dp.first;
          f = dp.second;
          decision_points.push(make_pair(it,*(f->p_flow)));
        }

      // case 2: special pathlet (skip arbitrarily, .*) -> introduce decision point
      } else {
        decision_points.push(make_pair(it,*(f->p_flow)));
      }
    }
    it++;
  }
  return true;
}

template<class T1, class T2>
string PathCondition<T1, T2>::to_string() {
  stringstream res;
  res << "path ~ \"";
  for (auto const &it: pathlets) {
    res << (*it).to_string();
  }
  res << "\"";
  return res.str();
}

template<class T1, class T2>
bool HeaderCondition<T1, T2>::check(Flow<T1, T2> *f) {
  T1 tmp = *f->processed_hs;
  tmp.intersect(h);
  bool result = false;
  if (!tmp.is_empty()) {
    tmp.unroll();
    if (!tmp.is_empty()) result = true;
  }
  return result;
}

template<class T1, class T2>
void HeaderCondition<T1, T2>::enlarge(uint32_t length) {
	this->h->enlarge(length);
}

template<class T1, class T2>
string HeaderCondition<T1, T2>::to_string() {
  stringstream res;
  res << "header ~ " << h->to_str();
  return res.str();
}

template<class T1, class T2>
bool PortSpecifier<T1, T2>::check_and_move(Flow<T1, T2>* &f) {
  while (f->p_flow != f->node->get_EOSFI()) {
    if (f->in_port == port && f->node->is_at_input_stage()) {
      f = *f->p_flow;
      return true;
    }
    f = *f->p_flow;
  }
  return false;
}

template<class T1, class T2>
string PortSpecifier<T1, T2>::to_string() {
  stringstream res;
  res << ".*(p = " << this->port << ")";
  return res.str();
}

template<class T1, class T2>
bool TableSpecifier<T1, T2>::check_and_move(Flow<T1, T2>* &f) {
  while (f->p_flow != f->node->get_EOSFI()) {
    if (f->node->get_type() == RULE && ((RuleNode<T1, T2> *)(f->node))->table == table
        && f->node->is_at_input_stage()){
      f = *f->p_flow;
      return true;
    }
    f = *f->p_flow;
  }
  return false;
}

template<class T1, class T2>
string TableSpecifier<T1, T2>::to_string() {
  stringstream res;
  res << ".*(t = " << this->table << ")";
  return res.str();
}

template<class T1, class T2>
bool NextPortsSpecifier<T1, T2>::check_and_move(Flow<T1, T2>* &f) {
  while (f->p_flow != f->node->get_EOSFI() && !f->node->is_at_input_stage()) {
      f = *f->p_flow;
  }
  if (f->p_flow != f->node->get_EOSFI() && elem_in_sorted_list(f->in_port, ports)) {
    f = *f->p_flow;
    return true;
  }
  return false;
}

template<class T1, class T2>
string NextPortsSpecifier<T1, T2>::to_string() {
  stringstream res;
  res << "(p in " << list_to_string(this->ports) << ")";
  return res.str();
}

template<class T1, class T2>
bool NextTablesSpecifier<T1, T2>::check_and_move(Flow<T1, T2>* &f) {
  while (f->p_flow != f->node->get_EOSFI() && !f->node->is_at_input_stage()) {
      f = *f->p_flow;
  }
  if (f->p_flow != f->node->get_EOSFI() && f->node->get_type() == RULE &&
      elem_in_sorted_list(((RuleNode<T1, T2> *)(f->node))->table, tables)) {
    f = *f->p_flow;
    return true;
  }
  return false;
}

template<class T1, class T2>
string NextTablesSpecifier<T1, T2>::to_string() {
  stringstream res;
  res << "(t in " << list_to_string(this->tables) << ")";
  return res.str();
}

template<class T1, class T2>
bool LastPortsSpecifier<T1, T2>::check_and_move(Flow<T1, T2>* &f) {
  Flow<T1, T2> *prev = nullptr;
  while (f->p_flow != f->node->get_EOSFI()) {
    prev = f;
    f = *f->p_flow;
  }
  if (prev && prev->node->is_at_input_stage() &&
      elem_in_sorted_list(prev->in_port, ports)) {
    return true;
  } else {
    return false;
  }
}

template<class T1, class T2>
string LastPortsSpecifier<T1, T2>::to_string() {
  stringstream res;
  res << ".*(p in " << list_to_string(this->ports) << ")$";
  return res.str();
}

template<class T1, class T2>
bool LastTablesSpecifier<T1, T2>::check_and_move(Flow<T1, T2>* &f) {
  Flow<T1, T2> *prev = nullptr;
  while (f->p_flow != f->node->get_EOSFI()) {
    prev = f;
    f = *f->p_flow;
  }
  if (prev && prev->node->get_type() == RULE && prev->node->is_at_input_stage()
      && elem_in_sorted_list(((RuleNode<T1, T2> *)(prev->node))->table, tables)) {
    return true;
  } else {
    return false;
  }
}

template<class T1, class T2>
string LastTablesSpecifier<T1, T2>::to_string() {
  stringstream res;
  res << ".*(t in " << list_to_string(this->tables) << ")$";
  return res.str();
}

template<class T1, class T2>
bool SkipNextSpecifier<T1, T2>::check_and_move(Flow<T1, T2>* &f) {
  while (f->p_flow != f->node->get_EOSFI() && !f->node->is_at_input_stage()) {
      f = *f->p_flow;
  }
  if (f->p_flow != f->node->get_EOSFI()) {
    f = *f->p_flow;
    return true;
  }
  return false;
}

template<class T1, class T2>
bool SkipNextArbSpecifier<T1, T2>::check_and_move(Flow<T1, T2>* &/*f*/) {
  return true;
}

template<class T1, class T2>
void TrueCondition<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "true";
}

template<class T1, class T2>
void FalseCondition<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "false";
}

template<class T1, class T2>
void AndCondition<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "and";

  Json::Value arg1;
  c1->to_json(arg1);
  res["arg1"] = arg1;

  Json::Value arg2;
  c2->to_json(arg2);
  res["arg2"] = arg2;
}

template<class T1, class T2>
void OrCondition<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "or";

  Json::Value arg1;
  c1->to_json(arg1);
  res["arg1"] = arg1;

  Json::Value arg2;
  c2->to_json(arg2);
  res["arg2"] = arg2;
}

template<class T1, class T2>
void NotCondition<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "not";

  Json::Value arg;
  c->to_json(arg);

  res["arg"] = arg;
}

template<class T1, class T2>
void HeaderCondition<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "header";
  Json::Value hs(Json::objectValue);
  h->to_json(hs);
  res["header"] = hs;
}

template<class T1, class T2>
void PathCondition<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "path";

  Json::Value pathlets(Json::arrayValue);
  for (const auto& it: this->pathlets) {
    Json::Value pathlet(Json::objectValue);
    (*it).to_json(pathlet);
    pathlets.append(pathlet);
  }
  res["pathlets"] = pathlets;
}

template<class T1, class T2>
void PortSpecifier<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "port";
  res["port"] = this->port;
}

template<class T1, class T2>
void TableSpecifier<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "table";
  res["table"] = this->table;
}

template<class T1, class T2>
void NextPortsSpecifier<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "next_ports";
  res["ports"] = list_to_json(ports);
}

template<class T1, class T2>
void NextTablesSpecifier<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "next_tables";
  res["tables"] = list_to_json(tables);
}

template<class T1, class T2>
void LastPortsSpecifier<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "last_ports";
  res["ports"] = list_to_json(ports);
}

template<class T1, class T2>
void LastTablesSpecifier<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "last_tables";
  res["tables"] = list_to_json(tables);
}

template<class T1, class T2>
void SkipNextSpecifier<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "skip";
}

template<class T1, class T2>
void SkipNextArbSpecifier<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "skip_next";
}

template<class T1, class T2>
void EndPathSpecifier<T1, T2>::to_json(Json::Value& res) {
  res["type"] = "end";
}

template class TrueCondition<HeaderspacePacketSet, ArrayPacketSet>;
template class FalseCondition<HeaderspacePacketSet, ArrayPacketSet>;
template class AndCondition<HeaderspacePacketSet, ArrayPacketSet>;
template class OrCondition<HeaderspacePacketSet, ArrayPacketSet>;
template class NotCondition<HeaderspacePacketSet, ArrayPacketSet>;
template class HeaderCondition<HeaderspacePacketSet, ArrayPacketSet>;
template class PathCondition<HeaderspacePacketSet, ArrayPacketSet>;
template class PortSpecifier<HeaderspacePacketSet, ArrayPacketSet>;
template class TableSpecifier<HeaderspacePacketSet, ArrayPacketSet>;
template class NextPortsSpecifier<HeaderspacePacketSet, ArrayPacketSet>;
template class NextTablesSpecifier<HeaderspacePacketSet, ArrayPacketSet>;
template class LastPortsSpecifier<HeaderspacePacketSet, ArrayPacketSet>;
template class LastTablesSpecifier<HeaderspacePacketSet, ArrayPacketSet>;
template class SkipNextSpecifier<HeaderspacePacketSet, ArrayPacketSet>;
template class SkipNextArbSpecifier<HeaderspacePacketSet, ArrayPacketSet>;
template class EndPathSpecifier<HeaderspacePacketSet, ArrayPacketSet>;
