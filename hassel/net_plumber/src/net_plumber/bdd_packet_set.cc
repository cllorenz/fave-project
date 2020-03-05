#ifdef USE_BDD
#include "bdd_packet_set.h"
#include <assert.h>
#include <sstream>
#include <vector>

namespace net_plumber {

BDDPacketSet::BDDPacketSet(bdd ps) : ps(ps) {
    /* empty */
}


BDDPacketSet::BDDPacketSet(const size_t length) {
    bdd_setvarnum(length * 8);
}


BDDPacketSet::BDDPacketSet() {
    this->ps = bddfalse;
}


bdd
_all_zeros(const size_t len) {
    bdd res = bddfalse;
    for (size_t i = 0; i < len; i++) {
        res |= bdd_nithvar(i);
    }
    return res;
}


bdd
_all_ones(const size_t len) {
    bdd res = bddfalse;
    for (size_t i = 0; i < len; i++) {
        res |= bdd_ithvar(i);
    }
    return res;
}


BDDPacketSet::BDDPacketSet(const size_t length, enum bit_val val) : length(length) {
    switch (val) {
        case BIT_Z: this->ps = bddfalse; break;
        case BIT_0: this->ps = _all_zeros(length); break;
        case BIT_1: this->ps = _all_ones(length); break;
        case BIT_X: this->ps = bddtrue; break;
        default:    this->ps = bddfalse;
    }
}


BDDPacketSet::BDDPacketSet(const Json::Value& val, size_t length) : length(length) {
    // TODO
}


bdd
_bdd_from_str(std::string s) {
    bdd res = bddfalse;
    size_t cnt = 0;
    for (char const &c: s) {
        switch (c) {
            case 'z': return bddfalse;
            case '0' : res |= bdd_nithvar(cnt); break;
            case '1' : res |= bdd_ithvar(cnt); break;
            case 'x' : break;
            case ',' : break;
            default : fprintf(stderr, "error while parsing bdd packet set from string. no viable character: %c", c);
        }
        cnt++;
    }
    return res;
}


BDDPacketSet::BDDPacketSet(const std::string s) {
    this->ps = _bdd_from_str(s);
}


BDDPacketSet::BDDPacketSet(const BDDPacketSet& other) {
    this->ps = other.ps;
}


BDDPacketSet::~BDDPacketSet() {
    /* empty */
}


void
_string_handler(char *varset, int size, std::vector<std::string> res) {
    std::stringstream tmp;
    for (int v=0; v < size; ++v) {
        if (v+1 < size && v % 8 == 7) tmp << ",";
        tmp << (((varset[v]) < 0) ? 'x' : (char)('0' + varset[v]));
    }
    res.push_back(tmp.str());
}


std::string
BDDPacketSet::to_str(void) {
    std::vector<std::string> tmp;
    auto handler = [tmp](char *varset, int size){ _string_handler(varset, size, tmp); };

    //bdd_allsat(this->ps, handler); // XXX

    std::stringstream res;
    for (auto elem = tmp.begin(); elem != tmp.end(); elem++) {
        if ((*elem).empty()) continue;
        res << *elem;
        if (elem != tmp.end() - 1) res << " + ";
    }

    return res.str();
}


void
BDDPacketSet::to_json(Json::Value& res) {
    std::vector<std::string> tmp;
    auto handler = [tmp](char *varset, int size){ _string_handler(varset, size, tmp); };

    //bdd_allsat(this->ps, handler); // XXX

    Json::Value arr(Json::arrayValue);
    for (std::string item: tmp)
        arr.append((Json::StaticString)item.c_str());

    res["len"] = (Json::Value::UInt64)this->length;
    res["list"] = arr;
}


void
BDDPacketSet::enlarge(const size_t length) {
    bdd_extvarnum(length * 8 - bdd_varnum());
}


void
BDDPacketSet::compact(void) {
    /* empty */
}


size_t
BDDPacketSet::count(void) {
    // TODO
    return 0;
}


size_t
BDDPacketSet::count_diff(void) {
    // TODO
    return 0;
}


void
BDDPacketSet::diff(PacketSet *other) {
    this->ps &= bdd_not(((BDDPacketSet *)other)->ps);
}


void
BDDPacketSet::intersect(PacketSet *other) {
    this->ps &= ((BDDPacketSet *)other)->ps;
}

void
BDDPacketSet::psunion(PacketSet *other) {
    this->ps |= ((BDDPacketSet *)other)->ps;
}


void
BDDPacketSet::minus(PacketSet *other) {
    this->ps &= bdd_not(((BDDPacketSet *)other)->ps);
}


#ifdef USE_INV
void
BDDPacketSet::psand(PacketSet *other) {
    // TODO
}
#endif USE_INV


bool
BDDPacketSet::is_empty(void) {
    return this->ps == bddfalse;
}


bool
BDDPacketSet::is_equal(PacketSet *other) {
    return this->ps == ((BDDPacketSet *)other)->ps;
}


bool BDDPacketSet::is_subset_equal(PacketSet *other) {
    return bdd_imp(this->ps, ((BDDPacketSet *)other)->ps) == bddtrue;
}


bool
BDDPacketSet::is_subset(PacketSet *other) {
    return this->is_subset_equal(other) && !this->is_equal(other);
}

void
BDDPacketSet::rewrite(PacketSet *mask, PacketSet *rewrite) {
    /*
        a = 1100
        m = 1010
        r = 1110
        ->  1110

        a & m = 1000
        r & m = 1010

        pos = a & m | r & m = 1010
        neg = a &~m = 0100

        res = pos | neg = 1110
     */

    const bdd pos = (
        this->ps & ((BDDPacketSet *)mask)->ps
    ) | (
        ((BDDPacketSet *)rewrite)->ps & ((BDDPacketSet *)mask)->ps
    );
    const bdd neg = this->ps & bdd_not(((BDDPacketSet *)mask)->ps);

    this->ps = pos | neg;
}


void
BDDPacketSet::negate(void) {
    this->ps = bdd_not(this->ps);
}

} /* namespace net_plumber */

#endif // USE_BDD
