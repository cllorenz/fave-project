/*
 * FaVe libnetplumber -- in-process pybind11 bindings over NetPlumber's C++ core.
 *
 * See APKEEP_BACKEND.md (P1). This drives NetPlumber<hs, array_t> directly from
 * Python, replacing the JSON-RPC + socket transport with native calls, so the
 * from-zero model-build + compliance cost is not dominated by IPC/serialization.
 *
 * The translation MIRRORS net_plumber/src/net_plumber/rpc_handler.cc exactly:
 * the hot path (rule match/mask/rw, ports) is passed natively, while the rare
 * structured arguments (a source's header space, a probe's filter/test
 * conditions) are accepted as the SAME JSON the RPC client builds and converted
 * with copies of the handler's val_to_* helpers -- so the engine sees identical
 * inputs to the RPC path (bug-for-bug), at zero JSON cost on the rule bulk.
 *
 * Must be compiled with the canonical build's defines for ABI compatibility
 * with the linked .o files: -DWITH_EXTRA_NEW -DCHECK_ANOMALIES -DSTRICT_RW.
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <tuple>
#include <vector>

extern "C" {
#include "array.h"
#include "hs.h"
}

#include "net_plumber_utils.h"
#include "net_plumber.h"
#include "conditions.h"
#include "source_probe_node.h"

#include "json/json.h"

namespace py = pybind11;
using namespace net_plumber;

static const unsigned MAX_CONDITION_DEPTH = 256;

// ---------------------------------------------------------------------------
// Conversions -- faithful copies of the val_to_* helpers in rpc_handler.cc,
// specialised to the canonical build (T1 = hs, T2 = array_t; !GENERIC_PS,
// !NEW_HS). Keep these in lock-step with rpc_handler.cc.
// ---------------------------------------------------------------------------

static array_t *j_to_array(const Json::Value &val) {
    if (val.isNull()) return nullptr;
    const char *v = val.asCString();
    if (std::strlen(v) == 0) return nullptr;
    return array_from_str(v);
}

static List_t vec_to_list(const std::vector<uint32_t> &v) {
    // mirrors val_to_list (rpc_handler.cc), but from a native vector
    uint32_t *elems = (uint32_t *)malloc((v.size() ? v.size() : 1) * sizeof(uint32_t));
    for (size_t i = 0; i < v.size(); i++) elems[i] = v[i];
    List_t ret = make_sorted_list_from_array((uint32_t)v.size(), elems);
    free(elems);
    return ret;
}

static List_t j_to_list(const Json::Value &val) {
    const Json::ArrayIndex n = val.size();
    uint32_t *elems = (uint32_t *)malloc((n ? n : 1) * sizeof(uint32_t));
    for (Json::ArrayIndex i = 0; i < n; i++) elems[i] = val[i].asUInt();
    List_t ret = make_sorted_list_from_array((uint32_t)n, elems);
    free(elems);
    return ret;
}

static struct hs *j_to_hs(const Json::Value &val, const size_t len) {
    struct hs *res = hs_create(len);
    if (val.isString()) {
        hs_add(res, j_to_array(val));
    } else if (val.isObject()) {
        const Json::Value &list = val["list"];
        const Json::Value &diff = val["diff"];
        for (Json::ArrayIndex i = 0; i < list.size(); i++) {
            hs_add(res, j_to_array(list[i]));
            const Json::Value &d = diff[i];
            for (Json::ArrayIndex j = 0; j < d.size(); j++)
                hs_vec_append(&res->list.diff[i], j_to_array(d[j]), true);
        }
    }
    return res;
}

static Condition<hs, array_t> *j_to_path(const Json::Value &pathlets) {
    PathCondition<hs, array_t> *path = new PathCondition<hs, array_t>();
    for (Json::ArrayIndex i = 0; i < pathlets.size(); i++) {
        const Json::Value &val = pathlets[i];
        if (!val.isObject() || !val["type"].isString()) continue;
        const char *type = val["type"].asCString();
        PathSpecifier<hs, array_t> *p = nullptr;
        if (!strcasecmp(type, "port"))
            p = new PortSpecifier<hs, array_t>(val["port"].asUInt());
        else if (!strcasecmp(type, "table"))
            p = new TableSpecifier<hs, array_t>(val["table"].asUInt());
        else if (!strncasecmp(type, "next", 4) || !strncasecmp(type, "last", 4)) {
            const Json::Value &arg =
                !strcasecmp(type + 5, "ports") ? val["ports"] : val["tables"];
            List_t l = j_to_list(arg);
            if (!strcasecmp(type, "next_ports"))       p = new NextPortsSpecifier<hs, array_t>(l);
            else if (!strcasecmp(type, "next_tables")) p = new NextTablesSpecifier<hs, array_t>(l);
            else if (!strcasecmp(type, "last_ports"))  p = new LastPortsSpecifier<hs, array_t>(l);
            else if (!strcasecmp(type, "last_tables")) p = new LastTablesSpecifier<hs, array_t>(l);
        }
        else if (!strcasecmp(type, "skip_next")) p = new SkipNextArbSpecifier<hs, array_t>();
        else if (!strcasecmp(type, "skip"))      p = new SkipNextSpecifier<hs, array_t>();
        else if (!strcasecmp(type, "end"))       p = new EndPathSpecifier<hs, array_t>();
        if (p) path->add_pathlet(p);
    }
    return path;
}

static Condition<hs, array_t> *j_to_cond(const Json::Value &val, const size_t length,
                                         unsigned depth = 0) {
    if (depth > MAX_CONDITION_DEPTH) return nullptr;
    if (!val.isObject() || !val["type"].isString()) return nullptr;
    const char *type = val["type"].asCString();
    if (!strcasecmp(type, "true"))  return new TrueCondition<hs, array_t>();
    if (!strcasecmp(type, "false")) return new FalseCondition<hs, array_t>();
    if (!strcasecmp(type, "path"))  return j_to_path(val["pathlets"]);
    if (!strcasecmp(type, "header"))
        return new HeaderCondition<hs, array_t>(j_to_hs(val["header"], length));
    if (!strcasecmp(type, "not")) {
        Condition<hs, array_t> *c = j_to_cond(val["arg"], length, depth + 1);
        if (!c) return nullptr;
        return new NotCondition<hs, array_t>(c);
    }
    if (!strcasecmp(type, "and") || !strcasecmp(type, "or")) {
        Condition<hs, array_t> *c1 = j_to_cond(val["arg1"], length, depth + 1);
        Condition<hs, array_t> *c2 = j_to_cond(val["arg2"], length, depth + 1);
        if (!c1 || !c2) { delete c1; delete c2; return nullptr; }
        if (!strcasecmp(type, "and")) return new AndCondition<hs, array_t>(c1, c2);
        return new OrCondition<hs, array_t>(c1, c2);
    }
    return nullptr;
}

static Json::Value parse_json(const std::string &s) {
    Json::Value v;
    if (s.empty()) return v;  // null
    Json::Reader reader;       // matches the vendored (amalgamated) jsoncpp
    reader.parse(s, v);
    return v;
}

// ---------------------------------------------------------------------------
// The bound class.
// ---------------------------------------------------------------------------

class LibNetPlumber {
    NetPlumber<hs, array_t> *np_;
    size_t length_;  // bytes (the core's unit)

  public:
    explicit LibNetPlumber(size_t length) : length_(length) {
        np_ = new NetPlumber<hs, array_t>(length);
    }
    ~LibNetPlumber() { delete np_; }

    size_t get_length() const { return length_; }

    // RPC `expand` takes bits (multiple of 8) and converts to bytes.
    size_t expand(size_t length_bits) {
        size_t bytes = (length_bits / 8) + ((length_bits % 8) ? 1 : 0);
        length_ = np_->expand(bytes);
        return length_;
    }

    void add_table(uint32_t id, const std::vector<uint32_t> &ports) {
        np_->add_table(id, vec_to_list(ports));
    }
    void remove_table(uint32_t id) { np_->remove_table(id); }

    uint64_t add_rule(uint32_t table, uint32_t index,
                      const std::vector<uint32_t> &in_ports,
                      const std::vector<uint32_t> &out_ports,
                      const std::string &match, const std::string &mask,
                      const std::string &rw) {
        array_t *m = match.empty() ? array_create(length_, BIT_X)
                                   : array_from_str(match.c_str());
        array_t *mk = mask.empty() ? nullptr : array_from_str(mask.c_str());
        array_t *r  = rw.empty()   ? nullptr : array_from_str(rw.c_str());
        return np_->add_rule(table, index, vec_to_list(in_ports),
                             vec_to_list(out_ports), m, mk, r);
    }
    void remove_rule(uint64_t node_id) { np_->remove_rule(node_id); }

    void add_link(uint32_t from_port, uint32_t to_port) {
        np_->add_link(from_port, to_port);
    }
    void remove_link(uint32_t from_port, uint32_t to_port) {
        np_->remove_link(from_port, to_port);
    }

    // hs_json is the same `hs` param the RPC client builds: either a bare
    // ternary string, or {"list": [...], "diff": [...]}.
    uint64_t add_source(const std::string &hs_json,
                        const std::vector<uint32_t> &ports, uint64_t id) {
        struct hs *h = j_to_hs(parse_json(hs_json), length_);
        return np_->add_source(h, vec_to_list(ports), id);
    }
    void remove_source(uint64_t id) { np_->remove_source(id); }

    // filter_json / test_json are the same condition exprs the RPC client
    // builds (or "" -> TrueCondition, as the handler defaults).
    uint64_t add_source_probe(const std::vector<uint32_t> &ports,
                              const std::string &mode, const std::string &match,
                              const std::string &filter_json,
                              const std::string &test_json, uint64_t id) {
        PROBE_MODE m = !strcasecmp(mode.c_str(), "universal") ? UNIVERSAL : EXISTENTIAL;
        Condition<hs, array_t> *filter = j_to_cond(parse_json(filter_json), length_);
        if (!filter) filter = new TrueCondition<hs, array_t>();
        Condition<hs, array_t> *test = j_to_cond(parse_json(test_json), length_);
        if (!test) test = new TrueCondition<hs, array_t>();
        array_t *match_a = match.empty() ? array_create(length_, BIT_X)
                                         : array_from_str(match.c_str());
        return np_->add_source_probe(vec_to_list(ports), m, match_a, filter, test,
                                     nullptr, nullptr, id);
    }
    void remove_source_probe(uint64_t id) { np_->remove_source_probe(id); }

    // rules: {src_or_dst_node_id: [(other_node_id, valid, cond_str), ...]}.
    // cond_str "" -> nullptr (no header condition). Mirrors the RPC handler,
    // including freeing the cond arrays after the check (free_compliance_rules).
    void check_compliance(
        const std::map<uint64_t,
            std::vector<std::tuple<uint64_t, bool, std::string>>> &rules) {
        std::map<uint64_t, std::vector<std::tuple<uint64_t, bool, array_t *>>> m;
        for (const auto &kv : rules) {
            std::vector<std::tuple<uint64_t, bool, array_t *>> v;
            for (const auto &t : kv.second) {
                const std::string &cond = std::get<2>(t);
                array_t *c = cond.empty() ? nullptr : array_from_str(cond.c_str());
                v.emplace_back(std::get<0>(t), std::get<1>(t), c);
            }
            m[kv.first] = std::move(v);
        }
        np_->check_compliance(&m);
        for (auto &kv : m)
            for (auto &t : kv.second)
                if (std::get<2>(t)) array_free(std::get<2>(t));
    }

    void dump_plumbing_network(const std::string &dir) { np_->dump_plumbing_network(dir); }
    void dump_flows(const std::string &dir) { np_->dump_flows(dir); }
    void dump_flow_trees(const std::string &dir, bool simple) {
        np_->dump_flow_trees(dir, simple);
    }
    void dump_pipes(const std::string &dir) { np_->dump_pipes(dir); }
};

PYBIND11_MODULE(libnetplumber, m) {
    m.doc() = "In-process bindings over NetPlumber's C++ core (FaVe P1).";
    py::class_<LibNetPlumber>(m, "LibNetPlumber")
        .def(py::init<size_t>(), py::arg("length"),
             "Construct a NetPlumber<hs, array_t> with header length in bytes.")
        .def("get_length", &LibNetPlumber::get_length)
        .def("expand", &LibNetPlumber::expand, py::arg("length_bits"))
        .def("add_table", &LibNetPlumber::add_table, py::arg("id"), py::arg("ports"))
        .def("remove_table", &LibNetPlumber::remove_table, py::arg("id"))
        .def("add_rule", &LibNetPlumber::add_rule, py::arg("table"), py::arg("index"),
             py::arg("in_ports"), py::arg("out_ports"), py::arg("match"),
             py::arg("mask"), py::arg("rw"))
        .def("remove_rule", &LibNetPlumber::remove_rule, py::arg("node_id"))
        .def("add_link", &LibNetPlumber::add_link, py::arg("from_port"), py::arg("to_port"))
        .def("remove_link", &LibNetPlumber::remove_link, py::arg("from_port"), py::arg("to_port"))
        .def("add_source", &LibNetPlumber::add_source, py::arg("hs_json"),
             py::arg("ports"), py::arg("id"))
        .def("remove_source", &LibNetPlumber::remove_source, py::arg("id"))
        .def("add_source_probe", &LibNetPlumber::add_source_probe, py::arg("ports"),
             py::arg("mode"), py::arg("match"), py::arg("filter_json"),
             py::arg("test_json"), py::arg("id"))
        .def("remove_source_probe", &LibNetPlumber::remove_source_probe, py::arg("id"))
        .def("check_compliance", &LibNetPlumber::check_compliance, py::arg("rules"))
        .def("dump_plumbing_network", &LibNetPlumber::dump_plumbing_network, py::arg("dir"))
        .def("dump_flows", &LibNetPlumber::dump_flows, py::arg("dir"))
        .def("dump_flow_trees", &LibNetPlumber::dump_flow_trees, py::arg("dir"),
             py::arg("simple") = false)
        .def("dump_pipes", &LibNetPlumber::dump_pipes, py::arg("dir"));
}
