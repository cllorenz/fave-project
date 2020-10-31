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

#ifndef SRC_NET_PLUMBER_ARRAY_PACKET_SET_H_
#define SRC_NET_PLUMBER_ARRAY_PACKET_SET_H_

extern "C" {
  #include "../headerspace/array.h"
}
#include "packet_set.h"

namespace net_plumber {

class ArrayPacketSet : public PacketSet {
  public:
    array_t *array;
    size_t length;

    ArrayPacketSet(const size_t);
    ArrayPacketSet(array_t *, const size_t);
    ArrayPacketSet(const size_t, enum bit_val);
    ArrayPacketSet(const std::string);
    ArrayPacketSet(const Json::Value&, size_t);
    ArrayPacketSet(const ArrayPacketSet&);
    virtual ~ArrayPacketSet();

    std::string to_str(void);
    void to_json(Json::Value&);

    void compact(void) { /* empty */ }
    void unroll(void) { /* empty */ }
    size_t count(void);
    void enlarge(size_t len);
    void enlarge2(size_t len);

#ifdef USE_DEPRECATED
    void diff(PacketSet *);
#else
    void diff(PacketSet *) { /* empty */ }
#endif
    void intersect(PacketSet *);
    void psunion(PacketSet *) { /* empty */ }
#ifdef USE_DEPRECATED
    void minus(PacketSet *other) { this->diff(other); }
#else
    void minus(PacketSet *) { /* empty */ }
#endif
#ifdef USE_INV
    void psand(PacketSet *);
#endif

    bool is_empty(void);
    bool is_equal(PacketSet *);
    bool is_subset_equal(PacketSet *);
    bool is_subset(PacketSet *);

    void rewrite(PacketSet* /*mask*/, PacketSet* /*rewrite*/);
    void negate(void);

  private:
    void _generic_enlarge(size_t len, enum bit_val val);
};

} /* namespace net_plumber */

#endif // SRC_NET_PLUMBER_ARRAY_PACKET_SET_H_
