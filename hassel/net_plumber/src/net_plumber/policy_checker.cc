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

   Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#include "policy_checker.h"
#include <stdlib.h>

using namespace std;

PolicyChecker::PolicyChecker(int length) : length(length) {
    this->policy_rules = new std::list<struct policy_rule *>();
    this->allow_space = hs_create(length);
    this->deny_space = hs_create(length);
    this->probes = new std::list<PolicyProbeNode *>();
}

PolicyChecker::~PolicyChecker() {
    std::list<struct policy_rule *>::iterator it,tmp;
    for (it = policy_rules->begin(); it != policy_rules->end(); ) {
        hs_free((*it)->match);
        free(*it);
        tmp = it++;
        policy_rules->erase(tmp);
    }
    delete policy_rules;
    hs_free(allow_space);
    hs_free(deny_space);
    delete probes;
}

void PolicyChecker::_recalculate_firewall_auth_spaces() {

    hs *allow_space = hs_create(this->length);
    hs *deny_space = hs_create(this->length);

    list<struct policy_rule *>::iterator r;

    for (r = policy_rules->begin(); r != policy_rules->end(); r++) {
        struct policy_rule *rule = *r;
        if (rule->action == ACTION_ALLOW) {
            hs_minus(rule->match,deny_space);
            hs_add_hs(allow_space,rule->match);
        }
        if (rule->action == ACTION_DENY) {
            hs_minus(rule->match,allow_space);
            hs_add_hs(deny_space,rule->match);
        }
    }

    hs_free(this->allow_space);
    this->allow_space = allow_space;
    hs_free(this->deny_space);
    this->deny_space = deny_space;
}

void PolicyChecker::_notify_probes() {
    list<PolicyProbeNode *>::iterator p;
    for (p = probes->begin(); p != probes->end(); p++) (*p)->reprocess_flows();
}

list<PolicyProbeNode *>::iterator PolicyChecker::register_probe(PolicyProbeNode *probe) {
    probes->push_front(probe);
    return probes->begin();
}

void PolicyChecker::unregister_probe(list<PolicyProbeNode *>::iterator p) {
    probes->erase(p);
}

void PolicyChecker::add_policy_rule(uint32_t index, hs *match, ACTION_TYPE action) {
    if (index < policy_rules->size()) {
        list<struct policy_rule *>::iterator r = policy_rules->begin();
        advance(r,index);
        struct policy_rule *rule = (struct policy_rule *)malloc(sizeof(*rule));
        rule->action = action;
        rule->match = match;
        policy_rules->insert(r,rule);
        _recalculate_firewall_auth_spaces();
        _notify_probes();
    }
}

void PolicyChecker::remove_policy_rule(uint32_t index) {
    if (index < policy_rules->size()) {
        list<struct policy_rule *>::iterator r = policy_rules->begin();
        advance(r,index);
        hs_free((*r)->match);
        free(*r);
        policy_rules->erase(r);
        _recalculate_firewall_auth_spaces();
        _notify_probes();
    }
}

bool PolicyChecker::check_path(const hs *in, const hs *out) {

    if (!hs_is_sub_eq(in,allow_space)) return false;

    hs tmp = {length,{0}};
    hs_add_hs(&tmp,out);
    hs_isect(&tmp,deny_space);

    if (!hs_is_empty(&tmp)) {
        hs_destroy(&tmp);
        return false;
    }

    hs_destroy(&tmp);
    return true;
}
