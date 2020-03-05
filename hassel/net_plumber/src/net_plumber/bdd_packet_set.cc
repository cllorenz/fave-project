#ifdef USE_BDD
#include "bdd_packet_set.h"
#include <assert.h>
#include <sstream>
#include <vector>
#include <bdd.h>
#include <functional>

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
_all_zeros() {
    bdd res = bddfalse;
    for (int i = 0; i < bdd_varnum(); i++) {
        res |= bdd_nithvar(i);
    }
    return res;
}


bdd
_all_ones() {
    bdd res = bddfalse;
    for (int i = 0; i < bdd_varnum(); i++) {
        res |= bdd_ithvar(i);
    }
    return res;
}


bdd
_val_to_bdd(enum bit_val val) {
    switch (val) {
        case BIT_Z: return bddfalse;
        case BIT_0: return _all_zeros();
        case BIT_1: return _all_ones();
        case BIT_X: return bddtrue;
        default:    return bddfalse;
    }
}


BDDPacketSet::BDDPacketSet(enum bit_val val) {
    this->ps = _val_to_bdd(val);
}


BDDPacketSet::BDDPacketSet(const size_t length, enum bit_val val) {
    bdd_setvarnum(length * 8);
    this->ps = _val_to_bdd(val);
}


bdd
_bdd_from_vector_str(const std::string s) {
    bdd res = bddfalse;
    bool all_x = true;
    size_t cnt = 0;
    for (char const &c: s) {
        switch (c) {
            case 'z' : return bddfalse;
            case '0' : res |= bdd_nithvar(cnt); all_x = false; break;
            case '1' : res |= bdd_ithvar(cnt); all_x = false; break;
            case 'x' : break;
            case ',' : break;
            default : fprintf(stderr, "error while parsing bdd packet set from string. no viable character: %c", c);
        }
        cnt++;
    }
    return (all_x ? bddtrue : res);
}


bdd
_json_to_bdd(const Json::Value& val) {
    bdd res = bddfalse;
    Json::Value list = val["hs_list"];
    Json::Value diff = val["hs_diff"];

    for (Json::Value::ArrayIndex i = 0; i < list.size(); i++)
        res |= _bdd_from_vector_str(list[i].asString());

    for (Json::Value::ArrayIndex i = 0; i < diff.size(); i++)
        res &= bdd_not(_bdd_from_vector_str(diff[i].asString()));

    return res;
}


BDDPacketSet::BDDPacketSet(const Json::Value& val, size_t length) {
    bdd_setvarnum(length * 8);
    this->ps = _json_to_bdd(val);
}


bdd
_bdd_from_str(const std::string s) {
    std::vector<std::string> tokens;

    size_t last = 0;
    size_t cur = 0;
    for (char const &c: s) {
        switch (c) {
            case 'z' : cur++; break;
            case '0' : cur++; break;
            case '1' : cur++; break;
            case 'x' : cur++; break;
            case ',' : cur++; break;
            case ' ' : cur++; last = cur; break;
            case '+' :
                tokens.push_back(s.substr(last, cur-last));
                tokens.push_back("+");
                cur++; last = cur;
                break;
            case '-' :
                tokens.push_back(s.substr(last, cur-last+1));
                tokens.push_back("-");
                cur++; last = cur;
                break;
            case '(' :
                tokens.push_back("(");
                cur++; last = cur;
                break;
            case ')' :
                tokens.push_back(s.substr(last, cur-last));
                tokens.push_back(")");
                cur++; last = cur;
                break;
            default : cur--; break;
        }
    }

    bdd res = bddfalse;
    bool add = true;
    for (auto const token: tokens) {
        if (token == "+") {
            add = true;
        } else if (token == "-") {
            add = false;
        } else if (token == "(") continue;
        else if (token == ")") continue;
        else if (add) res |= _bdd_from_vector_str(token);
        else res &= bdd_not(_bdd_from_vector_str(token));
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
_string_handler(char *varset, int size, std::vector<std::string>& res) {
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
    std::function<void(char *, int)> bdd_to_string_cb = [&tmp](char *varset, int size){ _string_handler(varset, size, tmp); };

    bdd_allsat(this->ps, (bddallsathandler)&bdd_to_string_cb);

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
    std::function<void(char *, int)> bdd_to_string_cb = [&tmp](char *varset, int size){ _string_handler(varset, size, tmp); };

    bdd_allsat(this->ps, (bddallsathandler)&bdd_to_string_cb);

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
