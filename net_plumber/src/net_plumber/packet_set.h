/*
   Copyright 2020 Claas Lorenz

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#ifndef SRC_NET_PLUMBER_PACKET_SET_H_
#define SRC_NET_PLUMBER_PACKET_SET_H_

#include "../jsoncpp/json/json.h"
//#include "mask.h"
#include <sstream>
#include "log4cxx/logger.h"

namespace net_plumber {

class PacketSet {
  public:
    virtual std::string to_str(void) = 0;
    virtual void to_json(Json::Value&) = 0;

    virtual void compact(void) = 0;
    virtual void unroll(void) = 0;

    virtual size_t count(void) = 0;
    virtual void enlarge(size_t len) = 0;

    virtual void diff(PacketSet *) = 0;
    virtual void intersect(PacketSet *) = 0;
    virtual void psunion(PacketSet *) = 0;
    virtual void minus(PacketSet *) = 0;
#ifdef USE_INV
    virtual void psand(PacketSet *) = 0;
#endif

    virtual bool is_empty(void) = 0;
    virtual bool is_equal(PacketSet *) = 0;
    virtual bool is_subset_equal(PacketSet *) = 0;
    virtual bool is_subset(PacketSet *) = 0;

//    virtual void rewrite(Mask<PacketSet>* /*mask*/, Rewrite<PacketSet>* /*rewrite*/) = 0;
    virtual void rewrite(PacketSet* /*mask*/, PacketSet* /*rewrite*/) = 0;
    virtual void negate(void) = 0;
};

} /* namespace net_plumber */

#endif // SRC_NET_PLUMBER_PACKET_SET_H_
