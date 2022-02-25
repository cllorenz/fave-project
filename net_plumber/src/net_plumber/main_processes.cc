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
            jan@sohre.eu (Jan Sohre)
            cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#include "main_processes.h"
#include "rpc_handler.h"
#include "../jsoncpp/json/json.h"
#include <fstream>
#include <dirent.h>
#include <algorithm>
#include "array_packet_set.h"
#include "hs_packet_set.h"
#ifdef USE_BDD
#include "bdd_packet_set.h"
#endif

using namespace net_plumber;
using namespace std;

#ifdef PIPE_SLICING
template<typename T1, typename T2>
void _load_slices_from_file(string json_file_path, NetPlumber<T1, T2> * N, size_t hdr_len) {
  ifstream jsfile;
  Json::Value root;
  Json::Reader reader;

  // read slice definition
  string fname = json_file_path + "/" + "slices.json";
  jsfile.open(fname.c_str());
  if (!jsfile.good()) {
    printf("No such file: %s. Use empty default instead.\n",fname.c_str());
    return;
  }
  reader.parse(jsfile,root,false);
  Json::Value slices = root["slices"];
  for (Json::ArrayIndex i=0; i<slices.size(); i++) {
    T1 *h = val_to_hs<T1, T2>(slices[i]["space"], hdr_len);
    N->add_slice(slices[i]["id"].asInt(), h);
  }
  jsfile.close();
}
#endif /* PIPE_SLICING */

template<typename T1, typename T2>
void load_netplumber_from_dir(
    string json_file_path,
    NetPlumber<T1, T2> * N,
    T2 *filter
#ifdef PIPE_SLICING
    , size_t hdr_len
#endif
) {
  double start, end;
  int rule_counter = 0;
  ifstream jsfile;
  Json::Value root;
  Json::Reader reader;
  list<double> t_list;
  double total_run_time = 0;

#ifdef PIPE_SLICING
  _load_slices_from_file<T1, T2>(json_file_path, N, hdr_len);
#endif

  // read topology
  string file_name = json_file_path + "/" + "topology.json";
  jsfile.open (file_name.c_str());
  if (!jsfile.good()) {
    printf("Error opening the file %s\n",file_name.c_str());
    return;
  }
  reader.parse(jsfile,root,false);
  Json::Value topology = root["topology"];
  for (Json::ArrayIndex i = 0; i < topology.size(); i++) {
    N->add_link(topology[i]["src"].asInt(),topology[i]["dst"].asInt());
  }
  N->print_topology();
  jsfile.close();

  //read every json file.
  struct dirent *ent;
  DIR *dir = opendir(json_file_path.c_str());
#ifdef SORTED_DIR
  std::vector<std::string> files;
  if (dir != nullptr) {
    while ((ent = readdir(dir)) != nullptr) {
      file_name = string(ent->d_name);
      if (file_name.find(".rules.json") != string::npos || file_name.find(".tf.json") != string::npos) {
        files.push_back(file_name);
      }
    }
  }

#ifdef SORTED_FWD
  std::sort(files.begin(), files.end());
#else
  std::sort(files.rbegin(), files.rend());
#endif

  for (auto file: files) {
    file_name = json_file_path + "/" + file;
#else
  if (dir != nullptr) {
    while ((ent = readdir(dir)) != nullptr ) {
      file_name = string(ent->d_name);
      if (file_name.find(".rules.json") != string::npos ||
          file_name.find(".tf.json") != string::npos) {
        // open the json file
        file_name = json_file_path + "/" + file_name;
#endif
        printf("=== Loading rule file %s to NetPlumber ===\n",file_name.c_str());
        jsfile.open (file_name.c_str());
        reader.parse(jsfile,root,false);

        // get the table id, ports and rules
        uint32_t table_id = root["id"].asUInt();
        Json::Value ports = root["ports"];
        Json::Value rules = root["rules"];

        // create the table
        N->add_table(table_id,val_to_list(ports));

        // add the rules
        for (Json::ArrayIndex i = 0; i < rules.size(); i++) {
          long run_time = 0;
          rule_counter++;
          string action = rules[i]["action"].asString();
          uint32_t rule_id = rules[i]["id"].asUInt64() & 0xffffffff;
          if (action == "fwd" || action == "rw" /*|| action == "encap"*/) {
            T2 *match = val_to_array<T2>(rules[i]["match"]);
#ifdef GENERIC_PS
            match->intersect(filter);
            const bool empty = filter && match->is_empty();
#else
            const bool empty = !array_isect_arr_i(match, filter, N->get_length());
#endif
            if (empty) {
              run_time = 0;
            } else {
              start = get_cpu_time_us();
              N->add_rule(table_id,
                          rule_id,
                          val_to_list(rules[i]["in_ports"]),
                          val_to_list(rules[i]["out_ports"]),
                          match,
                          val_to_array<T2>(rules[i]["mask"]),
                          val_to_array<T2>(rules[i]["rewrite"]));
              end = get_cpu_time_us();
              run_time = end - start;
              total_run_time += run_time;
            }
            t_list.push_back(run_time);
          }
#ifdef USE_GROUPS
          else if (action == "multipath") {
            Json::Value mp_rules = rules[i]["rules"];
            uint64_t group = 0;
            for (Json::ArrayIndex i = 0; i < mp_rules.size(); i++) {
              uint32_t rule_id = mp_rules[i]["id"].asUInt64() & 0xffffffff;
              string action = mp_rules[i]["action"].asString();
              if (action == "fwd" || action == "rw" /*|| action == "encap"*/) {
                uint64_t id = N->add_rule_to_group(
                                table_id,
                                rule_id,
                                val_to_list(mp_rules[i]["in_ports"]),
                                val_to_list(mp_rules[i]["out_ports"]),
                                val_to_array<T1, T2>(mp_rules[i]["match"]),
                                val_to_array<T1, T2>(mp_rules[i]["mask"]),
                                val_to_array<T1, T2>(mp_rules[i]["rewrite"]),
                                group);
                if (i == 0) group = id;
              }
            }
          }
#endif
	  if (i % 100 == 99) printf("Loaded %u rules\n", i+1);
        }

        // clean up
        jsfile.close();
#ifndef SORTED_DIR
      }
    }
#endif
    //N->print_plumbing_network();
  }
  double avg = total_run_time / rule_counter;
  std::list<double> t_list_sorted(t_list);
  t_list_sorted.sort();

  auto it = t_list_sorted.begin();
  size_t pos = t_list_sorted.size()/2;
  for (size_t i = 0; i <= pos; i++) it++;
  double median = *it;

  double min = t_list_sorted.front();
  double max = t_list_sorted.back();

  printf(
    "total run time: %.2lf us, no rules: %d, average: %.2lf us, median: %.2lf us, min: %.2lf us, max: %.2lf us\n",
    total_run_time, rule_counter, avg, median, min, max
  );

  closedir(dir);
}

template<typename T1, typename T2>
void load_policy_file(string json_policy_file, NetPlumber<T1, T2> *N, T2 *filter) {
  printf("Loading policy file %s\n", json_policy_file.c_str());
  double start, end;
  ifstream jsfile;
  Json::Value root;
  Json::Reader reader;

  // read topology
  jsfile.open (json_policy_file.c_str());
  if (!jsfile.good()) {
    printf("Error opening the file %s\n",json_policy_file.c_str());
    return;
  }
  printf("Parse policy file: %s...\n", json_policy_file.c_str());
  reader.parse(jsfile,root,false);
  printf("Load policy...\n");
  Json::Value commands = root["commands"];
  start = get_cpu_time_us();
  for (Json::ArrayIndex i = 0; i < commands.size(); i++) {
    string type = commands[i]["method"].asString();
    if (type == "add_source") {
      T1 *h = val_to_hs<T1, T2>(commands[i]["params"]["hs"], N->get_length());
      if (filter) {
#ifdef GENERIC_PS
        h->intersect2(filter);
        const bool empty = h->is_empty();
#else
        const bool empty = !hs_isect_arr_i(h, filter);
#endif
        if (empty) continue;
      }
      List_t ports = val_to_list(commands[i]["params"]["ports"]);
      const uint64_t id = commands[i]["params"]["id"].asUInt64();
      N->add_source(h, ports, id);

    } else if (type == "add_source_probe") {
      List_t ports = val_to_list(commands[i]["params"]["ports"]);
      PROBE_MODE mode = !strcasecmp(commands[i]["params"]["mode"].asCString(), "universal")
          ? UNIVERSAL : EXISTENTIAL;
      T2 *match = val_to_array<T2>(commands[i]["params"]["match"]);
      Condition<T1, T2> *filter = val_to_cond<T1, T2>(commands[i]["params"]["filter"], N->get_length());
      Condition<T1, T2> *test = val_to_cond<T1, T2>(commands[i]["params"]["test"], N->get_length());
      const uint64_t id = commands[i]["params"]["id"].asUInt64();
      N->add_source_probe(ports, mode, match, filter, test, nullptr, nullptr, id);

    } else if (type == "add_link") {
      uint32_t from_port = commands[i]["params"]["from_port"].asUInt();
      uint32_t to_port = commands[i]["params"]["to_port"].asUInt();
      N->add_link(from_port,to_port);

    } else {
      printf("Oooops... unknown command: %s\n", type.c_str());
    }
  }
  end = get_cpu_time_us();
  printf("Loaded policy file in %.2lf seconds (%.2lfus)\n", (end - start)/1000000.0, (end - start));
  jsfile.close();
}

#ifdef CHECK_ANOMALIES
template<typename T1, typename T2>
void check_all_anomalies(NetPlumber<T1, T2> *N) {
  double t_start, t_end;
  const struct anomalies_config_t anomalies { true, false, false };
  t_start = get_cpu_time_us();
  N->check_anomalies(0, &anomalies);
  t_end = get_cpu_time_us();
  printf("Checked anomalies for all tables in %.2lf seconds (%.2lfus)\n", (t_end - t_start)/1000000.0, (t_end - t_start));
}
#endif

#ifdef GENERIC_PS
template void load_netplumber_from_dir<HeaderspacePacketSet, ArrayPacketSet>(
    string,
    NetPlumber<HeaderspacePacketSet, ArrayPacketSet> *,
    ArrayPacketSet *
#ifdef PIPE_SLICING
    , size_t
#endif
);
template void load_policy_file<HeaderspacePacketSet, ArrayPacketSet>(
  string,
  NetPlumber<HeaderspacePacketSet, ArrayPacketSet> *,
  ArrayPacketSet *
);

#ifdef USE_BDD
template void load_netplumber_from_dir<BDDPacketSet, BDDPacketSet>(
    string,
    NetPlumber<BDDPacketSet, BDDPacketSet> *,
    BDDPacketSet *
#ifdef PIPE_SLICING
    , size_t
#endif
);
template void load_policy_file<BDDPacketSet, BDDPacketSet>(
  string,
  NetPlumber<BDDPacketSet, BDDPacketSet> *,
  BDDPacketSet *
);
#ifdef CHECK_ANOMALIES
template void check_all_anomalies(NetPlumber<BDDPacketSet, BDDPacketSet>);
#endif
#endif
#else
template void load_netplumber_from_dir<hs, array_t>(
    string,
    NetPlumber<hs, array_t> *,
    array_t *
#ifdef PIPE_SLICING
    , size_t
#endif
);
template void load_policy_file<hs, array_t>(
  string,
  NetPlumber<hs, array_t> *,
  array_t *
);
#ifdef CHECK_ANOMALIES
template void check_all_anomalies(NetPlumber<hs, array_t>*);
#endif
#endif

