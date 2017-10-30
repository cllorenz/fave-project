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

#ifndef POLICY_CHECKER_H_
#define POLICY_CHECKER_H_

class PolicyProbeNode;

#include "policy_probe_node.h"
#include <list>

extern "C" {
  #include "../headerspace/hs.h"
}

enum ACTION_TYPE {
    ACTION_UNKNOWN = -1,
    ACTION_ALLOW,
    ACTION_DENY
};

struct policy_rule {
    ACTION_TYPE action;
    hs *match;
};

class PolicyChecker {

    private:
        int length;
        std::list<struct policy_rule *> *policy_rules;
        hs *allow_space;
        hs *deny_space;

        std::list<PolicyProbeNode *> *probes;

        void _recalculate_firewall_auth_spaces(void);
        void _notify_probes();

    public:
        PolicyChecker(int length);
        virtual ~PolicyChecker();

        void add_policy_rule(uint32_t index, hs *match, ACTION_TYPE action);
        void remove_policy_rule(uint32_t index);
        bool check_path(const hs *in, const hs *out);

        std::list<PolicyProbeNode *>::iterator register_probe(PolicyProbeNode *);
        void unregister_probe(std::list<PolicyProbeNode *>::iterator p);
};
#endif  // POLICY_CHECKER_H_
