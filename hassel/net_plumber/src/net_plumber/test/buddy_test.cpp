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
    cout << endl;
}

void allsatPrintHandler(char* varset, int size)
{
    stringstream s;
    for (int v=0; v<size; ++v)
    {
        char c = (varset[v] < 0 ? 'x' : (char)('0' + varset[v]));
        cout << c; s << c;
    }
    cout << endl;
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
    bdd_setvarnum(1);

    const bdd dc = bddtrue;
    const bdd zero = bdd_nithvar(0);
    const bdd one = bdd_ithvar(0);

    cout << "(0 & 1) => 0 = ";
    bdd_allsat(bdd_imp((zero & one), zero), *print_handler);

    cout << "(0 & 1) => 1 = ";
    bdd_allsat(bdd_imp((zero & one), one), *print_handler);

    cout << "(0 & 1) => x = ";
    bdd_allsat(bdd_imp((zero & one), dc), *print_handler);

    bdd_done();

    return 0;
}

/*
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
0 & 0 = 0
0 & 1 = -
0 & x = 0
1 & 0 = -
1 & 1 = 1
1 & x = 1
x & 0 = 0
x & 1 = 1
x & x = x


a <=> b
0 <=> 0 = x
0 <=> 1 = -
0 <=> x = 0
1 <=> 0 = -
1 <=> 1 = x
1 <=> x = 1
x <=> 0 = 0
x <=> 1 = 1
x <=> x = x

ite(a, b, c)
ite(0, 0, 0) = 0
ite(0, 0, 1) = x
ite(0, 0, x) = x
ite(0, 1, 0) = -
ite(0, 1, 1) = 1
ite(0, 1, x) = 1
ite(0, x, 0) = 0
ite(0, x, 1) = x
ite(0, x, x) = x
ite(1, 0, 0) = 0
ite(1, 0, 1) = -
ite(1, 0, x) = 0
ite(1, 1, 0) = x
ite(1, 1, 1) = 1
ite(1, 1, x) = x
ite(1, x, 0) = x
ite(1, x, 1) = 1
ite(1, x, x) = x
ite(x, 0, 0) = 0
ite(x, 0, 1) = 0
ite(x, 0, x) = 0
ite(x, 1, 0) = 1
ite(x, 1, 1) = 1
ite(x, 1, x) = 1
ite(x, x, 0) = x
ite(x, x, 1) = x
ite(x, x, x) = x
*/
