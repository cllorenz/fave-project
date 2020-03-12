#ifdef USE_BDD
#include "bdd_packet_set.h"
#include <assert.h>
#include <sstream>
#include <vector>
#include <bdd.h>
#include <functional>

namespace net_plumber {

static std::vector<std::string> *result_buffer;
static size_t vector_counter = 0;

void
BDDPacketSet::init_result_buffer(void) {
    result_buffer = new std::vector<std::string>();
}

void
BDDPacketSet::destroy_result_buffer(void) {
    delete result_buffer;
}


void
BDDPacketSet::reset_result_buffer(void) {
    result_buffer->clear();
}


std::vector<std::string> *
BDDPacketSet::get_result_buffer(void) {
    return result_buffer;
}


void
BDDPacketSet::append_result_buffer(std::string item) {
    result_buffer->push_back(item);
}


void
BDDPacketSet::reset_vector_counter(void) {
    vector_counter = 0;
}


void
BDDPacketSet::increment_vector_counter(void) {
    vector_counter++;
}


size_t
BDDPacketSet::get_vector_counter(void) {
    return vector_counter;
}


void
_initialize_bdd_varnum(const size_t length) {
    const int size = bdd_varnum();
    if (length * 8 > 0x1FFFFF || (size >= 0 && static_cast<size_t>(size) >= length * 8)) return;
    bdd_extvarnum((length * 8) - size);
}

BDDPacketSet::BDDPacketSet(bdd ps) : ps(ps) {
    /* empty */
}


BDDPacketSet::BDDPacketSet(const size_t length) {
    _initialize_bdd_varnum(length);
}


BDDPacketSet::BDDPacketSet() {
    this->ps = bddfalse;
}


bdd
_all_zeros() {
    bdd res = bddtrue;
    for (int i = 0; i < bdd_varnum(); i++) {
        res &= bdd_nithvar(i);
    }
    return res;
}


bdd
_all_ones() {
    bdd res = bddtrue;
    for (int i = 0; i < bdd_varnum(); i++) {
        res &= bdd_ithvar(i);
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
    _initialize_bdd_varnum(length);
    this->ps = _val_to_bdd(val);
}


bdd
_bdd_from_vector_str(const std::string s) {
    bdd res = bddtrue;
    bool all_x = true;
    size_t cnt = 0;
    for (char const &c: s) {
        switch (c) {
            case 'z' : return bddfalse;
            case '0' : res &= bdd_nithvar(cnt); all_x = false; break;
            case '1' : res &= bdd_ithvar(cnt); all_x = false; break;
            case 'x' : break;
            case ',' : cnt--; break;
            default : fprintf(stderr, "error while parsing bdd packet set from string. no viable character: %c", c);
        }
        cnt++;
    }

    return (all_x ? bddtrue : res);
}


bdd
_json_to_bdd(const Json::Value& val) {
    bdd res = bddfalse;

    if (val.isString()) {
        res |= _bdd_from_vector_str(val.asString());
    }
    else if (val.isObject()) {

        Json::Value list = val["hs_list"];

        for (Json::Value::ArrayIndex i = 0; i < list.size(); i++)
            res |= _bdd_from_vector_str(list[i].asString());

        Json::Value diff = val["hs_diff"];
        for (Json::Value::ArrayIndex i = 0; i < diff.size(); i++)
            res &= bdd_not(_bdd_from_vector_str(diff[i].asString()));
    }

    return res;
}


BDDPacketSet::BDDPacketSet(const Json::Value& val, size_t length) {
    _initialize_bdd_varnum(length);
    this->ps = _json_to_bdd(val);
}


size_t
_get_length_from_string(const std::string s, size_t *commas) {
    if (s == "(nil)") return 0;

    const char *c = s.c_str();
    if (*c == '(') c++;
    size_t l = 0;
    *commas = 0;
    while (! (
        *(c+l) == '\0' ||
        *(c+l) == ' ' ||
        *(c+l) == '-' ||
        *(c+l) == '+' ||
        *(c+l) == '(' ||
        *(c+l) == ')'
    )) {
        if (*(c+l) == ',') (*commas)++;
        l++;
    }
    const size_t res = l - (*commas);
    return res;
}


bdd
_bdd_from_str(const std::string s) {
    if (s == "(nil)") return bddfalse;

    const char *c = s.c_str();
    if (*c == '(') c++; // skip optional leading bracket
    while (*c == ' ') c++; // seek begin of array
    size_t commas = 0;
    size_t len = _get_length_from_string(c, &commas);
    const int size = bdd_varnum();
    if (size >= 0 && static_cast<size_t>(size) < len) bdd_extvarnum(len - size);
    len += commas;

    // create result hs
    bdd res = bddfalse;

    // parse hs string
    while (*c) {
        if (*c == '(') c++; // skip optional bracket
        while (*c == ' ') c++; // skip optional spaces

        res |= _bdd_from_vector_str(s.substr(c - s.c_str(), len));

        c += len; // skip array
        while (*c == ' ') c++; // skip optional space

        if (*c == '-') { // optional parse diff vector
            c++; // skip minus
            while (*c == ' ') c++; // skip optional space
            assert (*c == '('); // make sure diff vector is being parsed
            c++; // skip opening bracket
            while (*c == ' ') c++; // skip optional space
            while (*c != ')') { // parse diff vector

                res &= bdd_not(_bdd_from_vector_str(s.substr(c - s.c_str(), len)));

                c += len; // skip array

                while (*c == ' ') c++; // skip optional spaces
                if (*c == '+') c++; // skip plus
                while (*c == ' ') c++; //skip optional spaces
                if (*c == ')') c++; // skip optional bracket
                while (*c == ' ') c++; // skip optional spaces
            }
            c++; // skip closing bracket
        }
        if (*c == ')') c++; // skip optional closing bracket
        if (*c == ' ') c++; // skip optional space
        if (*c == '+') c++; // skip optional concatenation
        while (*c == ' ') c++; // skip optional spaces
    }

    return res;
}


/* XXX: deprecated?
size_t
_get_length_from_str(const std::string s) {
    size_t length = 0;

    for (char const &c: s) {
        switch (c) {
            case 'z' : length++; break;
            case '0' : length++; break;
            case '1' : length++; break;
            case 'x' : length++; break;
            case '(' : break;
            case ' ' : break;
            default  : return (length + 7) / 8;
        }
    }

    return (length + 7) / 8;
}
*/


BDDPacketSet::BDDPacketSet(const std::string s) {
//    const size_t length = _get_length_from_str(s); // XXX: deprecated?
//    _initialize_bdd_varnum(length);
    this->ps = _bdd_from_str(s);
}


BDDPacketSet::BDDPacketSet(const BDDPacketSet& other) {
    this->ps = other.ps;
}


BDDPacketSet::~BDDPacketSet() {
    /* empty */
}


void
//_string_handler(char *varset, int size, std::vector<std::string>& res) {
_string_handler(char *varset, int size) {
    std::stringstream tmp;
    for (int v=0; v < size; ++v) {
        tmp << (((varset[v]) < 0) ? 'x' : (char)('0' + varset[v]));
        if (v+1 < size && v % 8 == 7) tmp << ",";
    }
    BDDPacketSet::append_result_buffer(tmp.str());
}


std::string
_all_x_str(void) {
    std::stringstream s;
    const int size = bdd_varnum();
    for (int i = 0; i < size; i++) {
        s << 'x';
        if (i + 1 < size && i % 8 == 7) s << ',';
    }
    return s.str();
}


std::string
_bdd_to_str(bdd ps) {
    if (ps == bddtrue) return _all_x_str();
    if (ps == bddfalse) return "(nil)";

    BDDPacketSet::reset_result_buffer();
    bdd_allsat(ps, *_string_handler);

    auto* tmp = BDDPacketSet::get_result_buffer();
    std::stringstream res;
    for (auto elem = tmp->begin(); elem != tmp->end(); elem++) {
        if ((*elem).empty()) continue;
        res << *elem;
        if (elem != tmp->end() - 1) res << " + ";
    }

    return res.str().size() ? res.str() : "(nil)";
}


std::string
BDDPacketSet::to_str(void) {
    return _bdd_to_str(this->ps);
}


void
BDDPacketSet::to_json(Json::Value& res) {


    BDDPacketSet::reset_result_buffer();
    bdd_allsat(this->ps, *_string_handler);

    auto *tmp = BDDPacketSet::get_result_buffer();
    Json::Value arr(Json::arrayValue);
    for (std::string item: *tmp)
        arr.append((Json::StaticString)item.c_str());

    res["len"] = (Json::Value::UInt64)(bdd_varnum() / 8);
    res["list"] = arr;
}


void
BDDPacketSet::enlarge(const size_t length) {
    const int size = bdd_varnum();
    if (size >= 0 && length * 8 > static_cast<size_t>(size)) bdd_extvarnum(length * 8 - size);
}


void
BDDPacketSet::compact(void) {
    /* empty */
}


void
_count_handler(char *, int) {
    BDDPacketSet::increment_vector_counter();
}


size_t
BDDPacketSet::count(void) {
    BDDPacketSet::reset_vector_counter();
    bdd_allsat(this->ps, *_count_handler);
    return BDDPacketSet::get_vector_counter();
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
#endif //USE_INV


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
