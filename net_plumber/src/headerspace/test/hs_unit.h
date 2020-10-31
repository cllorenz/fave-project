/*
  Copyright 2018, Claas Lorenz. This file is licensed under GPL v2 plus
  a special exception, as described in included LICENSE_EXCEPTION.txt.

  Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#ifndef SRC_NET_PLUMBER_TEST_HS_UNIT_H_
#define SRC_NET_PLUMBER_TEST_HS_UNIT_H_

#include "cppunit/TestCase.h"
#include "cppunit/TestFixture.h"
#include <cppunit/extensions/HelperMacros.h>
extern "C" {
  #include "../hs.h"
}
#include "log4cxx/logger.h"

#include <sstream>

#define HS_TEST_LEN 1

class HeaderspaceTest : public CppUnit::TestFixture {
        CPPUNIT_TEST_SUITE(HeaderspaceTest);

        CPPUNIT_TEST(test_copy);
        CPPUNIT_TEST(test_copy_a);
        CPPUNIT_TEST(test_from_str);
        CPPUNIT_TEST(test_add);
        CPPUNIT_TEST(test_add_hs);
        CPPUNIT_TEST(test_diff);
        CPPUNIT_TEST(test_compact);
        CPPUNIT_TEST(test_compact_m);
        CPPUNIT_TEST(test_comp_diff);
        CPPUNIT_TEST(test_cmpl);
        CPPUNIT_TEST(test_isect);
        CPPUNIT_TEST(test_isect_a);
        CPPUNIT_TEST(test_isect_arr);
        CPPUNIT_TEST(test_minus);
        CPPUNIT_TEST(test_rewrite);
        CPPUNIT_TEST(test_vec_append);
        CPPUNIT_TEST(test_enlarge);
#ifdef USE_DEPRECATED
        CPPUNIT_TEST(test_potponed_diff_and_rewrite);
#endif
        CPPUNIT_TEST(test_is_empty);
        CPPUNIT_TEST(test_is_equal);
        CPPUNIT_TEST(test_is_equal_regression);
        CPPUNIT_TEST(test_is_sub);
        CPPUNIT_TEST(test_is_sub_regression);
        CPPUNIT_TEST(test_is_sub_eq);
        CPPUNIT_TEST(test_is_equal_and_is_sub_eq_regression);
        CPPUNIT_TEST(test_merge);
        CPPUNIT_TEST(test_compact_regression);
        CPPUNIT_TEST(test_is_equal_regression2);
//        CPPUNIT_TEST(test_comp_diff_regression);

        CPPUNIT_TEST_SUITE_END();

    public:
        void setUp();
        void tearDown();

        void test_copy();
        void test_copy_a();
        void test_from_str();
        void test_add();
        void test_add_hs();
        void test_diff();
        void test_compact();
        void test_compact_m();
        void test_comp_diff();
        void test_cmpl();
        void test_isect();
        void test_isect_a();
        void test_isect_arr();
        void test_minus();
        void test_rewrite();
        void test_vec_append();
        void test_enlarge();
#ifdef USE_DEPRECATED
        void test_potponed_diff_and_rewrite();
#endif
        void test_is_empty();
        void test_is_equal();
        void test_is_equal_regression();
        void test_is_sub();
        void test_is_sub_regression();
        void test_is_sub_eq();
        void test_is_equal_and_is_sub_eq_regression();
        void test_merge();
        void test_compact_regression();
        void test_is_equal_regression2();
        void test_comp_diff_regression();

    private:
        static log4cxx::LoggerPtr logger;
        hs *h;
        std::stringstream debug_msg;

        void debug(const char *msg, hs *h) {
            debug_msg << msg;
            char *s = NULL;
            if (h) {
                s = hs_to_str(h);
                debug_msg << s;
            }

            LOG4CXX_DEBUG(logger, debug_msg.str());

            if (s) free(s);

            debug_msg.str("");
            debug_msg.clear();
        }
};

#endif  // SRC_NET_PLUMBER_TEST_HS_UNIT_H_
