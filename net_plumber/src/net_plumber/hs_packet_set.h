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

#ifndef SRC_NET_PLUMBER_HS_PACKET_SET_H_
#define SRC_NET_PLUMBER_HS_PACKET_SET_H_

extern "C" {
  #include "../headerspace/hs.h"
}
#include "packet_set.h"
#include "array_packet_set.h"

namespace net_plumber {

class HeaderspacePacketSet : public PacketSet {
  protected:
    static log4cxx::LoggerPtr logger;

  public:
    struct hs hs = {0, {0, 0, 0, 0}};

    HeaderspacePacketSet(struct hs *);
    HeaderspacePacketSet(const size_t);
    HeaderspacePacketSet(const std::string);
    HeaderspacePacketSet(const Json::Value&, size_t);
    HeaderspacePacketSet(const HeaderspacePacketSet&);

    virtual ~HeaderspacePacketSet();

    std::string to_str(void);
    void to_json(Json::Value&);

    void enlarge(size_t len);

    void intersect(PacketSet *);
    void intersect2(ArrayPacketSet *);
    void psunion(PacketSet *);
    void psunion2(ArrayPacketSet *);
    void diff2(ArrayPacketSet *);
    void diff(PacketSet *);
    void minus(PacketSet *);
    void minus2(ArrayPacketSet *, const size_t);
#ifdef USE_INV
    void psand(PacketSet *) { /* empty */ };
#endif

    bool is_empty(void);
    bool is_equal(PacketSet *);
    bool is_subset_equal(PacketSet *);
    bool is_subset(PacketSet *);

    void rewrite(PacketSet* /*mask*/, PacketSet* /*rewrite*/);
    void rewrite2(ArrayPacketSet* /*mask*/, ArrayPacketSet* /*rewrite*/);
    void negate(void);
    void compact(void);
    void compact2(ArrayPacketSet * /*mask*/);
    void unroll(void);
    size_t count(void);
    size_t count_diff(void);
};

} /* namespace net_plumber */

#endif // SRC_NET_PLUMBER_HS_PACKET_SET_H_
