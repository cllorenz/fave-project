#include <bdd.h>
#include <iostream>
#include <assert.h>

using namespace std;

int main(void) {
    bdd x, y, z;

    bdd_init(1000, 100);
    bdd_setvarnum(5);

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

    bdd_done();

    return 0;
}
