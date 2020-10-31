/*
  Copyright 2018, Claas Lorenz. This file is licensed under GPL v2 plus
  a special exception, as described in included LICENSE_EXCEPTION.txt.

  Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#include "array_unit.h"


void ArrayTest::test_array_all_x() {
    printf("\n");

    array_t *a = array_from_str("xxxxxxxx");
    CPPUNIT_ASSERT(array_all_x(a, 1));
    array_free(a);

    a = array_from_str("xxxxxxx0");
    CPPUNIT_ASSERT(!array_all_x(a, 1));
    array_free(a);

    a = array_from_str("xxxxxx1x");
    CPPUNIT_ASSERT(!array_all_x(a, 1));
    array_free(a);

    a = array_from_str("xxxxxxxz");
    CPPUNIT_ASSERT(!array_all_x(a, 1));
    array_free(a);

    a = array_from_str("xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx");
    CPPUNIT_ASSERT(array_all_x(a, 6));
    array_free(a);

    a = array_from_str("xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxx0,xxxxxxxx");
    CPPUNIT_ASSERT(!array_all_x(a, 6));
    array_free(a);
}

void ArrayTest::test_array_has_x() {
    printf("\n");

    array_t *a = array_from_str("11001110");
    CPPUNIT_ASSERT(!array_has_x(a, 1));
    array_free(a);

    a = array_from_str("11111111");
    CPPUNIT_ASSERT(!array_has_x(a, 1));
    array_free(a);

    a = array_from_str("00000000");
    CPPUNIT_ASSERT(!array_has_x(a, 1));
    array_free(a);

    a = array_from_str("zzzzzzzz");
    CPPUNIT_ASSERT(!array_has_x(a, 1));
    array_free(a);

    a = array_from_str("110x1110");
    CPPUNIT_ASSERT(array_has_x(a, 1));
    array_free(a);

    a = array_from_str("110x11z0");
    CPPUNIT_ASSERT(array_has_x(a, 1));
    array_free(a);

    a = array_from_str(
        "11001110,11111111,00000000,10101010,01010101,1x000111"
    );
    CPPUNIT_ASSERT(array_has_x(a, 6));
    array_free(a);

    a = array_from_str("11001110,11111111,00x00000,10101010,01010101,11000111");
    CPPUNIT_ASSERT(array_has_x(a, 6));
    array_free(a);

    a = array_from_str("11001110,11111111,00000000,10101010,01010101,11000111");
    CPPUNIT_ASSERT(!array_has_x(a, 6));
    array_free(a);
}

void ArrayTest::test_array_has_z() {
    printf("\n");

    array_t *a = array_from_str("11001x10");
    CPPUNIT_ASSERT(!array_has_z(a, 1));
    array_free(a);

    a = array_from_str("11111111");
    CPPUNIT_ASSERT(!array_has_z(a, 1));
    array_free(a);

    a = array_from_str("00000000");
    CPPUNIT_ASSERT(!array_has_z(a, 1));
    array_free(a);

    a = array_from_str("xxxxxxxx");
    CPPUNIT_ASSERT(!array_has_z(a, 1));
    array_free(a);

    a = array_from_str("1z0x0111");
    CPPUNIT_ASSERT(array_has_z(a, 1));
    array_free(a);

    a = array_from_str("zzzzzzzz");
    CPPUNIT_ASSERT(array_has_z(a, 1));
    array_free(a);

    a = array_from_str(
        "11001110,11111111,00000000,10101010,01010101,1z000111"
    );
    CPPUNIT_ASSERT(array_has_z(a, 6));
    array_free(a);

    a = array_from_str("11001110,11111111,00z00000,10101010,01010101,11000111");
    CPPUNIT_ASSERT(array_has_z(a, 6));
    array_free(a);

    a = array_from_str("11001110,11111111,00000000,10101010,01010101,11000111");
    CPPUNIT_ASSERT(!array_has_z(a, 6));
    array_free(a);
}


void ArrayTest::test_array_is_sub_eq() {
    printf("\n");

    // Example 1: is 1xxxxxxx a subset of or equal to 1xxxxxx1?
    // 0b1111 1111 1011 1111  (0xffbf) <- a
    // 0b1111 1110 1011 1111  (0xfebf) <- b
    // 0b0000 0001 0000 0000  (0x0100) <- diff = a ^ b

    // 0b1111 1110 1011 1111  (0xfebf) <- b
    // 0b1111 1101 0111 1110  (0xfc7e) <- b << 1
    // 0b1010 1010 1010 1010  (0xaaaa) <- EVEN_MASK
    // 0b1010 1000 0010 1010  (0xa82a) <- f_b = b & (b << 1) & EVEN_MASK

    // 0b1111 1110 1011 1111  (0xfebf) <- b
    // 0b0111 1111 0101 1111  (0x7f5f) <- b >> 1
    // 0b0101 0101 0101 0101  (0x5555) <- ODD_MASK
    // 0b0101 0100 0001 0101  (0x5415) <- f_s = b & (b >> 1) & ODD_MASK

    // 0b1111 1100 0011 1111  (0xfc3f) <- set_x = f_b | f_s
    // 0b0000 0001 0000 0000  (0x0100) <- diff
    // 0b0000 0001 0000 0000  (0x0100) res = diff & ~set_x

    array_t *a = array_from_str("1xxxxxxx");
    array_t *b = array_from_str("1xxxxxx1");

    CPPUNIT_ASSERT(!array_is_sub_eq(a,b,1));
    CPPUNIT_ASSERT(array_is_sub_eq(b,a,1));

    // Example 2: is 1xxxxxx1 a subset of or equal to 0xxxxxxx?
    // 0b1111 1110 1011 1111  (0xfebf) <- a
    // 0b1111 1111 0111 1111  (0xff7f) <- b
    // 0b0000 0001 1100 0000  (0x01c0) <- diff = a ^ b

    // 0b1111 1111 0111 1111  (0xff7f) <- b
    // 0b1111 1110 1111 1110  (0xfefe) <- b << 1
    // 0b1010 1010 1010 1010  (0xaaaa) <- EVEN_MASK
    // 0b1010 1010 0010 1010  (0xaa2a) <- f_b = b & (b << 1) & EVEN_MASK

    // 0b1111 1111 0111 1111  (0xff7f) <- b
    // 0b0111 1111 1011 1111  (0x7fbf) <- b >> 1
    // 0b0101 0101 0101 0101  (0x5555) <- ODD_MASK
    // 0b0101 0101 0001 0101  (0x5515) <- s_b = b & (b >> 1) & ODD_MASK

    // 0b1111 1111 0011 1111  (0xff3f) <- set_x = f_b | s_b
    // 0b0000 0001 1100 0000  (0x01c0) <- diff
    // 0b0000 0000 1100 0000  (0x0100) <- res = diff & ~set_x

    array_t *c = array_from_str("0xxxxxxx");

    CPPUNIT_ASSERT(!array_is_sub_eq(a,c,1));
    CPPUNIT_ASSERT(!array_is_sub_eq(c,a,1));
    CPPUNIT_ASSERT(!array_is_sub_eq(b,c,1));
    CPPUNIT_ASSERT(!array_is_sub_eq(c,b,1));

    array_free(a);
    array_free(b);
    array_free(c);
}


void ArrayTest::test_array_is_equal() {
    printf("\n");

    array_t *a = array_from_str("1xxxxxx0");
    CPPUNIT_ASSERT(array_is_eq(a,a,1));

    array_t *b = array_from_str("1xxxxxx0");
    CPPUNIT_ASSERT(array_is_eq(a,b,1));

    array_t *c = array_from_str("0xxxxx1x");
    CPPUNIT_ASSERT(!array_is_eq(a,c,1));

    array_free(a);
    array_free(b);
    array_free(c);
}


void ArrayTest::test_array_is_sub() {
    printf("\n");

    CPPUNIT_ASSERT(!array_is_sub(NULL, NULL, 1));

    array_t *a = array_from_str("1xxxxxx0");
    CPPUNIT_ASSERT(!array_is_sub(a,a,1));
    CPPUNIT_ASSERT(array_is_sub(NULL, a, 1));

    array_t *b = array_from_str("1xxxxxx0");
    CPPUNIT_ASSERT(!array_is_sub(a,b,1));

    array_t *c = array_from_str("1xxxxx10");
    CPPUNIT_ASSERT(array_is_sub(c,a,1));

    array_t *d = array_from_str("zxxxxxxx");
    CPPUNIT_ASSERT(!array_is_sub(d, d, 1));
    CPPUNIT_ASSERT(array_is_sub(d, a, 1));
    CPPUNIT_ASSERT(array_is_sub(d, c, 1));
    CPPUNIT_ASSERT(!array_is_sub(a, d, 1));
    CPPUNIT_ASSERT(!array_is_sub(c, d, 1));
    CPPUNIT_ASSERT(!array_is_sub(NULL, d, 1));
    CPPUNIT_ASSERT(!array_is_sub(d, NULL, 1));

    array_free(a);
    array_free(b);
    array_free(c);
    array_free(d);

    array_t *la = array_from_str(
        "1xxxxxx0,xxxxxxxx,xxxxxxxx,1xxxxxxx,xxxxxxxx,xxxxxxx0,xxxxxxxx"
    );
    array_t *lb = array_from_str(
        "1xxxxxx0,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxx0,xxxxxxxx"
    );

    CPPUNIT_ASSERT(array_is_sub(la, lb, 6));

    array_free(la);
    array_free(lb);
}


void ArrayTest::test_array_one_bit_subtract() {
    printf("\n");

    array_t *a = array_from_str("10xxxxx0");
    array_t *b = array_from_str("10xxxxx1");
    array_t *r = array_from_str("10xxxxx1");

    size_t diffs = array_one_bit_subtract(a, b, 1);

    CPPUNIT_ASSERT(diffs == 1);
    CPPUNIT_ASSERT(array_is_eq(b, r, 1));

    array_free(a);
    array_free(b);
    array_free(r);


    a = array_from_str("10xxxx10");
    b = array_from_str("10xxxxx1");
    r = array_from_str("10xxxxx1");

    diffs = array_one_bit_subtract(a, b, 1);

    CPPUNIT_ASSERT(diffs == 2);
    CPPUNIT_ASSERT(array_is_eq(b, r, 1));

    array_free(a);
    array_free(b);
    array_free(r);


    a = array_from_str("10xxxx10");
    b = array_from_str("10xxxx01");
    r = array_from_str("10xxxx01");

    diffs = array_one_bit_subtract(a, b, 1);

    CPPUNIT_ASSERT(diffs == 2);
    CPPUNIT_ASSERT(array_is_eq(b, r, 1));

    array_free(a);
    array_free(b);
    array_free(r);


    a = array_from_str("10xxxxx1");
    b = array_from_str("10xxxxx0");
    r = array_from_str("10xxxxx0");

    diffs = array_one_bit_subtract(a, b, 1);

    CPPUNIT_ASSERT(diffs == 1);
    CPPUNIT_ASSERT(array_is_eq(b, r, 1));

    array_free(a);
    array_free(b);
    array_free(r);


    a = array_from_str("11111101");
    b = array_from_str("11111111");
    r = array_from_str("11111111");

    diffs = array_one_bit_subtract(a, b, 1);

    CPPUNIT_ASSERT(diffs == 1);
    CPPUNIT_ASSERT(array_is_eq(b, r, 1));

    array_free(a);
    array_free(b);
    array_free(r);


    a = array_from_str("11111111");
    b = array_from_str("111111x1");
    r = array_from_str("11111101");

    diffs = array_one_bit_subtract(a, b, 1);

    CPPUNIT_ASSERT(diffs == 1);
    CPPUNIT_ASSERT(array_is_eq(b, r, 1));

    array_free(a);
    array_free(b);
    array_free(r);


    a = array_from_str("11111101");
    b = array_from_str("111111x1");
    r = array_from_str("11111111");

    diffs = array_one_bit_subtract(a, b, 1);

    CPPUNIT_ASSERT(diffs == 1);
    CPPUNIT_ASSERT(array_is_eq(b, r, 1));

    array_free(a);
    array_free(b);
    array_free(r);


    a = array_from_str("00000010");
    b = array_from_str("00000000");
    r = array_from_str("00000000");

    diffs = array_one_bit_subtract(a, b, 1);

    CPPUNIT_ASSERT(diffs == 1);
    CPPUNIT_ASSERT(array_is_eq(b, r, 1));

    array_free(a);
    array_free(b);
    array_free(r);


    a = array_from_str("000000x0");
    b = array_from_str("00000000");
    r = array_from_str("00000000");

    diffs = array_one_bit_subtract(a, b, 1);

    CPPUNIT_ASSERT(diffs == 0);
    CPPUNIT_ASSERT(array_is_eq(b, r, 1));

    array_free(a);
    array_free(b);
    array_free(r);


    a = array_from_str("00000000");
    b = array_from_str("11111111");
    r = array_from_str("11111111");

    diffs = array_one_bit_subtract(a, b, 1);

    CPPUNIT_ASSERT(diffs == 8);
    CPPUNIT_ASSERT(array_is_eq(b, r, 1));

    array_free(a);
    array_free(b);
    array_free(r);
}


void ArrayTest::test_array_merge() {
    printf("\n");

    array_t *a = array_from_str("10xxxxx1");
    array_t *b = array_from_str("11xxxxx1");
    array_t *c = array_from_str("1xxxxxx1");

    array_t *r = array_merge(a, b, 1);

    CPPUNIT_ASSERT(array_is_eq(r, c, 1));

    array_free(a);
    array_free(b);
    array_free(c);
    array_free(r);

    a = array_from_str("1001xxxx");
    b = array_from_str("1xx0xxxx");

    r = array_merge(a, b, 1);

    CPPUNIT_ASSERT(array_is_eq(r, NULL, 1));

    array_free(a);
    array_free(b);
    array_free(r);
}


// Successful cases for array_combine
// 1. A \subset B -> return B
// 2. B \subset A -> return A
// 3. A = B -> return either A or B: convention -> return A
// 4. A, B differ in exactly one bit position
//    ex. 1, 0 -> X
//    greater differences can not be combined,
//    result set would be greater than A \cup B
//    ex. (a) { 0010, 0011, 1010, 1011 } \in x01x = A
//            { 0000, 0001, 1000, 1001 } \in x00x = B
//            -> result = A \cup B = x0xx
//    ex. (b) { 0010, 0011, 1010, 1011 } \in x01x = A
//            { 0100, 0101, 1100, 1101 } \in x10x = B
//            -> if combining differences naively
//            -> xxxx which would encompasses 2^3 more elements than A \cup B
// 5. A, B differ in more bit positions
//    combinations possible, iff
//    - prefix(A) \subset prefix(B) \land
//    - suffix(A), suffix(B) differ in one bit position
//    ex. 1001 = A
//        1xx0 = B
//        -> prefix(A) = 100, prefix(B) = 1xx
//        -> prefix(A) \subset prefix(B)
//        -> suffix(A) = 1, suffix(B) = 0, differ in one bit position
//    -> return B and prefix(A)+combination(suffix(A),suffix(B))
//    -> reverse case analogous
//    -> combination results in A encompassing more elements, B remains the same
//
// Observations:
// 1. \0 \subset A, \forall sets A
//    -> If either array contains Z -> return other array
// ...
//
// Unsuccessful combinations:
// 1. A \cap B = \0 and bit difference > 1, but mind (5)
// ...
//
// Combinations derived from original implementation (cases from last):
// 1. 10x0 \cup 10x1 -> 10xx (4a)
// 2. 1001 \cup 1xx0 -> 100x \cup 1xx0 (5a)
// 3. 1xx0 \cup 1001 -> 1xx0 \cup 100x (5b)
//
// 10x1 \cup 1x00
// { 1001, 1011 }
// { 1000, 1100 }
// 10x1 = { 1001, 1011 }
// 1x00 = { 1000, 1100 }
// 100x = { 1000, 1001 }
// -> extra contains elements from A, B --> useful to have extra?
//
// 1001 = { 1001 }
// 1xx0 = { 1000, 1010, 1100, 1110 }
// no intersection
// 100x = { 1001, 1000 }
// 1xx0 = { 1000, 1010, 1100, 1111 }
// -> A grows larger --> useful?
//
// --> Preserve originally intended semanatics as much as possible
// --> usefulness can only be determined in usage of extra
// --> masked tests should be done as well
void ArrayTest::test_array_combine() {
  printf("\n");

  // subset test (1a)
  // \0 \subset B, \forall sets B
  array_t *a = array_from_str("zxxxxxxx");
  array_t *b = array_from_str("1xxxxxxx");
  array_t *e = NULL;
  array_t *r = array_from_str("1xxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(a == NULL);
  CPPUNIT_ASSERT(array_is_eq(b, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // subset test (2a)
  // \0 \subset B, \forall sets B
  a = array_from_str("zzzzzzzz");
  b = array_from_str("1xxxxxxx");
  e = NULL;
  r = array_from_str("1xxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(a == NULL);
  CPPUNIT_ASSERT(array_is_eq(b, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);
    
  // subset test (3a)
  a = array_from_str("11xxxxxx");
  b = array_from_str("1xxxxxxx");
  e = NULL;
  r = array_from_str("1xxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(a == NULL);
  CPPUNIT_ASSERT(array_is_eq(b, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // subset test (4a)
  a = array_from_str("11111111");
  b = array_from_str("1xxxxxxx");
  e = NULL;
  r = array_from_str("1xxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(a == NULL);
  CPPUNIT_ASSERT(array_is_eq(b, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // subset test (5a)
  a = array_from_str("11111111");
  b = array_from_str("xxxxxxxx");
  e = NULL;
  r = array_from_str("xxxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(a == NULL);
  CPPUNIT_ASSERT(array_is_eq(b, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // reverse subset cases
  // subset test (1b)
  // \0 \subset B, \forall sets B
  a = array_from_str("1xxxxxxx");
  b = array_from_str("zxxxxxxx");
  e = NULL;
  r = array_from_str("1xxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(array_is_eq(a, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // subset test (2b)
  // \0 \subset B, \forall sets B
  a = array_from_str("1xxxxxxx");
  b = array_from_str("zzzzzzzz");
  e = NULL;
  r = array_from_str("1xxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(array_is_eq(a, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);
    
  // subset test (3b)
  a = array_from_str("1xxxxxxx");
  b = array_from_str("11xxxxxx");
  e = NULL;
  r = array_from_str("1xxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(array_is_eq(a, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // subset test (4b)
  a = array_from_str("1xxxxxxx");
  b = array_from_str("11111111");
  e = NULL;
  r = array_from_str("1xxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(array_is_eq(a, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // subset test (5b)
  a = array_from_str("xxxxxxxx");
  b = array_from_str("11111111");
  e = NULL;
  r = array_from_str("xxxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(array_is_eq(a, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // A = B
  // equality test (1)
  a = array_from_str("11111111");
  b = array_from_str("11111111");
  e = NULL;
  r = array_from_str("11111111");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(array_is_eq(a, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // equality test (2)
  a = array_from_str("zxxxxxxx");
  b = array_from_str("zxxxxxxx");
  e = NULL;
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(a == NULL);
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);

  // equality test (3)
  // since any z in a set makes it empty, a should be the result
  a = array_from_str("zxxxxxxx");
  b = array_from_str("xxxxxxxz");
  e = NULL;
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(a == NULL);
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);

  // difference in one bit position (1)
  a = array_from_str("1000xxxx");
  b = array_from_str("1001xxxx");
  e = NULL;
  r = array_from_str("100xxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(a == NULL);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(array_is_eq(e, r, 1));
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // difference in one bit position (2)
  a = array_from_str("1xxxxxx0");
  b = array_from_str("1xxxxxx1");
  e = NULL;
  r = array_from_str("1xxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(a == NULL);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(array_is_eq(e, r, 1));
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // difference in more than one bit position (1)
  // (behaviour as expected from comments)
  a = array_from_str("1001xxxx");
  b = array_from_str("1xx0xxxx");
  e = NULL;
  array_t *r1 = array_from_str("1001xxxx");
  array_t *r2 = array_from_str("1xx0xxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(e == NULL);
  CPPUNIT_ASSERT(array_is_eq(a, r1, 1));
  CPPUNIT_ASSERT(array_is_eq(b, r2, 1));
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r1);
  array_free(r2);

  // difference in more than one bit position (2)
  // (behaviour as expected from comments)
  a = array_from_str("1xx0xxxx");
  b = array_from_str("1001xxxx");
  e = NULL;
  r1 = array_from_str("1001xxxx");
  r2 = array_from_str("1xx0xxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(e == NULL);
  CPPUNIT_ASSERT(array_is_eq(a, r2, 1));
  CPPUNIT_ASSERT(array_is_eq(b, r1, 1));
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r1);
  array_free(r2);

  // difference in more than one bit position (3)
  // (behaviour as expected from comments)
  a = array_from_str("10x1xxxx");
  b = array_from_str("1x00xxxx");
  e = NULL;
  r1 = array_from_str("10x1xxxx");
  r2 = array_from_str("1x00xxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(array_is_eq(a, r1, 1));
  CPPUNIT_ASSERT(array_is_eq(b, r2, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r1);
  array_free(r2);
}


#ifdef USE_INV
void ArrayTest::test_array_and() {
    printf("\n");

    array_t *a = array_from_str("10xxxx01");
    array_t *b = array_from_str("10xxxx01");
    array_t *r = array_from_str("10xxxx01");

    array_t *res = array_create(1, BIT_UNDEF);

    array_and(a, b, 1, res);

    CPPUNIT_ASSERT(array_is_eq(r, res, 1));

    array_free(a);
    array_free(b);
    array_free(r);
    array_free(res);


    a = array_from_str("10xxxx01");
    b = array_from_str("10xxxx10");
    r = array_from_str("10xxxx00");

    res = array_create(1, BIT_UNDEF);

    array_and(a, b, 1, res);

    CPPUNIT_ASSERT(array_is_eq(r, res, 1));

    array_free(a);
    array_free(b);
    array_free(r);
    array_free(res);


    a = array_from_str("10xxx101");
    b = array_from_str("10xxxx01");
    r = array_from_str("10xxxx01");

    res = array_create(1, BIT_UNDEF);

    array_and(a, b, 1, res);

    CPPUNIT_ASSERT(array_is_eq(r, res, 1));

    array_free(a);
    array_free(b);
    array_free(r);
    array_free(res);


    a = array_from_str("10zxzx01");
    b = array_from_str("10zzxxzz");
    r = array_from_str("10z00x0z");

    res = array_create(1, BIT_UNDEF);

    array_and(a, b, 1, res);

    CPPUNIT_ASSERT(array_is_eq(r, res, 1));

    array_free(a);
    array_free(b);
    array_free(r);
    array_free(res);
}
#endif


void ArrayTest::test_array_cmpl() {
  printf("\n");

  array_t *a = array_from_str("10000000");
  size_t n;
  array_t **res = (array_t **)malloc(8 * sizeof a);

  CPPUNIT_ASSERT(array_cmpl(a, 1, &n, res));
  CPPUNIT_ASSERT(8 == n);

  array_t **r = (array_t **)malloc(8 * sizeof a);

  r[0] = array_from_str("xxx1xxxx");
  r[1] = array_from_str("xx1xxxxx");
  r[2] = array_from_str("x1xxxxxx");
  r[3] = array_from_str("0xxxxxxx");
  r[4] = array_from_str("xxxxxxx1");
  r[5] = array_from_str("xxxxxx1x");
  r[6] = array_from_str("xxxxx1xx");
  r[7] = array_from_str("xxxx1xxx");

  for (size_t i = 0; i < n; i++)
    CPPUNIT_ASSERT(array_is_eq(res[i], r[i], 1));

  array_free(a);

  for (size_t i = 0; i < n; i++)
    array_free(res[i]);
  free(res);

  for (size_t i = 0; i < 8; i++)
    array_free(r[i]);
  free(r);


  a = array_from_str("xxxx1010");
  n = 0;
  res = (array_t **)malloc(4 * sizeof a);

  CPPUNIT_ASSERT(array_cmpl(a, 1, &n, res));
  CPPUNIT_ASSERT(4 == n);

  r = (array_t **)malloc(4 * sizeof a);

  r[0] = array_from_str("xxxxxxx1");
  r[1] = array_from_str("xxxxxx0x");
  r[2] = array_from_str("xxxxx1xx");
  r[3] = array_from_str("xxxx0xxx");

  for (size_t i = 0; i < n; i++)
    CPPUNIT_ASSERT(array_is_eq(res[i], r[i], 1));

  array_free(a);

  for (size_t i = 0; i < n; i++)
    array_free(res[i]);
  free(res);

  for (size_t i = 0; i < 4; i++)
    array_free(r[i]);
  free(r);


  a = array_from_str("xxxxzzzz");
  n = 0;

/*
  // XXX: original behaviour
  res = (array_t **)malloc(8 * sizeof a);

  CPPUNIT_ASSERT(array_cmpl(a, 1, &n, res));
  CPPUNIT_ASSERT(8 == n);

  r = (array_t **)malloc(8 * sizeof a);

  r[0] = array_from_str("xxxxxxx0");
  r[1] = array_from_str("xxxxxxx1");
  r[2] = array_from_str("xxxxxx0x");
  r[3] = array_from_str("xxxxxx1x");
  r[4] = array_from_str("xxxxx0xx");
  r[5] = array_from_str("xxxxx1xx");
  r[6] = array_from_str("xxxx0xxx");
  r[7] = array_from_str("xxxx1xxx");

  for (size_t i = 0; i < n; i++)
    CPPUNIT_ASSERT(array_is_eq(res[i], r[i], 1));

  array_free(a);

  for (size_t i = 0; i < n; i++)
    array_free(res[i]);
  free(res);

  for (size_t i = 0; i < 8; i++)
    array_free(r[i]);
  free(r);
*/

  res = (array_t **)malloc(1 * sizeof a);

  CPPUNIT_ASSERT(array_cmpl(a, 1, &n, res));
  CPPUNIT_ASSERT(1 == n);

  r = (array_t **)malloc(1 * sizeof a);

  r[0] = array_from_str("xxxxxxxx");

  CPPUNIT_ASSERT(array_is_eq(res[0], r[0], 1));

  array_free(a);
  array_free(res[0]);
  free(res);
  array_free(r[0]);
  free(r);
}


void ArrayTest::test_array_isect() {
  printf("\n");

  array_t *a = array_from_str("10xz10xz,10xz10xz");
  array_t *b = array_from_str("10xz0xz1,xz10z10x");
  array_t *r = array_from_str("10xzz0zz,1z1zzz0z");

  array_t *res = array_create(2, BIT_UNDEF);

  array_isect(a, b, 2, res);

  CPPUNIT_ASSERT(array_is_eq(r, res, 2));

  array_free(a);
  array_free(b);
  array_free(r);
  array_free(res);
}


void ArrayTest::test_array_not() {
  printf("\n");

  array_t *a = array_from_str("10xz10xz");
#ifdef STRICT_RW
  array_t *r = array_from_str("01zx01zx");
#else
  array_t *r = array_from_str("01xz01xz");
#endif

  array_t *res = array_create(1, BIT_UNDEF);

  array_not(a, 1, res);

  CPPUNIT_ASSERT(array_is_eq(r, res, 1));

  array_free(a);
  array_free(r);
  array_free(res);
}


void ArrayTest::test_array_rewrite() {
  printf("\n");

  array_t *a  = array_from_str("10xz10xz");
#ifdef STRICT_RW
  array_t *m  = array_from_str("10111100");
#else
  array_t *m  = array_from_str("10xx1100");
#endif
  array_t *rw = array_from_str("01xxx10x");

#ifdef STRICT_RW
  array_t *res  = array_from_str("00xxx1xz");
#else
  array_t *res  = array_from_str("11xx110x");
#endif

  array_rewrite(a, m, rw, 1);

  CPPUNIT_ASSERT(array_is_eq(res, a, 1));

  array_free(a);
  array_free(m);
  array_free(rw);
  array_free(res);
}


void ArrayTest::test_array_generic_resize() {
  printf("\n");

  enum bit_val vals[4] = { BIT_X, BIT_0, BIT_1, BIT_Z };

  array_t *a = array_from_str("10xxxxxx");
  array_t *exp[4] = {
    array_from_str("10xxxxxx,xxxxxxxx"),
    array_from_str("10xxxxxx,00000000"),
    array_from_str("10xxxxxx,11111111"),
    array_from_str("10xxxxxx,zzzzzzzz")
  };

  for (size_t i = 0; i < 4; i++) {
    array_t *tmp = array_generic_resize(array_copy(a, 1), 1, 2, vals[i]);
    CPPUNIT_ASSERT(array_is_eq(tmp, exp[i], 2));
    array_free(tmp);
  }

  for (size_t i = 0; i < 4; i++) array_free(exp[i]);

  array_t *exp2[4] = {
    array_from_str("10xxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx,xxxxxxxx"),
    array_from_str("10xxxxxx,00000000,00000000,00000000,00000000,00000000"),
    array_from_str("10xxxxxx,11111111,11111111,11111111,11111111,11111111"),
    array_from_str("10xxxxxx,zzzzzzzz,zzzzzzzz,zzzzzzzz,zzzzzzzz,zzzzzzzz")
  };

  for (size_t i = 0; i < 4; i++) {
    array_t *tmp = array_generic_resize(array_copy(a, 1), 1, 6, vals[i]);
    CPPUNIT_ASSERT(array_is_eq(tmp, exp2[i], 2));
    array_free(tmp);
  }

  for (size_t i = 0; i < 4; i++) array_free(exp2[i]);

  array_free(a);
}


void ArrayTest::test_array_combine_regression() {
  printf("\n");

  array_t *a = array_from_str("0000110x");
  array_t *b = array_from_str("0001010x");
  array_t *extra = NULL;
  array_t *res = array_from_str("000xx10x");

  array_combine(&a, &b, &extra, NULL, 1);

  CPPUNIT_ASSERT(a != NULL);
  CPPUNIT_ASSERT(b != NULL);
  CPPUNIT_ASSERT(!array_is_eq(extra, res, 1));
  CPPUNIT_ASSERT(extra == NULL);

  array_free(a);
  array_free(b);
  array_free(extra);
  array_free(res);
}


void ArrayTest::test_array_has_xz_regression() {
  printf("\n");

  array_t *a = array_from_str("\
00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,\
00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,\
00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,\
00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,\
11111111,11111111,11111111,11111111"
  );

  CPPUNIT_ASSERT(!array_has_x(a, 36));
  CPPUNIT_ASSERT(!array_has_z(a, 36));

  array_free(a);
}
