/*
  Copyright 2026, Claas Lorenz. This file is licensed under GPL v2 plus
  a special exception, as described in included LICENSE_EXCEPTION.txt.

  Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

/*
 * Oracle / algebraic-law tests for the headerspace primitives (array_t, hs).
 *
 * These pin the *semantics* of the verification core against an independent
 * concrete-packet oracle (see oracle_util.h), so the internal representation
 * (compaction, diff lists, wildcard handling, ...) can be refactored with the
 * guarantee that observable set behaviour is preserved. This complements the
 * case-based ArrayTest/HeaderspaceTest suites, which check specific inputs.
 */

#ifndef HEADERSPACE_TEST_ORACLE_UNIT_H_
#define HEADERSPACE_TEST_ORACLE_UNIT_H_

#include "cppunit/TestCase.h"
#include "cppunit/TestFixture.h"
#include <cppunit/extensions/HelperMacros.h>

class OracleTest : public CppUnit::TestFixture {
  CPPUNIT_TEST_SUITE(OracleTest);
  // anchor: validate the oracle decoder itself
  CPPUNIT_TEST(test_oracle_self_consistency);
  // array_t (single-cube) operations vs the oracle
  CPPUNIT_TEST(test_array_isect_oracle);
  CPPUNIT_TEST(test_array_cmpl_oracle);
  CPPUNIT_TEST(test_array_rewrite_identities);
  CPPUNIT_TEST(test_array_predicate_laws);
  // hs (header space) operations vs the oracle
  CPPUNIT_TEST(test_hs_isect_oracle);
  CPPUNIT_TEST(test_hs_minus_oracle);
  CPPUNIT_TEST(test_hs_cmpl_oracle);
  CPPUNIT_TEST(test_hs_add_oracle);
  CPPUNIT_TEST(test_hs_compact_invariance);
  // algebraic laws (pure API-vs-API, compared in the concrete domain)
  CPPUNIT_TEST(test_hs_demorgan);
  CPPUNIT_TEST(test_hs_minus_eq_isect_cmpl);
  // deterministic regressions for the two engine bugs this harness found
  CPPUNIT_TEST(test_hs_cmpl_universe_regression);
  CPPUNIT_TEST(test_hs_add_hs_diff_source_regression);
  CPPUNIT_TEST_SUITE_END();

 public:
  void test_oracle_self_consistency();
  void test_array_isect_oracle();
  void test_array_cmpl_oracle();
  void test_array_rewrite_identities();
  void test_array_predicate_laws();
  void test_hs_isect_oracle();
  void test_hs_minus_oracle();
  void test_hs_cmpl_oracle();
  void test_hs_add_oracle();
  void test_hs_compact_invariance();
  void test_hs_demorgan();
  void test_hs_minus_eq_isect_cmpl();
  void test_hs_cmpl_universe_regression();
  void test_hs_add_hs_diff_source_regression();
};

#endif // HEADERSPACE_TEST_ORACLE_UNIT_H_
