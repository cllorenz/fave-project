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

#include "packet_set_unit.h"
#include "../array_packet_set.h"
#include "../hs_packet_set.h"
#include <iostream>
#ifdef USE_BDD
#include "../bdd_packet_set.h"
#endif

using namespace net_plumber;

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::setUp() {
#ifdef USE_BDD
    if (bdd_isrunning()) bdd_done();
    bdd_init(100000, 1000);
    bdd_setvarnum(8);
#endif
    this->ps = new PS1("xxxxxxxx");
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::tearDown() {
    delete this->ps;
#ifdef USE_BDD
    if (bdd_isrunning()) bdd_done();
#endif
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_from_str() {
    printf("\n");

    PS1 a{ "xxxxxxxx" };

    CPPUNIT_ASSERT(this->ps->is_equal(&a));

#ifdef USE_BDD
    PS1 b{ "(xxxxxxxx - (1xxxxxxx + 01xxxxxx))" };

    PS1 tmp1 {"1xxxxxxx"};
    this->ps->minus(&tmp1);

    PS1 tmp2 {"01xxxxxx"};
    this->ps->minus(&tmp2);

    CPPUNIT_ASSERT(this->ps->is_equal(&b));
#endif
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_to_str() {
    printf("\n");

    std::string s{ "xxxxxxxx" };
    std::string res = this->ps->to_str();

    CPPUNIT_ASSERT(res == s);
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_from_json() {
    printf("\n");

    Json::Value val;
    val = (Json::StaticString)"xxxxxxxx";

    PS1 a{ val, 1 };

    CPPUNIT_ASSERT(this->ps->is_equal(&a));
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_to_json() {
    printf("\n TODO: implement");
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_compact() {
    printf("\n");

    PS1 a { "1xxxxxxx" };
    PS1 tmp {"0xxxxxxx"};
    a.psunion(&tmp);

    a.compact();

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}

#ifndef USE_BDD
template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_unroll() {
    printf("\n");

    PS1 a { "xxxxxxxx" };
    PS2 diff {"1xxxxxxx"};
    a.diff(&diff);

    a.unroll();

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}
#endif

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_count() {
    printf("\n");

    CPPUNIT_ASSERT(this->ps->count() == 1);

    PS1 *a = new PS1(1);

    CPPUNIT_ASSERT(a->count() == 0);

    delete a;
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_enlarge() {
    printf("\n");
    PS1 a{"xxxxxxxx,xxxxxxxx"};

    this->ps->enlarge(2);

    CPPUNIT_ASSERT(this->ps->is_equal(&a));

    PS1 b{"xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx"};

    this->ps->enlarge(6);

    CPPUNIT_ASSERT(this->ps->is_equal(&b));
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_diff() {
    printf("\n");

    PS1 a{"xxxxxxxx"};
    PS2 diff1 {"1xxxxxxx"};
    a.diff(&diff1);
    PS2 diff2 {"0xxxxxxx"};
    a.diff(&diff2);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_intersect() {
    printf("\n");

    PS1 a{"1xxxxxxx"};

    this->ps->intersect(&a);

    CPPUNIT_ASSERT(this->ps->is_equal(&a));
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_psunion() {
    printf("\n");

    PS1 a{"xxxxxxxx"};

    PS1 tmp1 {"1xxxxxxx"};
    a.psunion(&tmp1);
    PS1 tmp2 {"0xxxxxxx"};
    a.psunion(&tmp2);

    CPPUNIT_ASSERT(this->ps->is_equal(&a));
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_minus() {
    printf("\n");

    PS1 a{"xxxxxxxx"};

    PS1 tmp {"1xxxxxxx"};
    a.minus(&tmp);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}

#ifdef USE_INV
template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_psand() {
    printf("\n");

    PS2 a{"xxxxxxxx"};
    PS2 b{"1xxxxxxx"};

    a.psand(&b);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}
#endif

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_is_empty() {
    printf("\n");

    PS1 a{ "(nil)" };

    CPPUNIT_ASSERT(a.is_empty());

#ifdef USE_BDD
    PS1 b{ "xxxxxxxx" };
    this->ps->minus(&b);

    CPPUNIT_ASSERT(this->ps->is_empty());
#endif
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_is_equal() {
    printf("\n");

    PS1 a{"xxxxxxxx"};

    CPPUNIT_ASSERT(this->ps->is_equal(&a));

    PS1 tmp1 {"1xxxxxxx"};
    a.psunion(&tmp1);

    CPPUNIT_ASSERT(this->ps->is_equal(&a));

    PS1 tmp2 {"0xxxxxxx"};
    a.psunion(&tmp2);

    CPPUNIT_ASSERT(this->ps->is_equal(&a)); 
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_is_subset() {
    printf("\n");

    PS1 a{"1xxxxxxx"};

    CPPUNIT_ASSERT(a.is_subset(this->ps));

    PS1 tmp1 {"01xxxxxx"};
    a.psunion(&tmp1);

    CPPUNIT_ASSERT(a.is_subset(this->ps));

#ifdef USE_BDD
    PS1 tmp2 {"00xxxxxx"};
    a.psunion(&tmp2);

    CPPUNIT_ASSERT(!a.is_subset(this->ps));

    PS2 tmp3 {"xxxxxxx1"};
    a.diff(&tmp3);

    CPPUNIT_ASSERT(a.is_subset(this->ps));
#endif
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_is_subset_equal() {
    printf("\n");

    PS1 a{"1xxxxxxx"};

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));

    PS1 tmp1 {"01xxxxxx"};
    a.psunion(&tmp1);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));

    PS1 tmp2 {"00xxxxxx"};
    a.psunion(&tmp2);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));

    PS1 tmp3 {"0xxxxxxx"};
    a.psunion(&tmp3);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_rewrite() {
    printf("\n");

    PS1 a{"1xxxxxxx"};

    PS2 m1 {"10000000"};
    PS2 rw1 {"x0000000"};

    a.rewrite(&m1 , &rw1);

    CPPUNIT_ASSERT(a.is_equal(this->ps));

    PS1 b {"000111xx,x01x01x0"};

    PS2 m2 {"11111111,10000000"};
    PS2 rw2 {"01x01x01,x1x0x01x"};

    b.rewrite(&m2, &rw2);

    PS1 r2 {"01x01x01,x01x01x0"};

    CPPUNIT_ASSERT(b.is_equal(&r2));
}

template<class PS1, class PS2>
void PacketSetTest<PS1, PS2>::test_negate() {
    printf("\n");

    PS1 a{"xxxxxxxx"};

    a.negate();

    CPPUNIT_ASSERT(a.is_subset(this->ps));
}


template class PacketSetTest<HeaderspacePacketSet, ArrayPacketSet>;
template class PacketSetTest<ArrayPacketSet, ArrayPacketSet>;
#ifdef USE_BDD
template class PacketSetTest<BDDPacketSet, BDDPacketSet>;
#endif
