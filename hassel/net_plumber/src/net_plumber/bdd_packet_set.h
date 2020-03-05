#ifndef SRC_NET_PLUMBER_BDD_PACKET_SET_H_
#define SRC_NET_PLUMBER_BDD_PACKET_SET_H_

#include <bdd.h>
#include "packet_set.h"
#include "../headerspace/bitval.h"

namespace net_plumber {

class BDDPacketSet : public PacketSet {
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
