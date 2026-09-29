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

#ifndef VERIFLOW_FR_TEST_UTIL_H_
#define VERIFLOW_FR_TEST_UTIL_H_

#include <vector>

#include "../src/veriflow.h"

namespace vftest {

inline vf::u128 ip(unsigned a, unsigned b, unsigned c, unsigned d) {
  return ((vf::u128)a << 24) | ((vf::u128)b << 16) | ((vf::u128)c << 8) | d;
}

inline vf::Rule rule(uint64_t id, uint32_t table, int64_t priority,
                     const std::string &match, std::vector<uint64_t> out,
                     int64_t in_port = vf::ANY_PORT) {
  vf::Rule r;
  r.id = id;
  r.table = table;
  r.priority = priority;
  r.match = match;
  r.out_ports = out;
  r.in_port = in_port;
  return r;
}

// One table with the given ports, none of them linked.
inline void one_table(vf::Network &net, uint32_t table,
                      std::vector<uint64_t> ports) {
  net.add_table(table);
  for (uint64_t p : ports) net.add_port(p, table);
}

}  // namespace vftest

#endif  // VERIFLOW_FR_TEST_UTIL_H_
