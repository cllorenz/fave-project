#ifndef SRC_NET_PLUMBER_PACKET_SET_H_
#define SRC_NET_PLUMBER_PACKET_SET_H_

#include "../jsoncpp/json/json.h"

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

    virtual void rewrite(PacketSet* /*mask*/, PacketSet* /*rewrite*/) = 0;
    virtual void negate(void) = 0;
};

} /* namespace net_plumber */

#endif // SRC_NET_PLUMBER_PACKET_SET_H_
