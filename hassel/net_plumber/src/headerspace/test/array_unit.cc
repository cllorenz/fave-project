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

void ArrayTest::test_array_combine() {
    printf("\n");

    array_t *a = array_from_str("1xxxxxx0");
    array_t *b = array_from_str("1xxxxxx1");

    array_t *res = array_from_str("1xxxxxxx");
    array_t *tmp;

    array_combine(&a, &b, &tmp, NULL, 1);

    CPPUNIT_ASSERT(array_is_eq(res, tmp, 1));

    array_free(a);
    array_free(b);
    array_free(res);
    array_free(tmp);
}
