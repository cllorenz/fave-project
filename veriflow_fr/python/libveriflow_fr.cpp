/*
   Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

   This file is part of FaVe.

   FaVe is free software: you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   FaVe is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with FaVe.  If not, see <https://www.gnu.org/licenses/>.
*/

/*
   libveriflow_fr -- in-process pybind11 bindings over the VeriFlow-FR engine
   (VERIFLOW_PLAN.md D3, condition 4), driven by fave/veriflow/adapter.py.

   A thin shell: every call maps to one engine call. The hot paths -- adding
   rules and answering a query set for many starts -- cross the boundary once
   per rule and once per query set, not once per EC.
*/

#include <chrono>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "../src/queries.h"
#include "../src/veriflow.h"

namespace py = pybind11;
using namespace vf;

namespace {

py::int_ to_py(u128 v) {
  py::int_ hi((uint64_t)(v >> 64)), lo((uint64_t)v);
  return py::int_(hi.attr("__lshift__")(64).attr("__or__")(lo));
}

class PyNetwork {
 public:
  explicit PyNetwork(const std::vector<std::pair<std::string, unsigned>> &fields)
      : net_(make_layout(fields)) {}

  void add_table(uint32_t t) { net_.add_table(t); }
  void add_port(uint64_t p, uint32_t t) { net_.add_port(p, t); }
  void add_link(uint64_t a, uint64_t b) { net_.add_link(a, b); }
  bool remove_link(uint64_t a, uint64_t b) { return net_.remove_link(a, b); }

  // Returns the number of ECs the rule affects (the ECs themselves are not
  // needed in bulk mode, and returning them would cost a conversion each).
  size_t add_rule(uint64_t id, uint32_t table, int64_t priority, int64_t in_port,
                  const std::string &match, const std::vector<uint64_t> &out,
                  bool consume) {
    Rule r;
    r.id = id;
    r.table = table;
    r.priority = priority;
    r.in_port = in_port;
    r.match = match;
    r.out_ports = out;
    r.consume = consume;
    return net_.add_rule(r).size();
  }

  // Add a rule without computing its ECs: bulk loading, where no insertion is
  // verified on its own. `rewrites`: (field index, the ternary value it is set to).
  void load_rule(uint64_t id, uint32_t table, int64_t priority, int64_t in_port,
                 const std::string &match, const std::vector<uint64_t> &out,
                 bool consume,
                 const std::vector<std::pair<size_t, std::string>> &rewrites) {
    Rule r;
    r.id = id;
    r.table = table;
    r.priority = priority;
    r.in_port = in_port;
    r.match = match;
    r.out_ports = out;
    r.consume = consume;
    for (const auto &rw : rewrites) r.rewrites.push_back({rw.first, prefix_to_interval(rw.second)});
    net_.load_rule(r);
  }

  // Q22's bulk query: (delivered per start, finished, stopped_at, predicted,
  // single_table, local ECs sliced, states expanded, local ECs per table).
  // `state`: Q4's revisit rule -- the thesis's visited states, or NetPlumber's
  // path rule.
  // `scan`: V3b's per-field scan flags (empty: plain slicing).
  py::tuple local_deliveries(const std::string &range,
                             const std::vector<std::pair<uint32_t, int64_t>> &starts,
                             uint64_t budget, bool state,
                             const std::vector<bool> &scan) const {
    LocalResult r;
    {
      py::gil_scoped_release release;
      r = vf::local_deliveries(net_, range, starts, budget,
                               state ? Revisit::STATE : Revisit::PATH, scan);
    }
    return py::make_tuple(r.delivered, r.finished, r.stopped_at, r.predicted,
                          r.single_table, r.local_ecs, r.hops, r.per_table);
  }

  size_t remove_rule(uint64_t id) { return net_.remove_rule(id).size(); }

  py::list affected_ecs(const std::string &range) const {
    py::list out;
    for (const EC &ec : net_.affected_ecs(range)) {
      py::list ranges;
      for (const Interval &i : ec.ranges) ranges.append(py::make_tuple(to_py(i.lo), to_py(i.hi)));
      out.append(ranges);
    }
    return out;
  }

  // The rule deciding at (table, in_port) for the single packet `point`
  // (exact bits), 0 for none: the LPM guard's primitive.
  uint64_t decide_point(const std::string &point, uint32_t table, int64_t in_port) const {
    std::vector<EC> ecs = net_.affected_ecs(point);
    const Rule *r = net_.forwarding_graph(ecs.at(0)).decide(table, in_port);
    return r ? r->id : 0;
  }

  std::vector<std::set<uint32_t>> deliveries(
      const std::string &range,
      const std::vector<std::pair<uint32_t, int64_t>> &starts) const {
    py::gil_scoped_release release;
    return vf::deliveries(net_, range, starts);
  }

  // DN §4.3.2's query on one node-level edge: (affected ECs, graphs built,
  // seconds). Timed inside the engine, so the binding's overhead is not in it.
  py::tuple link_failure(uint32_t table, int64_t in_port, uint64_t to_port) const {
    size_t graphs = 0;
    const auto t0 = std::chrono::steady_clock::now();
    const size_t ecs = vf::link_failure(net_, table, in_port, to_port, &graphs).size();
    const auto t1 = std::chrono::steady_clock::now();
    return py::make_tuple(ecs, graphs, std::chrono::duration<double>(t1 - t0).count());
  }

  // The EC count of a set without building the ECs: (per-field range counts,
  // the exact product or None when it exceeds 128 bits, the product as float).
  py::tuple ec_count(const std::string &range) const {
    const ECCount c = net_.ec_count(range);
    py::object exact = c.saturated ? py::object(py::none()) : py::object(to_py(c.exact));
    return py::make_tuple(c.per_field, exact, c.approx);
  }

 private:
  static Layout make_layout(const std::vector<std::pair<std::string, unsigned>> &fields) {
    std::vector<Field> fs;
    for (const auto &f : fields) fs.push_back({f.first, f.second});
    return Layout(fs);
  }
  Network net_;
};

}  // namespace

PYBIND11_MODULE(libveriflow_fr, m) {
  m.doc() = "VeriFlow-FR: an independent VeriFlow, from the literature alone";
  m.attr("ANY_PORT") = ANY_PORT;
  py::class_<PyNetwork>(m, "Network")
      .def(py::init<const std::vector<std::pair<std::string, unsigned>> &>())
      .def("add_table", &PyNetwork::add_table)
      .def("add_port", &PyNetwork::add_port)
      .def("add_link", &PyNetwork::add_link)
      .def("remove_link", &PyNetwork::remove_link)
      .def("add_rule", &PyNetwork::add_rule)
      .def("load_rule", &PyNetwork::load_rule, py::arg("id"), py::arg("table"),
           py::arg("priority"), py::arg("in_port"), py::arg("match"), py::arg("out"),
           py::arg("consume"), py::arg("rewrites") = std::vector<std::pair<size_t, std::string>>())
      .def("local_deliveries", &PyNetwork::local_deliveries, py::arg("range"),
           py::arg("starts"), py::arg("budget"), py::arg("state"),
           py::arg("scan") = std::vector<bool>())
      .def("remove_rule", &PyNetwork::remove_rule)
      .def("affected_ecs", &PyNetwork::affected_ecs)
      .def("decide_point", &PyNetwork::decide_point)
      .def("deliveries", &PyNetwork::deliveries)
      .def("link_failure", &PyNetwork::link_failure)
      .def("ec_count", &PyNetwork::ec_count);
}
