/*
   Copyright 2020 Claas Lorenz

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#include "hs_packet_set.h"
#include "rpc_handler.h"
extern "C" {
  #include "../headerspace/array.h"
}

using namespace log4cxx;

namespace net_plumber {

LoggerPtr HeaderspacePacketSet::logger(Logger::getLogger("NetPlumber"));

HeaderspacePacketSet::HeaderspacePacketSet() {}

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
    if (hs) {
        this->hs.len = hs->len;
        this->hs.list = hs->list;
        free(hs);
    }
}


HeaderspacePacketSet::HeaderspacePacketSet(const Json::Value& val, const size_t length) {
#ifdef GENERIC_PS
    HeaderspacePacketSet *tmp = val_to_hs<HeaderspacePacketSet, ArrayPacketSet>(val, length);
    this->hs = tmp->hs;
    tmp->hs = {0, {0, 0, 0, 0}};
    delete tmp;
#else
    struct hs *tmp = val_to_hs<struct hs, array_t>(val, length);
    this->hs = *tmp;
    tmp->list = {0, 0, 0, 0};
    delete tmp;
#endif
}


/*
    Create hs packet set by intersecting an existing hs with an array. This is
    semantically equivalent to the copy constructor plus an application of
    intersect2(). This constructor is more efficient in time and space since
    only non-empty intersections will be added to the hs in a constructive way
    instead of deleting empty intersections from a previously copied hs.
 */
HeaderspacePacketSet::HeaderspacePacketSet(
    const HeaderspacePacketSet *hps, const ArrayPacketSet *arr
) {
    this->hs = {hps->hs.len, {0, 0, 0, 0}};
    const bool empty = !hs_isect_arr(&this->hs, &hps->hs, arr->array);
    if (empty) {
        hs_destroy(&this->hs);
        this->hs = {hps->hs.len, {0, 0, 0, 0}};
    }
}


HeaderspacePacketSet::HeaderspacePacketSet(const HeaderspacePacketSet& hps) {
    this->hs = {hps.hs.len, {0, 0, 0, 0}};
    hs_copy(&this->hs, &hps.hs);
}


void
HeaderspacePacketSet::enlarge(size_t len) {
    if (this->logger->isDebugEnabled()) {
      std::stringstream enl;
      enl << "HeaderspacePacketSet::enlarge():";
      enl << " enlarge hs from " << std::dec << this->hs.len << " to " << len;
      LOG4CXX_DEBUG(this->logger, enl.str());
    }
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

    if (this->is_empty()) return;

    if (other->is_empty()) {
        hs_destroy(&this->hs);
        this->hs.list = {0, 0, 0, 0};
        return;
    }

    if (!hs_isect_arr_i(&this->hs, other->array)) {
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
