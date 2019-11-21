#include "hs_packet_set.h"
#include "rpc_handler.h"
extern "C" {
  #include "../headerspace/array.h"
}

namespace net_plumber {

HeaderspacePacketSet::HeaderspacePacketSet(struct hs *hs) : hs(hs) {
    /* empty */
}


HeaderspacePacketSet::HeaderspacePacketSet(size_t length) {
    this->hs = hs_create(length);
}


HeaderspacePacketSet::~HeaderspacePacketSet() {
    hs_free(this->hs);
}


std::string
HeaderspacePacketSet::to_str(void) {
    return std::string(hs_to_str(this->hs));
}


int
get_length_from_val(const Json::Value& val) {
    if (val.isString()) return strlen(val.asString().c_str());
    else if (val.isObject()) {
        return val["length"].asInt();
    } else { // should never happen
        throw;
    }
}

static HeaderspacePacketSet*
from_json(const Json::Value& val) {
    int len = get_length_from_val(val);
    return new HeaderspacePacketSet(val_to_hs<struct hs, array_t>(val, len));
}


HeaderspacePacketSet *
HeaderspacePacketSet::copy(void) {
    return new HeaderspacePacketSet(hs_copy_a(this->hs));
}


void
HeaderspacePacketSet::enlarge(size_t len) {
    hs_enlarge(this->hs, len);
}


void
HeaderspacePacketSet::intersect(PacketSet *other) {
    assert(this->hs->len == ((HeaderspacePacketSet *)other)->hs->len);
    hs_isect(this->hs, ((HeaderspacePacketSet *)other)->hs);
}


void
HeaderspacePacketSet::intersect(ArrayPacketSet *other) {
    assert(this->hs->len == other->length);
    hs_isect_arr(this->hs, this->hs, other->array);
}


void
HeaderspacePacketSet::psunion(PacketSet *other) {
    assert(this->hs->len == ((HeaderspacePacketSet *)other)->hs->len);
    hs_add_hs(this->hs, ((HeaderspacePacketSet *)other)->hs);
}


void
HeaderspacePacketSet::psunion(ArrayPacketSet *other) {
    assert(this->hs->len == other->length);
    hs_add(this->hs, other->array);
}


void
HeaderspacePacketSet::diff(PacketSet *other) {
    this->diff((ArrayPacketSet *)other);
}


void
HeaderspacePacketSet::diff(ArrayPacketSet *other) {
    assert(this->hs->len == other->length);
    hs_diff(this->hs, other->array);
}


void
HeaderspacePacketSet::minus(PacketSet *other) {
    assert(this->hs->len == ((HeaderspacePacketSet *)other)->hs->len);
    hs_minus(this->hs, ((HeaderspacePacketSet *)other)->hs);
}


bool
HeaderspacePacketSet::is_empty(void) {
    return hs_is_empty(this->hs);
}


bool
HeaderspacePacketSet::is_equal(PacketSet *other) {
    assert(this->hs->len == ((HeaderspacePacketSet *)other)->hs->len);
    return hs_is_equal(this->hs, ((HeaderspacePacketSet *)other)->hs);
}


bool HeaderspacePacketSet::is_subset_equal(PacketSet *other) {
    assert(this->hs->len == ((HeaderspacePacketSet *)other)->hs->len);
    return hs_is_sub_eq(this->hs, ((HeaderspacePacketSet *)other)->hs);
}


bool
HeaderspacePacketSet::is_subset(PacketSet *other) {
    assert(this->hs->len == ((HeaderspacePacketSet *)other)->hs->len);
    return hs_is_sub(this->hs, ((HeaderspacePacketSet *)other)->hs);
}

void
HeaderspacePacketSet::rewrite(PacketSet *mask, PacketSet *rewrite) {
    this->rewrite((ArrayPacketSet *)mask, (ArrayPacketSet *)rewrite);
}

void
HeaderspacePacketSet::rewrite(ArrayPacketSet *mask, ArrayPacketSet *rewrite) {
    assert(this->hs->len == mask->length && this->hs->len ==rewrite->length);
    hs_rewrite(this->hs, mask->array, rewrite->array);
}


void
HeaderspacePacketSet::negate(void) {
    hs_cmpl(this->hs);
}


void
HeaderspacePacketSet::compact(void) {
    hs_compact(this->hs);
}


size_t
HeaderspacePacketSet::count(void) {
    return hs_count(this->hs);
}

} /* namespace net_plumber */
