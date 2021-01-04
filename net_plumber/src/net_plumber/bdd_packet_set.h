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

#ifndef SRC_NET_PLUMBER_BDD_PACKET_SET_H_
#define SRC_NET_PLUMBER_BDD_PACKET_SET_H_

#include <bdd.h>
#include "packet_set.h"
#include "../headerspace/bitval.h"

namespace net_plumber {

class BDDPacketSet : public PacketSet {
  protected:
    static log4cxx::LoggerPtr logger;

  public:
    bdd ps;

    BDDPacketSet(const size_t);
    BDDPacketSet();
    BDDPacketSet(bdd);
    BDDPacketSet(const size_t, enum bit_val);
    BDDPacketSet(enum bit_val);
    BDDPacketSet(const std::string);
    BDDPacketSet(const Json::Value&, size_t);
    BDDPacketSet(const BDDPacketSet&);
    virtual ~BDDPacketSet();

    static void init_result_buffer(void);
    static void destroy_result_buffer(void);
    static void reset_result_buffer(void);
    static void append_result_buffer(std::string);
    static std::vector<std::string> *get_result_buffer(void);

    static void reset_vector_counter(void);
    static void increment_vector_counter(void);
    static size_t get_vector_counter(void);

    std::string to_str(void);
    void to_json(Json::Value&);

    void compact(void);
    void compact2(PacketSet *) { this->compact(); }
    void unroll(void) { /* empty */ }
    size_t count(void);
    size_t count_diff(void);
    void enlarge(size_t);
    void enlarge2(size_t len) { this->enlarge(len); }

    void diff(PacketSet *);
    void diff2(PacketSet *ps) { this->diff(ps); }
    void intersect(PacketSet *);
    void intersect2(PacketSet *ps) { this->intersect(ps); };
    void psunion(PacketSet *);
    void psunion2(PacketSet *ps) { this->psunion(ps); }
    void minus(PacketSet *);
    void minus2(PacketSet *ps, const size_t) { this->minus(ps); }
#ifdef USE_INV
    void psand(PacketSet *);
#endif

    bool is_empty(void);
    bool is_equal(PacketSet *);
    bool is_subset_equal(PacketSet *);
    bool is_subset(PacketSet *);

    void rewrite(PacketSet* /*mask*/, PacketSet* /*rewrite*/);
    void rewrite2(PacketSet* mask, PacketSet* rw) { this->rewrite(mask, rw); }
    void negate(void);
};

} /* namespace net_plumber */

#endif // SRC_NET_PLUMBER_BDD_PACKET_SET_H_
