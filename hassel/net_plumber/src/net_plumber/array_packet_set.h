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

    void diff(PacketSet *) { /* empty */ }
    void intersect(PacketSet *);
    void psunion(PacketSet *) { /* empty */ }
    void minus(PacketSet *) { /* empty */ }
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
