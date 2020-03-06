#include <bdd.h>
#include <iostream>
#include <assert.h>
#include <vector>
#include <sstream>
#include <functional>

using namespace std;

static std::vector<std::string> *result_buffer;

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

    return 0;
}
