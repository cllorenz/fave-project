#include "bdd_packet_set.h"

namespace net_plumber {

BDDPacketSet::BDDPacketSet(bdd ps, const size_t length) : ps(ps), length(length) {
    /* empty */
}


BDDPacketSet::BDDPacketSet(const size_t length) : length(length) {
    // TODO
}


BDDPacketSet::BDDPacketSet(const size_t length, enum bit_val val) : length(length) {
    // TODO
}


BDDPacketSet::BDDPacketSet(const Json::Value& val, size_t length) : length(length) {
    // TODO
}


BDDPacketSet::BDDPacketSet(const BDDPacketSet& other) {
    this->length = other.length;
    this->ps_bdd = other.ps_bdd;
}


BDDPacketSet::~BDDPacketSet() {
    // TODO
}


std::string
BDDPacketSet::to_str(void) {
    // TODO
}


void
BDDPacketSet::to_json(Json::Value& res) {
    // TODO
}


void
BDDPacketSet::compact(void) {
    // TODO
}


size_t
BDDPacketSet::count(void) {
    // TODO
}


size_t
BDDPacketSet::count_diff(void) {
    // TODO
}


void
BDDPacketSet::enlarge(size_t len) {
    // TODO
}


void
BDDPacketSet::diff(PacketSet *other) {
    // TODO
}


void
BDDPacketSet::intersect(PacketSet *other) {
    // TODO
}

void
BDDPacketSet::psunion(PacketSet *other) {
    // TODO
}


void
BDDPacketSet::minus(PacketSet *other) {
    // TODO
}


void
BDDPacketSet::psand(PacketSet *other) {
    // TODO
}


bool
BDDPacketSet::is_empty(void) {
    // TODO
}


bool
BDDPacketSet::is_equal(PacketSet *other) {
    // TODO
}


bool BDDPacketSet::is_subset_equal(PacketSet *other) {
    // TODO
}


bool
BDDPacketSet::is_subset(PacketSet *other) {
    // TODO
}

void
BDDPacketSet::rewrite(PacketSet *mask, PacketSet *rewrite) {
    // TODO
}


void
BDDPacketSet::negate(void) {
    // TODO
}

} /* namespace net_plumber */
