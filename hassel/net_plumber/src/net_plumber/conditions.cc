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
#include <sstream>

using namespace std;

PathCondition::~PathCondition() {
  list<PathSpecifier*>::iterator it;
  for (it = pathlets.begin(); it != pathlets.end(); it++) {
    delete *it;
  }
}

void PathCondition::add_pathlet(PathSpecifier *pathlet) {
  pathlets.push_back(pathlet);
}

bool PathCondition::check(Flow *f) {
/*
  list<PathSpecifier*>::iterator it;
  for (it = pathlets.begin(); it != pathlets.end(); it++) {
    if (!(*it)->check_and_move(f)) return false;
  }
  return true;
*/
  stack<pair<list<PathSpecifier*>::iterator,Flow*> >decision_points;
  list<PathSpecifier*>::iterator it = pathlets.begin();
  while (it != pathlets.end()) {
    // case 1: end of flow and no alternatives -> path does not meet spec, final decline
    if (!f && decision_points.empty()) {
      return false;

    // case 2: end of flow but still alternatives open -> jump to decision point and continue with next alternative
    } else if (!f && !decision_points.empty()) {
      pair<list<PathSpecifier*>::iterator,Flow*> dp = decision_points.top();
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
          pair<list<PathSpecifier*>::iterator,Flow*> dp = decision_points.top();
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

string PathCondition::to_string() {
  stringstream res;
  res << "path ~ \"";
  list<PathSpecifier*>::iterator it;
  for (it = pathlets.begin(); it != pathlets.end(); it++) {
    res << (*it)->to_string();
  }
  res << "\"";
  return res.str();
}

bool HeaderCondition::check(Flow *f) {
  hs *tmp = hs_isect_a(f->processed_hs, h);
  bool result = false;
  if (tmp) {
    hs_comp_diff(tmp);
    if (tmp->list.used > 0) result = true;
    hs_free(tmp);
  }
  return result;
}

void HeaderCondition::enlarge(uint32_t length) {
	hs_enlarge(this->h,length);
}

string HeaderCondition::to_string() {
  stringstream res;
  char *c = hs_to_str(h);
  res << "header ~ " << string(c);
  free(c);
  return res.str();
}

bool PortSpecifier::check_and_move(Flow* &f) {
  while (f->p_flow != f->node->get_EOSFI()) {
    if (f->in_port == port && f->node->is_at_input_stage()) {
      f = *f->p_flow;
      return true;
    }
    f = *f->p_flow;
  }
  return false;
}

string PortSpecifier::to_string() {
  stringstream res;
  res << ".*(p = " << this->port << ")";
  return res.str();
}

bool TableSpecifier::check_and_move(Flow* &f) {
  while (f->p_flow != f->node->get_EOSFI()) {
    if (f->node->get_type() == RULE && ((RuleNode*)(f->node))->table == table
        && f->node->is_at_input_stage()){
      f = *f->p_flow;
      return true;
    }
    f = *f->p_flow;
  }
  return false;
}

string TableSpecifier::to_string() {
  stringstream res;
  res << ".*(t = " << this->table << ")";
  return res.str();
}

bool NextPortsSpecifier::check_and_move(Flow* &f) {
  while (f->p_flow != f->node->get_EOSFI() && !f->node->is_at_input_stage()) {
      f = *f->p_flow;
  }
  if (f->p_flow != f->node->get_EOSFI() && elem_in_sorted_list(f->in_port, ports)) {
    f = *f->p_flow;
    return true;
  }
  return false;
}

string NextPortsSpecifier::to_string() {
  stringstream res;
  res << "(p in " << list_to_string(this->ports) << ")";
  return res.str();
}

bool NextTablesSpecifier::check_and_move(Flow* &f) {
  while (f->p_flow != f->node->get_EOSFI() && !f->node->is_at_input_stage()) {
      f = *f->p_flow;
  }
  if (f->p_flow != f->node->get_EOSFI() && f->node->get_type() == RULE &&
      elem_in_sorted_list(((RuleNode*)(f->node))->table, tables)) {
    f = *f->p_flow;
    return true;
  }
  return false;
}

string NextTablesSpecifier::to_string() {
  stringstream res;
  res << "(t in " << list_to_string(this->tables) << ")";
  return res.str();
}


bool LastPortsSpecifier::check_and_move(Flow* &f) {
  Flow *prev = NULL;
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

string LastPortsSpecifier::to_string() {
  stringstream res;
  res << ".*(p in " << list_to_string(this->ports) << ")$";
  return res.str();
}

bool LastTablesSpecifier::check_and_move(Flow* &f) {
  Flow *prev = NULL;
  while (f->p_flow != f->node->get_EOSFI()) {
    prev = f;
    f = *f->p_flow;
  }
  if (prev && prev->node->get_type() == RULE && prev->node->is_at_input_stage()
      && elem_in_sorted_list(((RuleNode*)(prev->node))->table, tables)) {
    return true;
  } else {
    return false;
  }
}

string LastTablesSpecifier::to_string() {
  printf("next table specifier called\n");
  stringstream res;
  res << ".*(t in " << list_to_string(this->tables) << ")$";
  return res.str();
}

bool SkipNextSpecifier::check_and_move(Flow* &f) {
  while (f->p_flow != f->node->get_EOSFI() && !f->node->is_at_input_stage()) {
      f = *f->p_flow;
  }
  if (f->p_flow != f->node->get_EOSFI()) {
    f = *f->p_flow;
    return true;
  }
  return false;
}

bool SkipNextArbSpecifier::check_and_move(Flow* &f) {
  return true;
}

void TrueCondition::to_json(Json::Value& res) {
  res = true;
}

void FalseCondition::to_json(Json::Value& res) {
  res = false;
}

void AndCondition::to_json(Json::Value& res) {
  res["type"] = "and";

  Json::Value arg1;
  c1->to_json(arg1);
  res["arg1"] = arg1;

  Json::Value arg2;
  c2->to_json(arg2);
  res["arg2"] = arg2;
}

void OrCondition::to_json(Json::Value& res) {
  res["type"] = "or";

  Json::Value arg1;
  c1->to_json(arg1);
  res["arg1"] = arg1;

  Json::Value arg2;
  c2->to_json(arg2);
  res["arg2"] = arg2;
}

void NotCondition::to_json(Json::Value& res) {
  res["type"] = "not";

  Json::Value arg;
  c->to_json(arg);

  res["arg"] = arg;
}

void HeaderCondition::to_json(Json::Value& res) {
  res["type"] = "header";
  Json::Value hs(Json::objectValue);
  hs_to_json(hs,h);
  res["header"] = hs;
}

void PathCondition::to_json(Json::Value& res) {
  res["type"] = "path";

  Json::Value pathlets(Json::arrayValue);
  for (
    std::list<PathSpecifier*>::iterator it = this->pathlets.begin();
    it != this->pathlets.end();
    it++
  ) {
    Json::Value pathlet(Json::objectValue);
    (*it)->to_json(pathlet);
    pathlets.append(pathlet);
  }
  res["pathlets"] = pathlets;
}

void PortSpecifier::to_json(Json::Value& res) {
  res["type"] = "port";
  res["port"] = this->port;
}

void TableSpecifier::to_json(Json::Value& res) {
  res["type"] = "table";
  res["table"] = this->table;
}

void NextPortsSpecifier::to_json(Json::Value& res) {
  res["type"] = "next_ports";
  res["ports"] = list_to_json(ports);
}

void NextTablesSpecifier::to_json(Json::Value& res) {
  res["type"] = "next_tables";
  res["tables"] = list_to_json(tables);
}

void LastPortsSpecifier::to_json(Json::Value& res) {
  res["type"] = "last_ports";
  res["ports"] = list_to_json(ports);
}

void LastTablesSpecifier::to_json(Json::Value& res) {
  res["type"] = "last_tables";
  res["tables"] = list_to_json(tables);
}

void SkipNextSpecifier::to_json(Json::Value& res) {
  res["type"] = "skip";
}

void SkipNextArbSpecifier::to_json(Json::Value& res) {
  res["type"] = "skip_next";
}

void EndPathSpecifier::to_json(Json::Value& res) {
  res["type"] = "end";
}

