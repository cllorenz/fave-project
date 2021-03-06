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
*/

#ifndef NET_PLUMBER_UTILS_H_
#define NET_PLUMBER_UTILS_H_

#include <string>
extern "C" {
  #include "../headerspace/util.h"
  #include "../headerspace/hs.h"
}
#include "../jsoncpp/json/json.h"

struct PACKED List_t {
  uint32_t size;
  uint32_t *list;
  bool shared;
};

List_t      make_sorted_list (uint32_t count,...);
List_t      make_sorted_list_from_array (uint32_t count, uint32_t elems[]);
List_t      make_unsorted_list (uint32_t count,...);
List_t      intersect_sorted_lists (List_t a, List_t b);
std::string list_to_string (List_t p);
bool        elem_in_sorted_list (uint32_t elem, List_t list);
#ifdef USE_DEPRECATED
bool        elem_in_unsorted_list (uint32_t elem, List_t list);
#endif
bool        lists_has_intersection(List_t a, List_t b);
#ifdef USE_DEPRECATED
List_t      copy_list (List_t l);
#endif
Json::Value list_to_json(List_t l);
void hs_to_json(Json::Value& res, hs *h);

double get_wall_time_s(void);
double get_wall_time_ms(void);
double get_wall_time_us(void);
double get_cpu_time_s(void);
double get_cpu_time_ms(void);
double get_cpu_time_us(void);

#endif  // NET_PLUMBER_UTILS_H_
