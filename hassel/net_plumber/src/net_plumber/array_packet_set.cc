#include "array_packet_set.h"
#include "rpc_handler.h"
extern "C" {
  #include "../headerspace/hs.h"
}

namespace net_plumber {

ArrayPacketSet::ArrayPacketSet(array_t *array, size_t length) : array(array), length(length) {
    /* empty */
}


ArrayPacketSet::ArrayPacketSet(size_t length) : length(length) {
    this->array = array_create(length, BIT_X);
}


ArrayPacketSet::~ArrayPacketSet() {
    array_free(this->array);
}


size_t
length_from_array_cstr(const char *s) {
    return strlen(s);
}


ArrayPacketSet *
from_str(std::string s) {
    return new ArrayPacketSet(
        array_from_str(s.c_str()),
        length_from_array_cstr(s.c_str())
    );
}


std::string
ArrayPacketSet::to_str(void) {
    return std::string(array_to_str(this->array, this->length, false));
}


size_t
length_from_array_val(const Json::Value& val) {
    return length_from_array_cstr(val.asCString());
}


static ArrayPacketSet*
from_json(const Json::Value& val) {
    return new ArrayPacketSet(val_to_array<struct hs, array_t>(val), length_from_array_val(val));
}


ArrayPacketSet *
ArrayPacketSet::copy(void) {
    return new ArrayPacketSet(array_copy(this->array, this->length), this->length);
}


void
ArrayPacketSet::enlarge(size_t len) {
    const size_t olen = this->length;
    this->length += len;
    array_resize(this->array, olen, this->length);
}


void
ArrayPacketSet::intersect(PacketSet *other) {
    assert(this->length == ((ArrayPacketSet *)other)->length);
    array_isect_a(this->array, ((ArrayPacketSet *)other)->array, this->length);
}


void
ArrayPacketSet::psand(PacketSet *other) {
    assert(this->length == ((ArrayPacketSet *)other)->length);
    array_and(this->array, ((ArrayPacketSet *)other)->array, this->length, this->array);
}


bool
ArrayPacketSet::is_empty(void) {
    return array_is_empty(this->array, this->length);
}


bool
ArrayPacketSet::is_equal(PacketSet *other) {
    assert(this->length == ((ArrayPacketSet *)other)->length);
    return array_is_eq(this->array, ((ArrayPacketSet *)other)->array, this->length);
}


bool ArrayPacketSet::is_subset_equal(PacketSet *other) {
    assert(this->length == ((ArrayPacketSet *)other)->length);
    return array_is_sub_eq(this->array, ((ArrayPacketSet *)other)->array, this->length);
}


bool
ArrayPacketSet::is_subset(PacketSet *other) {
    assert(this->length == ((ArrayPacketSet *)other)->length);
    return array_is_sub(this->array, ((ArrayPacketSet *)other)->array, this->length);
}

void
ArrayPacketSet::rewrite(PacketSet *mask, PacketSet *rewrite) {
    assert(
        this->length == ((ArrayPacketSet *)mask)->length &&
        this->length == ((ArrayPacketSet *)rewrite)->length
    );
    array_rewrite(
        this->array,
        ((ArrayPacketSet *)mask)->array,
        ((ArrayPacketSet *)rewrite)->array,
        this->length
    );
}


void
ArrayPacketSet::negate(void) {
    array_not_a(this->array, this->length);
}

} /* namespace net_plumber */
