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
    struct hs *hs;

    HeaderspacePacketSet(size_t);
    HeaderspacePacketSet(struct hs *);
    virtual ~HeaderspacePacketSet();

    static HeaderspacePacketSet *from_str(std::string) { return nullptr; };
    std::string to_str(void);
    static HeaderspacePacketSet *from_json(const Json::Value&);

    HeaderspacePacketSet *copy(void);

    void enlarge(size_t len);

    void intersect(PacketSet *);
    void intersect(ArrayPacketSet *);
    void psunion(PacketSet *);
    void psunion(ArrayPacketSet *);
    void diff(PacketSet *);
    void diff(ArrayPacketSet *);
    void minus(PacketSet *);
    void psand(PacketSet *) { /* empty */ };

    bool is_empty(void);
    bool is_equal(PacketSet *);
    bool is_subset_equal(PacketSet *);
    bool is_subset(PacketSet *);

    void rewrite(PacketSet* /*mask*/, PacketSet* /*rewrite*/);
    void rewrite(ArrayPacketSet* /*mask*/, ArrayPacketSet* /*rewrite*/);
    void negate(void);
    void compact(void);
    size_t count(void);
};

} /* namespace net_plumber */

#endif // SRC_NET_PLUMBER_HS_PACKET_SET_H_
