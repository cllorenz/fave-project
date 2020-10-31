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

#include <bdd.h>
#include <iostream>
#include <assert.h>
#include <vector>
#include <sstream>
#include <functional>

using namespace std;

static std::vector<std::string> *result_buffer;

void print_handler(char *varset, int size) {
    for (int v = 0; v < size; v++) cout << (varset[v] < 0 ? 'x' : (char)('0' + varset[v]));
    cout << " ";
}

void print_handler_nl(char *varset, int size) {
    print_handler(varset, size);
    cout << endl;
}

void allsatPrintHandler(char* varset, int size)
{
    stringstream s;
    for (int v=0; v<size; ++v)
    {
        s << (varset[v] < 0 ? 'x' : (char)('0' + varset[v]));
    }
    result_buffer->push_back(s.str());
}

void result_handler(char *varset, int size, std::vector<std::string> result) {
    stringstream s;
    for (int v=0; v<size; ++v)
    {
        char c = (varset[v] < 0 ? 'x' : (char)('0' + varset[v]));
        s << c;
    }
    result.push_back(s.str());
}

int main(void) {
    bdd x, y, z;

    bdd_init(1000, 100);
    bdd_setvarnum(5);
    result_buffer = new std::vector<std::string>();

    x = bdd_ithvar(0);
    y = bdd_ithvar(1);
    z = x & y;

    bdd_extvarnum(5);

    bdd a, b, c;

    a = bdd_ithvar(0);
    b = bdd_ithvar(1);
    c = a & b;

    assert (a == x);
    assert (b == y);
    assert (c == z);

    bdd_allsat(z, *allsatPrintHandler);
    for (auto r: *result_buffer) cout << r << endl;

    bdd_printset(z); cout << endl;

    result_buffer->clear();

    bdd all_x = bddtrue;
    bdd_allsat(all_x, *allsatPrintHandler);
    for (auto r: *result_buffer) cout << r << endl;

    bdd_printset(all_x); cout << endl;

    result_buffer->clear();

    bdd empty_set = bddfalse;
    bdd_allsat(empty_set, *allsatPrintHandler);
    for (auto r: *result_buffer) cout << r << endl;

    bdd_printset(empty_set); cout << endl;

//    std::vector<std::string> tmp;
//    std::function<void(char *, int)> lambda_handler = [&tmp](char *varset, int size){ result_handler(varset, size, tmp); };
//    bdd_allsat(all_x, (bddallsathandler)&lambda_handler);
//    for (auto r: tmp) cout << r << endl;

    bdd_done();

    bdd_init(1000, 100);
    bdd_setvarnum(3);

    // mask -> set of pairs 1 -> rw, 0,x -> x (can be precomputed)
    // mask = 10x
    // rw = 1x0
    // -> 1xx

    // inv_mask -> set of pairs 0,x -> a (inv_mask can be precomputed)
    // inv_mask = x11
    // a = 01x
    // -> x1x
    // 1xx & x1x = 11x

    int set[3] = {0,2};
    bdd v = bdd_makeset(set, 2);
    cout << "makeset({0,2}) = ";
    bdd_allsat(v, *print_handler);

    bdd all_true = bddtrue;
    bdd g = (bdd_ithvar(0) & bdd_ithvar(1) & bdd_nithvar(2));

    cout << "compose(xxx,110,{0,2}) = ";
    bdd_allsat(bdd_compose(all_true, g, 1), *print_handler);

    bddPair * p = bdd_newpair();
//    bdd_setpair(p, 1, 0);
    bdd_setpair(p, 2, 1);

    cout << "veccompose(10x, {2,1}) = ";
    bdd_allsat(bdd_replace(bdd_ithvar(0) & bdd_nithvar(1), p), *print_handler);

    bdd_done();

    cout << endl;

    bdd_init(1000, 100);
    bdd_setvarnum(1);


    const bdd dc = bddtrue;
    const bdd zero = bdd_nithvar(0);
    const bdd one  = bdd_ithvar(0);

    cout << "restrict(0, 0) = ";
    bdd_allsat(bdd_restrict(zero, zero), *print_handler);

    cout << "restrict(0, 1) = ";
    bdd_allsat(bdd_restrict(zero, one), *print_handler);

    cout << "restrict(0, x) = ";
    bdd_allsat(bdd_restrict(zero, dc), *print_handler);

    cout << "restrict(1, 0) = ";
    bdd_allsat(bdd_restrict(one, zero), *print_handler);

    cout << "restrict(1, 1) = ";
    bdd_allsat(bdd_restrict(one, one), *print_handler);

    cout << "restrict(1, x) = ";
    bdd_allsat(bdd_restrict(one, dc), *print_handler);

    cout << "~(0 & 1) = ";
    bdd_allsat(bdd_not(zero & one), *print_handler_nl);

    cout << "~0 = ";
    bdd_allsat(bdd_not(zero), *print_handler_nl);

    cout << "~1 = ";
    bdd_allsat(bdd_not(one), *print_handler_nl);

    cout << "~x = ";
    bdd_allsat(bdd_not(dc), *print_handler_nl);

    bdd_done();

/*
    bdd_init(1000, 100);
    bdd_setvarnum(4);

    bdd a1 = bddtrue;
    // a1 = 1011
    a1 &= bdd_ithvar(0);
    a1 &= bdd_nithvar(1);
    a1 &= bdd_ithvar(2);
    a1 &= bdd_ithvar(3);

    bdd a2 = bddtrue;
    // a2 = 01xx
    a2 &= bdd_nithvar(0);
    a2 &= bdd_ithvar(1);

    bdd a3 = bddtrue;
    // a 3 = 1100
    a3 &= bdd_ithvar(0);
    a3 &= bdd_ithvar(1);
    a3 &= bdd_nithvar(2);
    a3 &= bdd_nithvar(3);

    bdd all_a = a1 | a2 | a3;

    cout << "all_a = ( a1 = ";
    bdd_allsat(a1, *print_handler);
    cout << " | a2 = ";
    bdd_allsat(a2, *print_handler);
    cout << " | a3 = ";
    bdd_allsat(a3, *print_handler);
    cout << " ) = ";
    result_buffer->clear();
    bdd_allsat(all_a, *allsatPrintHandler);
    for (auto r: *result_buffer) {
        cout << r;
        cout << " ";
    }
    cout << endl;

    cout << " -> sat count: " << bdd_satcount(all_a) << endl;
    cout << " -> logarithmic sat count: " << bdd_satcountln(all_a) << endl;

    cout << "restrict(x, 0) = ";
    bdd_allsat(bdd_restrict(dc, zero), *print_handler);

    cout << "restrict(x, 1) = ";
    bdd_allsat(bdd_restrict(dc, one), *print_handler);

    cout << "restrict(x, x) = ";
    bdd_allsat(bdd_restrict(dc, dc), *print_handler);

    bdd_done();

    bdd_init(1000, 100);
    bdd_setvarnum(4);

    const bdd ary = bdd_ithvar(0); // 1xxx

    cout << endl << "ary = ";
    bdd_allsat(ary, *print_handler_nl);

    bdd mask = bddtrue;
    mask &= bdd_ithvar(0);
    mask &= bdd_nithvar(1); // 10xx

    cout << "mask = ";
    bdd_allsat(mask, *print_handler_nl);

    bdd neg_bits = bddtrue;
    for (size_t i = 0; i < 4; i++) neg_bits &= bdd_nithvar(i); // 0000

    cout << "neg_bits = ";
    bdd_allsat(neg_bits, *print_handler_nl);

    bdd pos_bits = bddtrue;
    for (size_t i = 0; i < 4; i++) pos_bits &= bdd_ithvar(i); // 1111

    cout << "pos_bits = ";
    bdd_allsat(pos_bits, *print_handler_nl);

    const bdd zm = bdd_imp(neg_bits, mask); // 1xxx

    cout << "zm = ";
    bdd_allsat(neg_bits, *print_handler);
    cout << "=> ";
    bdd_allsat(mask, *print_handler);
    cout << "= ";
    bdd_allsat(zm, *print_handler);
    cout << endl;

    bdd rw = bdd_nithvar(0); // 0xxx

    bdd masked_rw = bdd_imp(pos_bits, rw); // 0xxx
    cout << "masked_rw = ";
    bdd_allsat(pos_bits, *print_handler);
    cout << "=> ";
    bdd_allsat(rw, *print_handler);
    cout << "= ";
    bdd_allsat(masked_rw, *print_handler);
    cout << endl;

    bdd unmasked_prev = bdd_imp(zm, ary); // xxxx
    cout << "unmasked_prev = ";
    bdd_allsat(zm, *print_handler);
    cout << "=> ";
    bdd_allsat(ary, *print_handler);
    cout << "= ";
    bdd_allsat(unmasked_prev, *print_handler);
    cout << endl;

    bdd res = masked_rw & unmasked_prev; // 0xxx
    cout << "res = ";
    bdd_allsat(masked_rw, *print_handler);
    cout << "& ";
    bdd_allsat(unmasked_prev, *print_handler);
    cout << "= ";
    bdd_allsat(res, *print_handler);
    cout << endl;

    bdd_done();
*/

    return 0;
}

/*
Mask semantics:
0 or x unmask bit
1 masks bit

1 implies rw
0 implies previous
x implies previous

(1 => rw) & (0/x => prev) = masked_rw & unmasked_prev

masked_rw: set masked bits, x unmasked bits
unmasked_prev: set unmasked bits, x masked bits

unmasked_normalization: 0 => mask

const bdd nm = (all_zero => mask)

f_a_mask(a, m) = a if m == 0 or m == x else x


f_rw_mask(rw, m) = rw if m == 1 else x

m  rw x  f(m, rw, x)
// selects third operand (alternative: map 0 to x before)
0  0  x  x
0  1  x  x
0  x  x  x
// selects second operand
1  0  x  0
1  1  x  1
1  x  x  x
// selects third operand
x  0  x  x
x  1  x  x
x  x  x  x


m  rw x frw(m,rw,x)  ite  m&rw  ~m&x   ^
0  0  x      x        x    0      1    x
0  1  x      x        1    -      1    1
0  x  x      x        x    0      1    x

1  0  x      0        0    -      0    0
1  1  x      1        x    1      0    x
1  x  x      x        x    1      0    x

x  0  x      x        0    0      x    1
x  1  x      x        1    1      x    0
x  x  x      x        x    x      x    -


frw(m,rw,x) = (m == 1) ? rw : x

m  rw x frw(m,rw,x)
0  0  x      x
0  1  x      x
0  x  x      x

1  0  x      0
1  1  x      1
1  x  x      x

x  0  x      x
x  1  x      x
x  x  x      x




m  a  x fa(m,a,x)  ite
0  0  x     0       x <-
0  1  x     1       1
0  x  x     x       x

1  0  x     x       0 <-
1  1  x     x       x
1  x  x     x       x

x  0  x     0       0
x  1  x     1       1
x  x  x     x       x

fa(m,a,x) = (m != 1) ? a : x


m  a  rw  f
-----------
0  0  0   0
0  0  1   0
0  0  x   0
0  1  0   1
0  1  1   1
0  1  x   1
0  x  0   x
0  x  1   x
0  x  x   x

m  a  rw  f(m, a, rw)
-----------
1  0  0   0
1  0  1   1
1  0  x   x
1  1  0   0
1  1  1   1
1  1  x   x
1  x  0   0
1  x  1   1
1  x  x   x

m  a  rw  f(m, a, rw)
x  0  0   0
x  0  1   0
x  0  x   0
x  1  0   1
x  1  1   1
x  1  x   1
x  x  0   x
x  x  1   x
x  x  x   x



~a
~(0 & 1) = x
~0 = 1
~1 = 0
~x = F


a => b
// F implies x
(0 & 1) => 0 = x
(0 & 1) => 1 = x
(0 & 1) => x = x
// 0 implies 1 if b=1 else x
0 => 0 = x
0 => 1 = 1
0 => x = x
// 1 implies 0 if b=0 else x
1 => 0 = 0
1 => 1 = x
1 => x = x
// x implies self
x => 0 = 0
x => 1 = 1
x => x = x


a | b
(0 & 1) | 0 = 0
(0 & 1) | 1 = 1
(0 & 1) | x = X
0 | 0 = 0
0 | 1 = x
0 | x = x
1 | 0 = x
1 | 1 = 1
1 | x = x
x | 0 = x
x | 1 = x
x | x = x


a & b
(0 & 1) & 0 = F
(0 & 1) & 1 = F
(0 & 1) & x = F
0 & 0 = 0
0 & 1 = F
0 & x = 0
1 & 0 = F
1 & 1 = 1
1 & x = 1
x & 0 = 0
x & 1 = 1
x & x = x

a ^ b
z ^ 0 = 0
z ^ 1 = 1
z ^ x = x
0 ^ 0 = -
0 ^ 1 = x
0 ^ x = 1
1 ^ 0 = x
1 ^ 1 = -
1 ^ x = 0
x ^ 0 = 1
x ^ 1 = 0
x ^ x = -

a ^ b
(0 & 1) ^ 0 = 0
(0 & 1) ^ 1 = 1
(0 & 1) ^ x = x
0 ^ 0 = F
0 ^ 1 = x
0 ^ x = 1
1 ^ 0 = x
1 ^ 1 = F
1 ^ x = 0
x ^ 0 = 1
x ^ 1 = 0
x ^ x = F

a <=> b
(0 & 1) <=> 0 = 1
(0 & 1) <=> 1 = 0
(0 & 1) <=> x = F
0 <=> 0 = x
0 <=> 1 = F
0 <=> x = 0
1 <=> 0 = F
1 <=> 1 = x
1 <=> x = 1
x <=> 0 = 0
x <=> 1 = 1
x <=> x = x


ite(a, b, c) = a & b | ~a & c
ite(0, 0, 0) = 0
ite(0, 0, 1) = x
ite(0, 0, x) = x   <- :-(
ite(0, 1, 0) = F
ite(0, 1, 1) = 1
ite(0, 1, x) = 1   <- ok
ite(0, x, 0) = 0
ite(0, x, 1) = x
ite(0, x, x) = x   <- ok


ite(1, 0, 0) = 0
ite(1, 0, 1) = F
ite(1, 0, x) = 0   <- ok
ite(1, 1, 0) = x
ite(1, 1, 1) = 1
ite(1, 1, x) = x   <- :-(
ite(1, x, 0) = x
ite(1, x, 1) = 1
ite(1, x, x) = x   <- ok


// fetches second operand  <- :-(
ite(x, 0, 0) = 0
ite(x, 0, 1) = 0
ite(x, 0, x) = 0   <- ok
ite(x, 1, 0) = 1
ite(x, 1, 1) = 1
ite(x, 1, x) = 1   <- ok
ite(x, x, 0) = x
ite(x, x, 1) = x
ite(x, x, x) = x   <- ok

restrict(a, b)
restrict(0, 0) = x
restrict(0, 1) = -
restrict(0, x) = 0
restrict(1, 0) = -
restrict(1, 1) = x
restrict(1, x) = 1
restrict(x, 0) = x
restrict(x, 1) = x
restrict(x, x) = x
*/
