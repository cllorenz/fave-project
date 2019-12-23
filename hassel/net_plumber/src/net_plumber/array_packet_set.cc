#include "array_packet_set.h"
#include "rpc_handler.h"
extern "C" {
  #include "../headerspace/hs.h"
}

namespace net_plumber {

ArrayPacketSet::ArrayPacketSet(array_t *array, const size_t length) : array(array), length(length) {
    /* empty */
}


ArrayPacketSet::ArrayPacketSet(const size_t length) : array(nullptr), length(length) {
    /* empty */
}

ArrayPacketSet::ArrayPacketSet(const size_t length, enum bit_val preset) : length(length) {
    this->array = array_create(length, preset);
}


ArrayPacketSet::~ArrayPacketSet() {
    array_free(this->array);
}


ArrayPacketSet::ArrayPacketSet(const std::string s) {
    this->array = hs_get_array_from_string(s.c_str());
    this->length = hs_get_length_from_string(s.c_str());
}


std::string
ArrayPacketSet::to_str(void) {
    char *tmp = array_to_str(this->array, this->length, false);
    std::string res = std::string(tmp);
    free(tmp);
    return res;
}

void
ArrayPacketSet::to_json(Json::Value& res) {
    res = this->to_str();
}

size_t
ArrayPacketSet::count(void) {
    return (this->array) ? 1 : 0;
}

size_t
length_from_array_val(const Json::Value& val) {
    return hs_get_length_from_string(val.asCString());
}


ArrayPacketSet::ArrayPacketSet(const Json::Value& val, const size_t length) {
    ArrayPacketSet *a = val_to_array<ArrayPacketSet>(val);
    assert(length == a->length);

    this->array = array_copy(a->array, a->length);
    this->length = length;
    delete a;
}


ArrayPacketSet::ArrayPacketSet(const ArrayPacketSet& aps) { // copy constructor
    this->length = aps.length;
    this->array = (aps.array) ? array_copy(aps.array, aps.length) : nullptr;
}


void
ArrayPacketSet::enlarge(size_t len) {
    if (this->length < len) {
        const size_t olen = this->length;
        this->length = len;
        array_t * tmp = array_resize(this->array, olen, this->length);
        this->array = tmp;
    }
}


void
ArrayPacketSet::intersect(PacketSet *other) {
    assert(this->length == ((ArrayPacketSet *)other)->length);

    array_t *tmp = array_isect_a(this->array, ((ArrayPacketSet *)other)->array, this->length);

    // XXX: inefficient memory handling -> use in-situ intersection instead
    array_free(this->array);
    if (tmp) this->array = tmp;
    else this->array = nullptr;
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
    array_t *tmp = array_not_a(this->array, this->length);
    array_free(this->array);
    this->array = tmp;
}

} /* namespace net_plumber */
