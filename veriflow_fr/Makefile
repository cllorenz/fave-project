# VeriFlow-FR (VERIFLOW_PLAN.md). D3: C++17, standard library only in the
# engine, NetPlumber's compiler and -O3; CppUnit for the tests only.
#
#   make            the engine library and the test runner
#   make test       run the tests
#   make sanitize   the tests under ASan + UBSan (D3 condition 5)

CXX      ?= g++
CXXSTD   := -std=c++17
WARN     := -Wall -Wextra -Wpedantic
OPT      ?= -O3
EXTRA    ?=
CXXFLAGS := $(CXXSTD) $(WARN) $(OPT) -fPIC $(EXTRA)

SRC      := $(wildcard src/*.cc)
OBJ      := $(SRC:src/%.cc=build/%.o)
TSRC     := $(wildcard test/*.cc)
TOBJ     := $(TSRC:test/%.cc=build/test/%.o)

all: build/libveriflow_fr.a build/veriflow_fr_test

build/%.o: src/%.cc src/veriflow.h src/queries.h
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -c $< -o $@

build/test/%.o: test/%.cc src/veriflow.h src/queries.h test/test_util.h
	@mkdir -p build/test
	$(CXX) $(CXXFLAGS) -c $< -o $@

build/libveriflow_fr.a: $(OBJ)
	ar rcs $@ $^

build/veriflow_fr_test: $(TOBJ) build/libveriflow_fr.a
	$(CXX) $(CXXFLAGS) -o $@ $(TOBJ) build/libveriflow_fr.a -lcppunit

test: build/veriflow_fr_test
	./build/veriflow_fr_test

sanitize:
	$(MAKE) clean
	$(MAKE) test OPT="-O1 -g" EXTRA="-fsanitize=address,undefined -fno-sanitize-recover=all"

clean:
	rm -rf build

.PHONY: all test sanitize clean
