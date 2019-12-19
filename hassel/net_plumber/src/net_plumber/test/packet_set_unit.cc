/*
   Copyright 2012 Google Inc.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Author: peyman.kazemian@gmail.com (Peyman Kazemian)
*/

#include "packet_set_unit.h"
#include "../array_packet_set.h"
#include "../hs_packet_set.h"
#include <iostream>

using namespace net_plumber;

template<class PS>
void PacketSetTest<PS>::setUp() {
    this->ps = new PS("xxxxxxxx");
}

template<class PS>
void PacketSetTest<PS>::tearDown() {
    delete this->ps;
}

template<class PS>
void PacketSetTest<PS>::test_from_str() {
    printf("\n");

    PS a{ "xxxxxxxx" };

    CPPUNIT_ASSERT(this->ps->is_equal(&a));


    PS b{ "(xxxxxxxx - (1xxxxxxx + 01xxxxxx))" };

    PS tmp1 = PS("1xxxxxxx");
    this->ps->minus(&tmp1);
    PS tmp2 = PS("01xxxxxx");
    this->ps->minus(&tmp2);

    CPPUNIT_ASSERT(this->ps->is_equal(&b));
}

template<class PS>
void PacketSetTest<PS>::test_to_str() {
    printf("\n");

    std::string s{ "xxxxxxxx" };
    std::string res = this->ps->to_str();

    CPPUNIT_ASSERT(res == s);
}

template<class PS>
void PacketSetTest<PS>::test_from_json() {
    printf("\n");

    Json::Value val;
    val = (Json::StaticString)"xxxxxxxx";

    PS a{ val, 1 };

    CPPUNIT_ASSERT(this->ps->is_equal(&a));
}

template<class PS>
void PacketSetTest<PS>::test_to_json() {
    printf("\n TODO: implement");
}

template<class PS>
void PacketSetTest<PS>::test_compact() {
    printf("\n");

    PS a { "1xxxxxxx" };
    PS tmp = PS("0xxxxxxx");
    a.psunion(&tmp);

    a.compact();

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}

template<class PS>
void PacketSetTest<PS>::test_unroll() {
    printf("\n");

    PS a { "xxxxxxxx" };
    auto diff = ArrayPacketSet("1xxxxxxx");
    a.diff(&diff); // XXX: implement invariant PS test

    a.unroll();

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}

template<class PS>
void PacketSetTest<PS>::test_count() {
    printf("\n");

    CPPUNIT_ASSERT(this->ps->count() == 1);

    PS *a = new PS(1);

    CPPUNIT_ASSERT(a->count() == 0);

    delete a;
}

template<class PS>
void PacketSetTest<PS>::test_enlarge() {
    printf("\n");
    PS a{"xxxxxxxx,xxxxxxxx"};

    this->ps->enlarge(2);

    CPPUNIT_ASSERT(this->ps->is_equal(&a));

    PS b{"xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx"};

    this->ps->enlarge(6);

    CPPUNIT_ASSERT(this->ps->is_equal(&b));
}

template<class PS>
void PacketSetTest<PS>::test_diff() {
    printf("\n");

    PS a{"xxxxxxxx"};
    auto diff1 = ArrayPacketSet("1xxxxxxx");
    a.diff(&diff1); // XXX: implement invariant PS test
    auto diff2 = ArrayPacketSet("0xxxxxxx");
    a.diff(&diff2); // XXX: implement invariant PS test

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}

template<class PS>
void PacketSetTest<PS>::test_intersect() {
    printf("\n");

    PS a{"1xxxxxxx"};

    this->ps->intersect(&a);

    CPPUNIT_ASSERT(this->ps->is_equal(&a));
}

template<class PS>
void PacketSetTest<PS>::test_psunion() {
    printf("\n");

    PS a{"xxxxxxxx"};

    PS tmp1 = PS("1xxxxxxx");
    a.psunion(&tmp1);
    PS tmp2 = PS("0xxxxxxx");
    a.psunion(&tmp2);

    CPPUNIT_ASSERT(this->ps->is_equal(&a));
}

template<class PS>
void PacketSetTest<PS>::test_minus() {
    printf("\n");

    PS a{"xxxxxxxx"};

    PS tmp = PS("1xxxxxxx");
    a.minus(&tmp);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}

template<class PS>
void PacketSetTest<PS>::test_psand() {
    printf("\n");

    PS a{"xxxxxxxx"};
    PS b{"1xxxxxxx"};

    a.psand(&b);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}

template<class PS>
void PacketSetTest<PS>::test_is_empty() {
    printf("\n");

}

template<class PS>
void PacketSetTest<PS>::test_is_equal() {
    printf("\n");

    PS a{"xxxxxxxx"};

    CPPUNIT_ASSERT(this->ps->is_equal(&a));

    PS tmp1 = PS("1xxxxxxx");
    a.psunion(&tmp1);

    CPPUNIT_ASSERT(this->ps->is_equal(&a));

    PS tmp2 = PS("0xxxxxxx");
    a.psunion(&tmp2);

    CPPUNIT_ASSERT(this->ps->is_equal(&a)); 
}

template<class PS>
void PacketSetTest<PS>::test_is_subset() {
    printf("\n");

    PS a{"1xxxxxxx"};

    CPPUNIT_ASSERT(a.is_subset(this->ps));

    PS tmp1 = PS("01xxxxxx");
    a.psunion(&tmp1);

    CPPUNIT_ASSERT(a.is_subset(this->ps));

    PS tmp2 = PS("00xxxxxx");
    a.psunion(&tmp2);

    CPPUNIT_ASSERT(a.is_subset(this->ps));

    auto tmp3 = ArrayPacketSet("xxxxxxx1");
    a.diff(&tmp3); // XXX: implement invariant PS test

    CPPUNIT_ASSERT(a.is_subset(this->ps));
}

template<class PS>
void PacketSetTest<PS>::test_is_subset_equal() {
    printf("\n");

    PS a{"1xxxxxxx"};

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));

    PS tmp1 = PS("01xxxxxx");
    a.psunion(&tmp1);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));

    PS tmp2 = PS("00xxxxxx");
    a.psunion(&tmp2);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));

    PS tmp3 = PS("0xxxxxxx");
    a.psunion(&tmp3);

    CPPUNIT_ASSERT(a.is_subset_equal(this->ps));
}

template<class PS>
void PacketSetTest<PS>::test_rewrite() {
    printf("\n");

    PS a{"1xxxxxxx"};

    // XXX: implement invariant PS test
    auto mask = ArrayPacketSet("10000000");
    auto rw = ArrayPacketSet("x0000000");
    a.rewrite(&mask , &rw);

    CPPUNIT_ASSERT(a.is_equal(this->ps));
}

template<class PS>
void PacketSetTest<PS>::test_negate() {
    printf("\n");

    PS a{"xxxxxxxx"};

    a.negate();

    CPPUNIT_ASSERT(a.is_subset(this->ps));
}


template class PacketSetTest<HeaderspacePacketSet>;
template class PacketSetTest<ArrayPacketSet>;

