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

#ifndef MAIN_PROCESSES_H_
#define MAIN_PROCESSES_H_

#include "net_plumber.h"

template<typename T1, typename T2>
void load_netplumber_from_dir(
    std::string json_file_path,
    net_plumber::NetPlumber<T1, T2> *N,
    T2 *filter
#ifdef PIPE_SLICING
    , size_t hdr_len
#endif
);
template<typename T1, typename T2>
void load_policy_file(std::string json_policy_file,
                      net_plumber::NetPlumber<T1, T2> *N, T2 *filter);

#endif /* MAIN_PROCESSES_H_ */
