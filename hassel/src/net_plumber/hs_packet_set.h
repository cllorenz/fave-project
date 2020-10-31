#ifndef SRC_NET_PLUMBER_HS_PACKET_SET_H_
#define SRC_NET_PLUMBER_HS_PACKET_SET_H_

extern "C" {
  #include "../headerspace/hs.h"
}
#include "packet_set.h"
#include "array_packet_set.h"

namespace net_plumber {

class HeaderspacePacketSet : public PacketSet {
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
