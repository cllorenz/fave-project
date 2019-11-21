#ifndef SRC_NET_PLUMBER_PACKET_SET_H_
#define SRC_NET_PLUMBER_PACKET_SET_H_

#include "../jsoncpp/jsonrpc.h"

namespace net_plumber {

class PacketSet {
  public:
    static PacketSet* from_str(std::string);
    virtual std::string to_str(void) = 0;
    static PacketSet* from_json(const Json::Value&);

    virtual void compact(void) = 0;
    static PacketSet *copy(void);

    virtual size_t count(void) = 0;
    virtual void enlarge(size_t len) = 0;

    virtual void diff(PacketSet *) = 0;
    virtual void intersect(PacketSet *) = 0;
    virtual void psunion(PacketSet *) = 0;
    virtual void minus(PacketSet *) = 0;
    virtual void psand(PacketSet *) = 0;

    virtual bool is_empty(void) = 0;
    virtual bool is_equal(PacketSet *) = 0;
    virtual bool is_subset_equal(PacketSet *) = 0;
    virtual bool is_subset(PacketSet *) = 0;

    virtual void rewrite(PacketSet* /*mask*/, PacketSet* /*rewrite*/) = 0;
    virtual void negate(void) = 0;
};

} /* namespace net_plumber */

#endif // SRC_NET_PLUMBER_PACKET_SET_H_
