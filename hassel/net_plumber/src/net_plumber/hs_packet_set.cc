#include "hs_packet_set.h"
#include "rpc_handler.h"
extern "C" {
  #include "../headerspace/array.h"
}

namespace net_plumber {

HeaderspacePacketSet::HeaderspacePacketSet(struct hs *hs) {
    this->hs.len = hs->len;
    this->hs.list = hs->list;
}


HeaderspacePacketSet::HeaderspacePacketSet(const size_t length) {
    this->hs = {length, {0, 0, 0, 0}};
}


HeaderspacePacketSet::~HeaderspacePacketSet() {
    hs_destroy(&this->hs);
}


std::string
HeaderspacePacketSet::to_str(void) {
    char *tmp = hs_to_str(&this->hs);
    std::string res = std::string(tmp);
    free(tmp);
    return res;
}


void
HeaderspacePacketSet::to_json(Json::Value& res) {
    hs_to_json(res, &this->hs);
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

HeaderspacePacketSet::HeaderspacePacketSet(const std::string s) {
    struct hs *hs = hs_from_str(s.c_str());
    this->hs.len = hs->len;
    this->hs.list = hs->list;
    free(hs);
}


HeaderspacePacketSet::HeaderspacePacketSet(const Json::Value& val, size_t length) {
    HeaderspacePacketSet *tmp = val_to_hs<HeaderspacePacketSet, ArrayPacketSet>(val, length);
    hs_copy(&this->hs, &tmp->hs);
    delete tmp;
}


HeaderspacePacketSet::HeaderspacePacketSet(const HeaderspacePacketSet& hps) {
    hs_copy(&this->hs, &hps.hs);
}


void
HeaderspacePacketSet::enlarge(size_t len) {
    hs_enlarge(&this->hs, len);
}


void
HeaderspacePacketSet::intersect(PacketSet *other) {
    assert(this->hs.len == ((HeaderspacePacketSet *)other)->hs.len);
    hs_isect(&this->hs, &((HeaderspacePacketSet *)other)->hs);
}


void
HeaderspacePacketSet::intersect2(ArrayPacketSet *other) {
    assert(this->hs.len == other->length);
    if (!other->is_empty() && !this->is_empty()) {
        struct hs tmp = {this->hs.len, {0, 0, 0, 0}};
        const bool empty = !hs_isect_arr(&tmp, &this->hs, other->array);
        if (empty) {
            hs_destroy(&tmp);
            hs_destroy(&this->hs);
            this->hs.list = {0, 0, 0, 0};
        } else {
            hs_destroy(&this->hs);
            this->hs.list = tmp.list;
        }
    } else if (other->is_empty() || this->is_empty()) {
        hs_destroy(&this->hs);
        this->hs.list = {0, 0, 0, 0};
    }
}


void
HeaderspacePacketSet::psunion(PacketSet *other) {
    assert(this->hs.len == ((HeaderspacePacketSet *)other)->hs.len);
    hs_add_hs(&this->hs, &((HeaderspacePacketSet *)other)->hs);
}


void
HeaderspacePacketSet::psunion2(ArrayPacketSet *other) {
    assert(this->hs.len == other->length);
    hs_add(&this->hs, array_copy(other->array, other->length));
}


void
HeaderspacePacketSet::diff(PacketSet *other) {
    this->diff2((ArrayPacketSet *)other);
}


void
HeaderspacePacketSet::diff2(ArrayPacketSet *other) {
    assert(this->hs.len == other->length);
    hs_diff(&this->hs, other->array);
}


void
HeaderspacePacketSet::minus(PacketSet *other) {
    assert(this->hs.len == ((HeaderspacePacketSet *)other)->hs.len);
    hs_minus(&this->hs, &((HeaderspacePacketSet *)other)->hs);
}


void
HeaderspacePacketSet::minus2(ArrayPacketSet *other, const size_t pos) {
    assert(this->hs.len == other->length);
    assert(this->hs.list.used > pos);
    hs_vec_append(&this->hs.list.diff[pos], other->array, true);
}

bool
HeaderspacePacketSet::is_empty(void) {
    return hs_is_empty(&this->hs);
}


bool
HeaderspacePacketSet::is_equal(PacketSet *other) {
    assert(this->hs.len == ((HeaderspacePacketSet *)other)->hs.len);
    return hs_is_equal(&this->hs, &((HeaderspacePacketSet *)other)->hs);
}


bool HeaderspacePacketSet::is_subset_equal(PacketSet *other) {
    assert(this->hs.len == ((HeaderspacePacketSet *)other)->hs.len);
    return hs_is_sub_eq(&this->hs, &((HeaderspacePacketSet *)other)->hs);
}


bool
HeaderspacePacketSet::is_subset(PacketSet *other) {
    assert(this->hs.len == ((HeaderspacePacketSet *)other)->hs.len);
    return hs_is_sub(&this->hs, &((HeaderspacePacketSet *)other)->hs);
}

void
HeaderspacePacketSet::rewrite(PacketSet *mask, PacketSet *rewrite) {
    this->rewrite2((ArrayPacketSet *)mask, (ArrayPacketSet *)rewrite);
}

void
HeaderspacePacketSet::rewrite2(ArrayPacketSet *mask, ArrayPacketSet *rewrite) {
    assert(this->hs.len == mask->length && this->hs.len == rewrite->length);
    hs_rewrite(&this->hs, mask->array, rewrite->array);
}


void
HeaderspacePacketSet::negate(void) {
    hs_cmpl(&this->hs);
}


void
HeaderspacePacketSet::compact(void) {
    hs_compact(&this->hs);
}


void
HeaderspacePacketSet::compact2(ArrayPacketSet *mask) {
    if (!mask) this->compact();
    else {
        assert(this->hs.len == mask->length);
        const bool is_empty = !hs_compact_m(&this->hs, mask->array);
        if (is_empty) {
            hs_destroy(&this->hs);
            this->hs.list = {0, 0, 0, 0};
        }
    }
}


void HeaderspacePacketSet::unroll(void) {
    hs_comp_diff(&this->hs);
}


size_t
HeaderspacePacketSet::count(void) {
    return hs_count(&this->hs);
}

size_t
HeaderspacePacketSet::count_diff(void) {
    return hs_count_diff(&this->hs);
}

} /* namespace net_plumber */
