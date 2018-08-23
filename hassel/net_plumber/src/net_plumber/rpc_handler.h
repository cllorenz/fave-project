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

#ifndef _RPC_HANDLER_H_
#define _RPC_HANDLER_H_

#include "net_plumber.h"
#include "../jsoncpp/jsonrpc.h"

namespace net_plumber {

array_t *val_to_array(const Json::Value &val);
hs *val_to_hs(const Json::Value &val, int len);
List_t val_to_list(const Json::Value &val);
Condition *val_to_path(const Json::Value &pathlets);
Condition *val_to_cond(const Json::Value &val, int length);
#ifdef POLICY_PROBES
ACTION_TYPE val_to_action(const char *action);
#endif

class RpcHandler {
  NetPlumber *netPlumber;
  size_t length;
public:
  RpcHandler(NetPlumber *N): netPlumber(N), length(N->get_length()) { }
  void initServer(Json::Rpc::Server *server);

private:
#define FN(NAME) bool NAME (const Json::Value &, Json::Value &)
  FN(init); FN(destroy);
  FN(add_link); FN(remove_link);
  FN(add_table); FN(remove_table);
  FN(add_rule); FN(remove_rule);
  FN(add_source); FN(remove_source);
  FN(add_source_probe); FN(remove_source_probe);
#ifdef PIPE_SLICING
  FN(add_slice); FN(remove_slice);
  FN(add_slice_matrix); FN(remove_slice_matrix);
  FN(add_slice_allow); FN(remove_slice_allow);
  FN(print_slice_matrix);
  FN(dump_slices_pipes);
#endif
#ifdef FIREWALL_RULES
  FN(add_fw_rule);
  FN(remove_fw_rule);
#endif
#ifdef POLICY_PROBES
  FN(add_policy_rule); FN(remove_policy_rule);
  FN(add_policy_probe); FN(remove_policy_probe);
#endif
  FN(print_table);
  FN(print_topology);
  FN(print_plumbing_network);
  FN(reset_plumbing_network);
  FN(expand);
  FN(dump_plumbing_network);
  FN(dump_flows);
  FN(dump_pipes);
  FN(stop);
#undef FN
};

}

#endif

