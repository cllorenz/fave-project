/*
   Copyright 2018 Claas Lorenz

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

#include "array_unit.h"

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

    array_t *a = array_from_str("1xxxxxx0");
    CPPUNIT_ASSERT(!array_is_sub(a,a,1));

    array_t *b = array_from_str("1xxxxxx0");
    CPPUNIT_ASSERT(!array_is_sub(a,b,1));

    array_t *c = array_from_str("1xxxxx10");
    CPPUNIT_ASSERT(array_is_sub(c,a,1));

    array_free(a);
    array_free(b);
    array_free(c);
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
  r = array_from_str("zxxxxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(array_is_eq(a, r, 1));
  CPPUNIT_ASSERT(e == NULL);
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r);

  // equality test (3)
  // since any z in a set makes it empty, a should be the result
  // TODO: currently fails
  // a = array_from_str("zxxxxxxx");
  // b = array_from_str("xxxxxxxz");
  // e = NULL;
  // r = array_from_str("zxxxxxxx");
  // array_combine(&a, &b, &e, NULL, 1);
  // CPPUNIT_ASSERT(b == NULL);
  // CPPUNIT_ASSERT(array_is_eq(a, r, 1));
  // CPPUNIT_ASSERT(e == NULL);
  // array_free(a);
  // array_free(b);
  // array_free(e);
  // array_free(r);

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
  array_t *r1 = array_from_str("100xxxxx");
  array_t *r2 = array_from_str("1xx0xxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(a == NULL);
  CPPUNIT_ASSERT(array_is_eq(b, r2, 1));
  CPPUNIT_ASSERT(array_is_eq(e, r1, 1));
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
  r1 = array_from_str("100xxxxx");
  r2 = array_from_str("1xx0xxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(b == NULL);
  CPPUNIT_ASSERT(array_is_eq(a, r2, 1));
  CPPUNIT_ASSERT(array_is_eq(e, r1, 1));
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
  array_t *r3 = array_from_str("100xxxxx");
  array_combine(&a, &b, &e, NULL, 1);
  CPPUNIT_ASSERT(array_is_eq(a, r1, 1));
  CPPUNIT_ASSERT(array_is_eq(b, r2, 1));
  CPPUNIT_ASSERT(array_is_eq(e, r3, 1));
  array_free(a);
  array_free(b);
  array_free(e);
  array_free(r1);
  array_free(r2);
  array_free(r3);
}
