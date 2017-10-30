/*
   Copyright 2016 Claas Lorenz

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Authors: cllorenz@uni-potsdam.de (Claas Lorenz),
            peyman.kazemian@gmail.com (Peyman Kazemian)
*/

#ifndef SRC_NET_PLUMBER_PROBE_NODE_COMMONS_H_
#define SRC_NET_PLUMBER_PROBE_NODE_COMMONS_H_

enum PROBE_STATE {
  STOPPED = 0,
  STARTED,
  RUNNING
};

enum PROBE_FLOW_ACTION {
    FLOW_ADD = 0,
    FLOW_MODIFY,
    FLOW_DELETE
};

#endif  // SRC_NET_PLUMBER_PROBE_NODE_COMMONS_H_
