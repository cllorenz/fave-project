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

   Authors: peyman.kazemian@gmail.com (Peyman Kazemian)
            cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#include "test/packet_set_unit.h"
#include "test/net_plumber_basic_unit.h"
#include "test/net_plumber_plumbing_unit.h"
#include "test/net_plumber_slicing_unit.h"
#include "test/conditions_unit.h"
#include "../headerspace/test/array_unit.h"
#include "../headerspace/test/hs_unit.h"
#ifdef USE_BDD
#include "bdd_packet_set.h"
#endif
#include "hs_packet_set.h"
#include "array_packet_set.h"
#include <string.h>
#include "main_processes.h"
#include "net_plumber.h"
// For UnitTesting
#include <cppunit/ui/text/TestRunner.h>
#include <cppunit/extensions/TestFactoryRegistry.h>
#include <cppunit/CompilerOutputter.h>
#include <cppunit/TestResult.h>
#include <cppunit/TestResultCollector.h>
#include <cppunit/BriefTestProgressListener.h>
// For Logging
#include <log4cxx/logger.h>
#include <log4cxx/logmanager.h>
#include "log4cxx/propertyconfigurator.h"
#include <log4cxx/basicconfigurator.h>

#include "rpc_handler.h"
#include <csignal>
#include <sys/resource.h>

using namespace log4cxx;
using namespace::std;
using namespace net_plumber;

static bool server_stop;

static void sig_stop(int) {
  server_stop = true;
}

template<class T1, class T2>
void run_server(string address, int port, NetPlumber<T1, T2> *N) {
  server_stop = false;
  signal(SIGINT, sig_stop);
  signal(SIGTERM, sig_stop);

  net_plumber::RpcHandler<T1, T2> handler(N);

  Json::Rpc::Server *server;
  if (port) {
    server = new Json::Rpc::TcpServer(address, port);
  } else {
    server = new Json::Rpc::UnixServer(address);
  }

  if (!networking::init()) errx(1, "Couldn't initialize networking.");
  handler.initServer(server);
  if (!server->Bind()) errx(1, "bind(0.0.0.0:%d) failed.", port);
  if (port) {
    if (!((Json::Rpc::TcpServer *)server)->Listen()) errx(1, "listen() failed.");
  } else {
    if (!((Json::Rpc::UnixServer *)server)->Listen()) errx(1, "listen() failed.");
  }

  printf("Server listening on port %d.\n", port);
  while (!server_stop) server->WaitMessage(1000);

  server->Close();
  delete server;
  networking::cleanup();

}

template<class T1, class T2>
void run_tests() {
  NetPlumberBasicTest<T1, T2> t1;
  CPPUNIT_TEST_SUITE_REGISTRATION( decltype(t1) );
  NetPlumberPlumbingTest<T1, T2> t2;
  CPPUNIT_TEST_SUITE_REGISTRATION( decltype(t2) );
#ifdef PIPE_SLICING
  NetPlumberSlicingTest<T1, T2> t3;
  CPPUNIT_TEST_SUITE_REGISTRATION( decltype(t3) );
#endif
  ConditionsTest<T1, T2> t4;
  CPPUNIT_TEST_SUITE_REGISTRATION( decltype(t4) );
  CPPUNIT_TEST_SUITE_REGISTRATION( ArrayTest );
  CPPUNIT_TEST_SUITE_REGISTRATION( HeaderspaceTest );

  PacketSetTest<T1, T2> t5;
  CPPUNIT_TEST_SUITE_REGISTRATION( decltype(t5) );
  PacketSetTest<T2, T2> t6;
  CPPUNIT_TEST_SUITE_REGISTRATION( decltype(t6) );

  // informs test-listener about testresults
  CPPUNIT_NS::TestResult testresult;

  // register listener for collecting the test-results
  CPPUNIT_NS::TestResultCollector collectedresults;
  testresult.addListener (&collectedresults);

  // register listener for per-test progress output
  CPPUNIT_NS::BriefTestProgressListener progress;
  testresult.addListener (&progress);

  // insert test-suite at test-runner by registry
  CPPUNIT_NS::TestRunner testrunner;
  testrunner.addTest (CPPUNIT_NS :: TestFactoryRegistry :: getRegistry ().
                      makeTest ());
  testrunner.run (testresult);

  // output results in compiler-format
  CPPUNIT_NS::CompilerOutputter compileroutputter(&collectedresults, std::cerr);
  compileroutputter.write ();
}

template<class T1, class T2>
int typed_main(int argc, char* argv[]) {
  bool do_run_server = false;
  bool do_run_test = false;
  bool do_load_json_files = false;
  bool do_dump_json_files = false;
  bool do_load_policy = false;
  bool do_print_network = false;

  string log_config_file = "";
  string json_files_path = "";
  string dump_files_path = "";
  string policy_json_file = "";
  int hdr_len = 1;
  string server_address;
  int server_port = 0;
  T2 *filter = nullptr;

  for (int i = 1; i < argc; i++) {
    if ( strcmp(argv[i] , "--help") == 0 ) {
      printf("Usage: net_plumber [run option(s)][settings]\n");
      printf("  run options:\n");
      printf("\t --test  runs all the unit tests.\n");
      printf("\t --server <ip> <port> : runs net_plumber as a server listening for updates on address <ip> and port <port>.\n");
      printf("\t --load <path> : load the rules from json files in the <path>.\n");
      printf("\t --dump <path> : dump the dependency graph to json files in the <path>.\n");
      printf("\t --policy <file> : loads the source and probe nodes from a json policy <file>.\n");
      printf("\t --filter <filter-wc> : cluster based on <wc-filter>.\n");

      printf("  settings:\n");
      printf("\t --log4j-config <config file> : path to <log4j config> file.\n");
      printf("\t --hdr-len <length> : <length> of packet header (default is 1 byte).\n");
      printf("\t --print : print plumbing network.\n");
      break;
    }
    if ( strncmp(argv[i], "--unix", 6) == 0 ) {
      if (i + 1 >= argc) {
        printf("Please specify a file path.\n");
        return -1;
      }
      server_address = argv[++i];
      server_port = 0;
      do_run_server = true;
    }
    if ( strncmp(argv[i], "--server", 8) == 0 ) {
      if (i + 2 >= argc) {
        printf("Please specify IP and port for server.\n");
        return -1;
      }
      server_address = argv[++i];
      server_port = atoi(argv[++i]);
      do_run_server = true;
    }
    if ( strncmp(argv[i], "--test", 6) == 0 ) {
      do_run_test = true;
    }

    if ( strncmp(argv[i], "--policy", 8) == 0)  {
      if (i+1 >= argc) {
        printf("Please specify policy file after --policy.\n");
        return -1;
      }
      do_load_policy = true;
      policy_json_file = string(argv[++i]);
    }

    if ( strncmp(argv[i], "--load", 6) == 0)  {
      if (i+1 >= argc) {
        printf("Please specify path to json files after --load.\n");
        return -1;
      }
      do_load_json_files = true;
      json_files_path = string(argv[++i]);
    }

    if ( strncmp(argv[i], "--dump", 6) == 0)  {
      if (i+1 >= argc) {
        printf("Please specify path after --load.\n");
        return -1;
      }
      do_dump_json_files = true;
      dump_files_path = string(argv[++i]);
    }

    if ( strncmp(argv[i], "--filter", 8) == 0)  {
      if (i+1 >= argc) {
        printf("Please specify a header after --filter.\n");
        return -1;
      }
#ifdef GENERIC_PS
      filter = new T2(argv[++i]);
#else
      filter = array_from_str(argv[++i]);
#endif
    }

    if ( strncmp(argv[i], "--log4j-config", 14) == 0 ) {
      if (i+1 >= argc) {
        printf("Please specify config file name after --log4j-config.\n");
        return -1;
      }
      log_config_file = string(argv[++i]);
    }

    if ( strncmp(argv[i], "--hdr-len", 9) == 0 ) {
      if (i+1 >= argc) {
        printf("Please specify length of header after --hdr-len.\n");
        return -1;
      }
      hdr_len = atoi(argv[++i]);
    }

    if ( strncmp(argv[i], "--print", 7) == 0 ) {
      do_print_network = true;
    }
  }
  //configure log4cxx.
  if (log_config_file != "") {
    PropertyConfigurator::configure(log_config_file);
  } else {
    BasicConfigurator::configure();
  }

  if (do_run_test) {
    run_tests<T1, T2>();
  }

#ifdef USE_BDD
  if (!bdd_isrunning()) bdd_init(100000, 10000);
#endif

  auto *N = new NetPlumber<T1, T2>(hdr_len);

  if (do_load_json_files) {
#ifdef GENERIC_PS
    T2 null_filter = T2(hdr_len, BIT_X);
#else
    T2 null_filter[ARRAY_BYTES (hdr_len) / sizeof (array_t)];
    array_init(null_filter, hdr_len, BIT_X);
#endif

    load_netplumber_from_dir<T1, T2>(
        json_files_path,
        N,
#ifdef GENERIC_PS
        &null_filter
#else
        null_filter
#endif
#ifdef PIPE_SLICING
        , hdr_len
#endif
    );
  }

  if (do_load_policy) {
    load_policy_file<T1, T2>(policy_json_file, N, filter);
  }

  if (do_run_server) {
    run_server<T1, T2>(server_address, server_port, N);
  }

  if (do_dump_json_files) {
    N->dump_plumbing_network(dump_files_path);
    N->dump_pipes(dump_files_path);
    N->dump_flow_trees(dump_files_path, false);
#ifdef PIPE_SLICING
    N->dump_slices(dump_files_path);
#endif
    printf("Dumped the plumbing network to %s/\n", dump_files_path.c_str());
  }

  if (do_print_network) {
    N->print_plumbing_network();
  }

  if (!do_run_server) {
    struct rusage usage;
    getrusage(RUSAGE_SELF, &usage);

    printf("Maximum RSS Memory consumption before exiting: %ld KB\n", usage.ru_maxrss);

    printf("Done! Cleaning up the NetPlumber\n");
    delete N;
  }

  LogManager::shutdown();

  return 0;
}


int main(int argc, char* argv[]) {
#ifdef GENERIC_PS
#ifdef USE_BDD
  if (bdd_init(1000000, 10000) != 0) fprintf(stderr, "failed to intialize bdd package with %d nodes and a cache size of %d\n", 1000000, 10000);
  if (bdd_setmaxincrease(10000000) < 0) fprintf(stderr, "failed to increase maximum node size to %d\n", 10000000);

  bdd_setvarnum(8);
  BDDPacketSet::init_result_buffer();
  int ret = typed_main<BDDPacketSet, BDDPacketSet>(argc, argv);
  BDDPacketSet::destroy_result_buffer();
  if (bdd_isrunning()) bdd_done();
  return ret;
#else
  return typed_main<HeaderspacePacketSet, ArrayPacketSet>(argc, argv);
#endif
#else
  return typed_main<hs, array_t>(argc, argv);
#endif
}

