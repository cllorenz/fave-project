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

#include "rpc_handler.h"
#include <ctime>
extern "C" {
  #include "../headerspace/hs.h"
}

#include "net_plumber_utils.h"

#include "policy_checker.h"

using namespace log4cxx;
using namespace Json::Rpc;
using namespace std;

namespace net_plumber {

LoggerPtr rpc_logger(Logger::getLogger("JsonRpc"));

array_t *val_to_array(const Json::Value &val) {
  if (val.isNull()) {
    return NULL;
  } else {
    return array_from_str(val.asCString());
  }
}

hs *val_to_hs(const Json::Value &val, int len) {
  hs *res = hs_create (len);
  if (val.isString()) hs_add (res, val_to_array(val));
  else if (val.isObject()) {
    const Json::Value &list = val["list"];
    const Json::Value &diff = val["diff"];
    hs_vec *v = &res->list;
    for (Json::Value::ArrayIndex i = 0; i < list.size(); i++) {
      hs_vec_append(v, val_to_array(list[i]), false);

      const Json::Value &d = diff[i];
      hs_vec *v_diff = &v->diff[i];
      for (Json::Value::ArrayIndex j = 0; j < d.size(); j++)
        hs_vec_append(v_diff, val_to_array(d[j]), true);
    }
  }
  return res;
}

List_t val_to_list(const Json::Value &val) {
  uint32_t elems[val.size()];
  for (unsigned i = 0; i < val.size(); i++)
    elems[i] = val[i].asUInt();
  return make_sorted_list_from_array(val.size(),elems);
}

Condition *val_to_path(const Json::Value &pathlets) {
  PathCondition *path = new PathCondition();
  for (Json::Value::ArrayIndex i = 0; i < pathlets.size(); i++) {
    const Json::Value &val = pathlets[i];
    const char *type = val["type"].asCString();
    PathSpecifier *p = NULL;
    if (!strcasecmp(type, "port")) p = new PortSpecifier(val["port"].asUInt());
    else if (!strcasecmp(type, "table")) p = new TableSpecifier(val["table"].asUInt());
    else if (!strncasecmp(type, "next", 4) || !strncasecmp(type, "last", 4)) {
      const Json::Value &arg = !strcasecmp(type + 5, "ports") ? val["ports"] : val["tables"];
      List_t l = val_to_list(arg);
      if (!strcasecmp(type, "next_ports")) p = new NextPortsSpecifier(l);
      else if (!strcasecmp(type, "next_tables")) p = new NextTablesSpecifier(l);
      else if (!strcasecmp(type, "last_ports")) p = new LastPortsSpecifier(l);
      else if (!strcasecmp(type, "last_tables")) p = new LastTablesSpecifier(l);
    }
    else if (!strcasecmp(type, "skip")) p = new SkipNextSpecifier();
    else if (!strcasecmp(type, "end")) p = new EndPathSpecifier();
    path->add_pathlet(p);
  }
  return path;
}

Condition *val_to_cond(const Json::Value &val, int length) {
  if (val.isNull()) return NULL;
  const char *type = val["type"].asCString();
  if (!strcasecmp(type, "true")) return new TrueCondition();
  if (!strcasecmp(type, "false")) return new FalseCondition();
  if (!strcasecmp(type, "path")) return val_to_path(val["pathlets"]);
  if (!strcasecmp(type, "header")) return new HeaderCondition(val_to_hs(val["header"], length));
  if (!strcasecmp(type, "not")) return new NotCondition(val_to_cond(val["arg"], length));
  if (!strcasecmp(type, "and") || !strcasecmp(type, "or")) {
    Condition *c1 = val_to_cond(val["arg1"], length);
    Condition *c2 = val_to_cond(val["arg2"], length);
    if (!strcasecmp(type, "and")) return new AndCondition(c1, c2);
    else return new OrCondition(c1, c2);
  }
  return NULL;
}

ACTION_TYPE val_to_action(const char *action) {
  if (strcmp(action,"allow")) return ACTION_ALLOW;
  if (strcmp(action,"deny")) return ACTION_DENY;
  return ACTION_UNKNOWN;
}

typedef bool (RpcHandler::*RpcFn) (const Json::Value &, Json::Value &);

void RpcHandler::initServer (Server *server) {
#define FN(NAME) {#NAME, &RpcHandler::NAME}
  struct { string name; RpcFn fn; } methods[] = {
    FN(init), FN(destroy),
    FN(add_link), FN(remove_link),
    FN(add_table), FN(remove_table),
    FN(add_rule), FN(remove_rule),
    FN(add_source), FN(remove_source),
    FN(add_source_probe), FN(remove_source_probe),
#ifdef PIPE_SLICING
    FN(add_slice), FN(remove_slice),
#endif
#ifdef FIREWALL_RULES
    FN(add_fw_rule), FN(remove_fw_rule),
#endif
#ifdef POLICY_PROBES
    FN(add_policy_rule), FN(remove_policy_rule),
    FN(add_policy_probe), FN(remove_policy_probe),
#endif
    FN(print_table),
    FN(print_topology),
    FN(print_plumbing_network),
    FN(reset_plumbing_network),
    FN(expand)
  };
  int n = sizeof methods / sizeof *methods;
  for (int i = 0; i < n; i++)
    server->AddMethod (new RpcMethod<RpcHandler> (*this, methods[i].fn, methods[i].name));
#undef FN
}

#define LOG_MSG_RESET do {\
    log_msg.str(""); \
    log_msg.clear(); \
  } while(0)

/*
    log_msg << "Recv: " << req; \
    LOG4CXX_DEBUG(rpc_logger,log_msg.str()); \
    LOG_MSG_RESET; \
 */
#define PROTO(NAME) \
  bool RpcHandler::NAME (const Json::Value &req, Json::Value &resp) { \
    stringstream log_msg; \
    resp["id"] = req["id"]; resp["jsonrpc"] = req["jsonrpc"]; \
    double start, end; start = get_cpu_time_ms();

/*
    log_msg << "Send: " << resp; \
    LOG4CXX_DEBUG(rpc_logger,log_msg.str()); \
    LOG_MSG_RESET; \
 */
#define FINI do { \
    return true; \
  } while (0)

#define RETURN(VAL) \
    end = get_cpu_time_ms(); \
    log_msg << "Event handling time: " << (end - start) << "ms for " << req["method"] << "."; \
    LOG4CXX_INFO(rpc_logger,log_msg.str()); \
    LOG_MSG_RESET; \
    do { resp["result"] = (VAL); FINI; } while (0)

#define ERROR(MSG) do { \
    resp["error"]["code"] = 1; resp["error"]["message"] = (MSG); FINI; \
  } while (0)

#define PARAM(NAME) req["params"][#NAME]
#define VOID Json::Value::null

PROTO(init)
  length = PARAM(length).asInt();
  if (netPlumber) ERROR ("Already initialized.");
  netPlumber = new NetPlumber(length);
  RETURN(VOID);
}

PROTO(destroy)
  delete netPlumber;
  netPlumber = NULL;
  RETURN(VOID);
}

PROTO(add_link)
  uint32_t from = PARAM(from_port).asUInt();
  uint32_t to = PARAM(to_port).asUInt();
  netPlumber->add_link(from, to);
  RETURN(VOID);
}

PROTO(remove_link)
  uint32_t from = PARAM(from_port).asUInt();
  uint32_t to = PARAM(to_port).asUInt();
  netPlumber->remove_link(from, to);
  RETURN(VOID);
}

PROTO(add_table)
  uint32_t id = PARAM(id).asUInt();
  List_t ports = val_to_list(PARAM(in));
  netPlumber->add_table(id,ports);
  RETURN(VOID);
}

PROTO(remove_table)
  uint32_t id = PARAM(id).asUInt();
  netPlumber->remove_table(id);
  RETURN(VOID);
}

PROTO(add_rule)
  uint32_t table = PARAM(table).asUInt();
  int index = PARAM(index).asInt();
  List_t in = val_to_list(PARAM(in));
  List_t out = val_to_list(PARAM(out));
  array_t *match = val_to_array(PARAM(match));
  array_t *mask = val_to_array(PARAM(mask));
  array_t *rw = val_to_array(PARAM(rw));
  uint64_t ret = netPlumber->add_rule(table, index, in, out, match, mask, rw);
  RETURN((Json::Value::UInt64) ret);
}

PROTO(remove_rule)
  uint64_t node = PARAM(node).asUInt64();
  double st, en; st = get_cpu_time_us();
  netPlumber->remove_rule(node);
  en = get_cpu_time_us();
  log_msg << "Only deleting takes: " << (en - st) << "us.";
  LOG4CXX_INFO(rpc_logger,log_msg.str());
  LOG_MSG_RESET;
  RETURN(VOID);
}

PROTO(add_source)
  hs *h = val_to_hs(PARAM(hs), length);
  List_t ports = val_to_list(PARAM(ports));
  uint64_t ret = netPlumber->add_source(h, ports);
  RETURN((Json::Value::UInt64) ret);
}

PROTO(remove_source)
  uint64_t id = PARAM(id).asUInt64();
  netPlumber->remove_source(id);
  RETURN(VOID);
}

PROTO(add_source_probe)
  List_t ports = val_to_list(PARAM(ports));
  PROBE_MODE mode = !strcasecmp(PARAM(mode).asCString(), "universal") ? UNIVERSAL : EXISTENTIAL;
  Condition *filter = val_to_cond(PARAM(filter), length);
  Condition *test = val_to_cond(PARAM(test), length);
  uint64_t ret = netPlumber->add_source_probe(ports, mode, filter, test, NULL, NULL);
  RETURN((Json::UInt64) ret);
}

PROTO(remove_source_probe)
  uint64_t id = PARAM(id).asUInt64();
  netPlumber->remove_source_probe(id);
  RETURN(VOID);
}

#ifdef PIPE_SLICING
PROTO(add_slice)
  uint64_t id = PARAM(id).asUInt64();
  hs *net_space = val_to_hs(PARAM(net_space),length);

  bool ret = true;
  ret = netPlumber->add_slice(id,net_space);
  if (!ret) hs_destroy(net_space);
  RETURN(Json::Value(ret));
}
#endif

#ifdef PIPE_SLICING
PROTO(remove_slice)
    uint64_t id = PARAM(id).asUInt64();
    netPlumber->remove_slice(id);
    RETURN(VOID);
}
#endif

#ifdef FIREWALL_RULES
PROTO(add_fw_rule)
    uint32_t table = PARAM(table).asUInt();
    int index = PARAM(index).asInt();
    List_t in_ports = val_to_list(PARAM(in_ports));
    List_t out_ports = val_to_list(PARAM(out_ports));
    hs *fw_match = val_to_hs(PARAM(fw_match),length);
    uint64_t ret = netPlumber->add_fw_rule(table,index,in_ports,out_ports,fw_match);
    RETURN((Json::Value::UInt64) ret);
}
#endif

#ifdef FIREWALL_RULES
PROTO(remove_fw_rule)
    uint64_t id = PARAM(node).asUInt64();
    netPlumber->remove_fw_rule(id);
    RETURN(VOID);
}
#endif

#ifdef POLICY_PROBES
PROTO(add_policy_rule)
    uint32_t index = PARAM(index).asUInt();
    hs *match = val_to_hs(PARAM(match),length);
    ACTION_TYPE action = val_to_action(PARAM(action).asCString());
    if (action == ACTION_UNKNOWN) ERROR("No such action type. Use allow or deny.");
    netPlumber->add_policy_rule(index,match,action);
    RETURN(VOID);
}
#endif

#ifdef POLICY_PROBES
PROTO(remove_policy_rule)
    uint32_t index = PARAM(index).asUInt();
    netPlumber->remove_policy_rule(index);
    RETURN(VOID);
}
#endif

#ifdef POLICY_PROBES
PROTO(add_policy_probe)
    List_t ports = val_to_list(PARAM(ports));
    uint64_t ret = netPlumber->add_policy_probe_node(ports,NULL,NULL);
    RETURN((Json::Value::UInt64) ret);
}
#endif

#ifdef POLICY_PROBES
PROTO(remove_policy_probe)
    uint64_t node = PARAM(node).asUInt64();
    netPlumber->remove_policy_probe_node(node);
    RETURN(VOID);
}
#endif

PROTO(print_table)
  uint64_t id = PARAM(id).asUInt();
  netPlumber->print_table(id);
  RETURN(VOID);
}

PROTO(print_topology)
  netPlumber->print_topology();
  RETURN(VOID);
}

PROTO(print_plumbing_network)
  netPlumber->print_plumbing_network();
  RETURN(VOID);
}

PROTO(reset_plumbing_network)
  netPlumber->~NetPlumber();
  netPlumber = new NetPlumber(length);
  RETURN(VOID);
}

/*
 * This RPC expands the global vector length to <length> bit (padded)
 */
PROTO(expand)
  uint32_t len = PARAM(length).asInt();
  uint32_t ret = netPlumber->expand((len / 8) + ((len % 8) ? 1 : 0));
  length = netPlumber->get_length();
  RETURN((Json::UInt) ret);
}

}

