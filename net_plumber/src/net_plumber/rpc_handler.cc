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

#include <csignal>

#include "rpc_handler.h"
#include "array_packet_set.h"
#include "hs_packet_set.h"
#include "net_plumber_utils.h"
#ifdef USE_BDD
#include "bdd_packet_set.h"
#endif

using namespace log4cxx;
using namespace Json::Rpc;
using namespace std;

namespace net_plumber {

LoggerPtr rpc_logger(Logger::getLogger("JsonRpc"));

template<typename T>
T *val_to_array(const Json::Value &val) {
  if (val.isNull()) {
    return nullptr;
  }
  const char *v = val.asCString();

  if (strlen(v) == 0) {
        return nullptr;
  }

  std::string s = std::string(v);
#ifdef GENERIC_PS
  return new T(s);
#else
  return array_from_str(s.c_str());
#endif
}

template<typename T1, typename T2>
T1 *val_to_hs(const Json::Value &val, const size_t len) {
#ifdef GENERIC_PS
  T1 *res = new T1(len);
#else
  T1 *res = hs_create(len);
#endif
  if (val.isString()) {
#ifdef GENERIC_PS
    T2 *tmp = val_to_array<T2>(val);
    res->psunion2(tmp);
    delete tmp;
#else
    hs_add(res, val_to_array<T2>(val));
#endif
  }
  else if (val.isObject()) {
    const Json::Value &list = val["list"];
    const Json::Value &diff = val["diff"];
#ifdef NEW_HS
    hs_vec *v_list = &res->list;
    for (Json::Value::ArrayIndex i = 0; i < list.size(); i++)
      hs_vec_append(v_list, val_to_array<T2>(list[i]));

    hs_vec *v_diff = &res->diff;
    for (Json::Value::ArrayIndex i = 0; i < diff.size(); i++)
      hs_vec_append(v_diff, val_to_array<T2>(diff[i]));
#else
    for (Json::Value::ArrayIndex i = 0; i < list.size(); i++) {
#ifdef GENERIC_PS
      T2 *tmp1 = val_to_array<T2>(list[i]);
      res->psunion2(tmp1);
      delete tmp1;
#else
      hs_add(res, val_to_array<T2>(list[i]));
#endif

      const Json::Value &d = diff[i];
      for (Json::Value::ArrayIndex j = 0; j < d.size(); j++) {
#ifdef GENERIC_PS
        T2 *tmp2 = val_to_array<T2>(d[j]);
        res->minus2(tmp2, j);
        delete tmp2;
#else
        hs_vec_append(&res->list.diff[i], val_to_array<T2>(d[j]), true);
#endif
      }
    }
#endif
  }
  return res;
}

List_t val_to_list(const Json::Value &val) {
  const size_t val_size = val.size();
  uint32_t *elems = (uint32_t *)malloc(val_size * sizeof(uint32_t));

  for (Json::Value::ArrayIndex i = 0; i < val_size; i++)
    elems[i] = val[i].asUInt();
  List_t ret = make_sorted_list_from_array(val_size, elems);

  free(elems);
  return ret;
}

template<typename T1, typename T2>
Condition<T1, T2> *val_to_path(const Json::Value &pathlets) {
  PathCondition<T1, T2> *path = new PathCondition<T1, T2>();
  for (Json::Value::ArrayIndex i = 0; i < pathlets.size(); i++) {
    const Json::Value &val = pathlets[i];
    const char *type = val["type"].asCString();
    PathSpecifier<T1, T2> *p = nullptr;
    if (!strcasecmp(type, "port")) p = new PortSpecifier<T1, T2>(val["port"].asUInt());
    else if (!strcasecmp(type, "table")) p = new TableSpecifier<T1, T2>(val["table"].asUInt());
    else if (!strncasecmp(type, "next", 4) || !strncasecmp(type, "last", 4)) {
      const Json::Value &arg = !strcasecmp(type + 5, "ports") ? val["ports"] : val["tables"];
      List_t l = val_to_list(arg);
      if (!strcasecmp(type, "next_ports")) p = new NextPortsSpecifier<T1, T2>(l);
      else if (!strcasecmp(type, "next_tables")) p = new NextTablesSpecifier<T1, T2>(l);
      else if (!strcasecmp(type, "last_ports")) p = new LastPortsSpecifier<T1, T2>(l);
      else if (!strcasecmp(type, "last_tables")) p = new LastTablesSpecifier<T1, T2>(l);
    }
    else if (!strcasecmp(type, "skip_next")) p = new SkipNextArbSpecifier<T1, T2>();
    else if (!strcasecmp(type, "skip")) p = new SkipNextSpecifier<T1, T2>();
    else if (!strcasecmp(type, "end")) p = new EndPathSpecifier<T1, T2>();
    path->add_pathlet(p);
  }
  return path;
}

template<typename T1, typename T2>
Condition<T1, T2> *val_to_cond(const Json::Value &val, const size_t length) {
  if (val.isNull()) return nullptr;
  const char *type = val["type"].asCString();
  if (!strcasecmp(type, "true")) return new TrueCondition<T1, T2>();
  if (!strcasecmp(type, "false")) return new FalseCondition<T1, T2>();
  if (!strcasecmp(type, "path")) return val_to_path<T1, T2>(val["pathlets"]);
  if (!strcasecmp(type, "header")) return new HeaderCondition<T1, T2>(val_to_hs<T1, T2>(val["header"], length));
  if (!strcasecmp(type, "not")) return new NotCondition<T1, T2>(val_to_cond<T1, T2>(val["arg"], length));
  if (!strcasecmp(type, "and") || !strcasecmp(type, "or")) {
    Condition<T1, T2> *c1 = val_to_cond<T1, T2>(val["arg1"], length);
    Condition<T1, T2> *c2 = val_to_cond<T1, T2>(val["arg2"], length);
    if (!strcasecmp(type, "and")) return new AndCondition<T1, T2>(c1, c2);
    else return new OrCondition<T1, T2>(c1, c2);
  }
  return nullptr;
}

template<class T1, class T2>
using RpcFn = bool (RpcHandler<T1, T2>::*) (const Json::Value &, Json::Value &);

template<class T1, class T2>
void RpcHandler<T1, T2>::initServer (Server *server) {
#define FN(NAME) {#NAME, &RpcHandler<T1, T2>::NAME}
  struct { string name; RpcFn<T1, T2> fn; } methods[] = {
    FN(init), FN(destroy),
    FN(add_link), FN(remove_link),
    FN(add_table), FN(remove_table),
    FN(add_rule), FN(remove_rule),
    FN(add_rules),
    FN(add_source), FN(remove_source),
    FN(add_source_probe), FN(remove_source_probe),
#ifdef PIPE_SLICING
    FN(add_slice), FN(remove_slice),
    FN(add_slice_matrix), FN(remove_slice_matrix),
    FN(add_slice_allow), FN(remove_slice_allow),
    FN(print_slice_matrix),
    FN(dump_slices_pipes),
    FN(dump_slices),
#endif
    FN(print_table),
    FN(print_topology),
    FN(print_plumbing_network),
    FN(reset_plumbing_network),
    FN(dump_plumbing_network),
    FN(dump_flows),
    FN(dump_flow_trees),
    FN(dump_pipes),
    FN(stop),
#ifdef CHECK_ANOMALIES
    FN(check_anomalies),
#endif
    FN(check_compliance),
    FN(expand)
  };
  size_t n = sizeof methods / sizeof *methods;
  for (size_t i = 0; i < n; i++)
    server->AddMethod (new RpcMethod<RpcHandler<T1, T2> > (*this, methods[i].fn, methods[i].name));
#undef FN
}

#define LOG_MSG_RESET do {\
    log_msg.str(""); \
    log_msg.clear(); \
  } while(0)

#define PROTO(NAME) \
  template<class T1, class T2>\
  bool RpcHandler<T1, T2>::NAME (const Json::Value &req, Json::Value &resp) { \
    stringstream log_msg; \
    if (rpc_logger->isTraceEnabled()) {\
      log_msg << "Recv: " << req; \
      LOG4CXX_TRACE(rpc_logger,log_msg.str()); \
      LOG_MSG_RESET; \
    } \
    resp["id"] = req["id"]; resp["jsonrpc"] = req["jsonrpc"]; \
    double start, end; start = get_cpu_time_ms();

#define FINI do { \
    return true; \
  } while (0)

#define RETURN(VAL) \
    end = get_cpu_time_ms(); \
    log_msg << "Event handling time: " << (end - start) << "ms for " << req["method"]; \
    if (netPlumber) log_msg << "(ID1: " << netPlumber->get_last_event().id1 << ")."; \
    else log_msg << "."; \
    LOG4CXX_INFO(rpc_logger,log_msg.str()); \
    LOG_MSG_RESET; \
    resp["result"] = (VAL); \
    if (rpc_logger->isTraceEnabled()) {\
      log_msg << "Send: " << resp; \
      LOG4CXX_TRACE(rpc_logger,log_msg.str()); \
      LOG_MSG_RESET; \
    } \
    do { FINI; } while (0)

#define ERROR(MSG) do { \
    resp["error"]["code"] = 1; resp["error"]["message"] = (MSG); FINI; \
  } while (0)

#define PARAM(NAME) req["params"][#NAME]
#define VOID Json::Value::null

PROTO(init)
  length = PARAM(length).asUInt64();
  if (netPlumber) ERROR ("Already initialized.");
  netPlumber = new NetPlumber<T1, T2>(length);
  RETURN(VOID);
}

PROTO(destroy)
  delete netPlumber;
  netPlumber = nullptr;
  RETURN(VOID);
}

PROTO(stop)
  delete netPlumber;
  netPlumber = nullptr;
  raise(SIGTERM);
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
  const uint32_t table = PARAM(table).asUInt();
  const uint32_t index = PARAM(index).asUInt();
  List_t in = val_to_list(PARAM(in));
  List_t out = val_to_list(PARAM(out));
  T2 *match = val_to_array<T2>(PARAM(match));
#ifdef GENERIC_PS
  if (!match || match->is_empty()) { delete match; match = nullptr; }
  if (!match) match = new T2(length, BIT_X);
#else
  if (!match) array_create(length, BIT_X);
#endif
  T2 *mask = val_to_array<T2>(PARAM(mask));
  T2 *rw = val_to_array<T2>(PARAM(rw));
  uint64_t ret = netPlumber->add_rule(table, index, in, out, match, mask, rw);
  RETURN((Json::Value::UInt64) ret);
}

PROTO(add_rules)
  Json::Value rules = PARAM(rules);
  Json::Value ret(Json::arrayValue);
  for (Json::ArrayIndex i = 0; i < rules.size(); i++) {
    Json::Value rule = rules[i];
    const uint32_t table = rule["table"].asUInt();
    const uint32_t index = rule["index"].asUInt();
    List_t in = val_to_list(rule["in"]);
    List_t out = val_to_list(rule["out"]);
    T2 *match = val_to_array<T2>(rule["match"]);
#ifdef GENERIC_PS
    if (!match || match->is_empty()) { delete match; match = nullptr; }
    if (!match) match = new T2(length, BIT_X);
#else
    if (!match) match = array_create(length, BIT_X);
#endif
    T2 *mask = val_to_array<T2>(rule["mask"]);
    T2 *rw = val_to_array<T2>(rule["rw"]);
    uint64_t np_id = netPlumber->add_rule(table, index, in, out, match, mask, rw);
    ret.append((Json::Value::UInt64) np_id);
  }
  RETURN(ret);
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
  T1 *h = val_to_hs<T1, T2>(PARAM(hs), length);
  List_t ports = val_to_list(PARAM(ports));
  const uint64_t id = PARAM(id).asUInt64();
  uint64_t ret = netPlumber->add_source(h, ports, id);
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
  Condition<T1, T2> *filter = val_to_cond<T1, T2>(PARAM(filter), length);
  if (!filter) filter = new TrueCondition<T1, T2>();
  Condition<T1, T2> *test = val_to_cond<T1, T2>(PARAM(test), length);
  if (!test) test = new TrueCondition<T1, T2>();
  T2 *match = val_to_array<T2>(PARAM(match));
#ifdef GENERIC_PS
  if (!match || match->is_empty()) match = new T2(length, BIT_X);
#else
  if (!match) match = array_create(length, BIT_X);
#endif
  const uint64_t id = PARAM(id).asUInt64();
  uint64_t ret = netPlumber->add_source_probe(
    ports, mode, match, filter, test, nullptr, nullptr, id
  );
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
  T1 *net_space = val_to_hs<T1, T2>(PARAM(net_space),length);

  bool ret = true;
  ret = netPlumber->add_slice(id,net_space);
  if (!ret) delete net_space;
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

#ifdef PIPE_SLICING
PROTO(add_slice_matrix);
    std::string m = PARAM(matrix).asString();
    bool ret = true;
    ret = netPlumber->add_slice_matrix(m);
    RETURN(Json::Value(ret));
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
PROTO(remove_slice_matrix);
    netPlumber->remove_slice_matrix();
    RETURN(VOID);
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
PROTO(add_slice_allow);
    uint64_t id1 = PARAM(id1).asUInt64();
    uint64_t id2 = PARAM(id2).asUInt64();
    bool ret = true;
    ret = netPlumber->add_slice_allow(id1, id2);
    RETURN(Json::Value(ret));
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
PROTO(remove_slice_allow);
    uint64_t id1 = PARAM(id1).asUInt64();
    uint64_t id2 = PARAM(id2).asUInt64();
    netPlumber->remove_slice_allow(id1, id2);
    RETURN(VOID);
}
#endif

#ifdef PIPE_SLICING
PROTO(print_slice_matrix);
    netPlumber->print_slice_matrix();
    RETURN(VOID);
}
#endif /* PIPE_SLICING */

#ifdef PIPE_SLICING
PROTO(dump_slices_pipes);
    std::string dir = PARAM(dir).asString();
    netPlumber->dump_slices_pipes(dir);
    RETURN(VOID);
}
#endif /* PIPE_SLICING */


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
  netPlumber = new NetPlumber<T1, T2>(length);
  RETURN(VOID);
}

/*
 * This RPC expands the global vector length to <length> bit (padded)
 */
PROTO(expand)
  size_t len = PARAM(length).asUInt64();
  assert (len % 8 == 0);
  size_t ret = netPlumber->expand((len / 8) + ((len % 8) ? 1 : 0));
  this->length = ret;
  RETURN((Json::Value::UInt64) ret);
}

PROTO(dump_plumbing_network)
  const std::string dir = PARAM(dir).asString();
  netPlumber->dump_plumbing_network(dir);
  RETURN(VOID);
}

PROTO(dump_flows)
  const std::string dir = PARAM(dir).asString();
  netPlumber->dump_flows(dir);
  RETURN(VOID);
}

PROTO(dump_flow_trees)
    const std::string dir = PARAM(dir).asString();
    const bool simple = PARAM(simple).asBool();
    netPlumber->dump_flow_trees(dir, simple);
    RETURN(VOID);
}

PROTO(dump_pipes)
  const std::string dir = PARAM(dir).asString();
  netPlumber->dump_pipes(dir);
  RETURN(VOID);
}

#ifdef PIPE_SLICING
PROTO(dump_slices)
  const std::string dir = PARAM(dir).asString();
  netPlumber->dump_slices(dir);
  RETURN(VOID);
}
#endif /* PIPE_SLICING */

#ifdef CHECK_ANOMALIES
PROTO(check_anomalies)
  const uint32_t table_id = PARAM(table_id).asUInt();
  const bool use_shadow = PARAM(use_shadow).asBool();
  const bool use_reach = PARAM(use_reach).asBool();
  const bool use_general = PARAM(use_general).asBool();
  const struct anomalies_config_t anomalies { use_shadow, use_reach, use_general };
  netPlumber->check_anomalies(table_id, &anomalies);
  RETURN(VOID);
}
#endif

PROTO(check_compliance)
  /*
   * JSON format: {dst:[(src,valid,cond)]}
   * if there is no condition, then cond == null
   */
  std::map<uint64_t, std::vector<std::tuple<uint64_t, bool, T2*>>> rules;

  auto json_rules = PARAM(rules);

  for (Json::Value::iterator policy_it = json_rules.begin(); policy_it != json_rules.end(); policy_it++) {
    uint64_t src = std::stoull(policy_it.key().asString());
    std::vector<std::tuple<uint64_t, bool, T2*>> dst_tpls;
    auto dsts_json = *policy_it;
    for (Json::ArrayIndex i = 0; i < dsts_json.size(); i++) {

      uint64_t dst = dsts_json[i][0].asUInt64();
      bool valid = dsts_json[i][1].asBool();
      T2 *cond = val_to_array<T2>(dsts_json[i][2]);
      std::tuple<uint64_t, bool, T2*> dst_tpl {dst, valid, cond};
      dst_tpls.push_back(dst_tpl);
    }
    rules[src] = dst_tpls;
  }
  netPlumber->check_compliance(&rules);
  RETURN(VOID);
}

#ifdef GENERIC_PS
template class RpcHandler<HeaderspacePacketSet, ArrayPacketSet>;

template HeaderspacePacketSet* val_to_hs<HeaderspacePacketSet, ArrayPacketSet>(const Json::Value&, const size_t);
template ArrayPacketSet* val_to_array<ArrayPacketSet>(const Json::Value&);
template Condition<HeaderspacePacketSet, ArrayPacketSet>* val_to_path<HeaderspacePacketSet, ArrayPacketSet>(const Json::Value&);
template Condition<HeaderspacePacketSet, ArrayPacketSet> *val_to_cond<HeaderspacePacketSet, ArrayPacketSet>(const Json::Value&, const size_t);

#ifdef USE_BDD
template class RpcHandler<BDDPacketSet, BDDPacketSet>;

template BDDPacketSet* val_to_array<BDDPacketSet>(const Json::Value&);
template BDDPacketSet* val_to_hs<BDDPacketSet, BDDPacketSet>(const Json::Value&, const size_t);
template Condition<BDDPacketSet, BDDPacketSet>* val_to_path<BDDPacketSet, BDDPacketSet>(const Json::Value&);
template Condition<BDDPacketSet, BDDPacketSet> *val_to_cond<BDDPacketSet, BDDPacketSet>(const Json::Value&, const size_t);
#endif
#else
template class RpcHandler<hs, array_t>;

template array_t* val_to_array<array_t>(const Json::Value&);
template hs* val_to_hs<hs, array_t>(const Json::Value&, const size_t);
template Condition<hs, array_t>* val_to_path<hs, array_t>(const Json::Value&);
template Condition<hs, array_t> *val_to_cond<hs, array_t>(const Json::Value&, const size_t);
#endif
} /* namespace net_plumber */

