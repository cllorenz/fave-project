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
  // verified on its own.
  void load_rule(uint64_t id, uint32_t table, int64_t priority, int64_t in_port,
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
    net_.load_rule(r);
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

  size_t ec_count(const std::string &range) const {
    return net_.affected_ecs(range).size();
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
      .def("load_rule", &PyNetwork::load_rule)
      .def("remove_rule", &PyNetwork::remove_rule)
      .def("affected_ecs", &PyNetwork::affected_ecs)
      .def("decide_point", &PyNetwork::decide_point)
      .def("deliveries", &PyNetwork::deliveries)
      .def("ec_count", &PyNetwork::ec_count);
}
