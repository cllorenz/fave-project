# Container for building, testing, and benchmarking FaVe

FROM ubuntu:24.04
LABEL Description="This image is used to build, test, and benchmark the FaVe verification system."

# --- Validated environment provenance (APKEEP_NDD_PLAN.md Part 1.2) ----------
# The APKeep-backend performance numbers are only reproducible on the toolchain
# they were measured on. apt point-releases roll forward (a hard `=version` pin
# breaks `apt-get install` once superseded), so instead of pinning we RECORD the
# exact versions the frozen BDD baseline was validated against. On a drift, the
# numbers must be re-measured before they are trusted (see Part 1.4).
#   ubuntu base            : 24.04
#   openjdk-11-jdk-headless: 11.0.31+11-1ubuntu1~24.04.2
#   maven                  : 3.8.7-2
#   bison                  : 2:3.8.2+dfsg-1build2
#   flex                   : 2.6.4-8.2build1
#   m4                     : 1.4.19-4build1
#   python3-dev            : 3.12.3-0ubuntu2.1
#   vendored JDD jar       : 111 (apkeep/local-maven-repo/.../JDD-111.jar, in-tree)
#   cadical                : 1.7.4-1                    (advisory, encoding bench only)
#   cryptominisat          : 5.11.15+dfsg1-1.1build1    (advisory, encoding bench only)
# Python deps are hard-pinned below (pure-Python -> stable across mirrors).
# -----------------------------------------------------------------------------

ENV APT_CONFS="--no-install-recommends -y"
ENV DIRPATH=/home/fave-code
WORKDIR $DIRPATH

RUN apt-get update
RUN apt-get $APT_CONFS install apt-utils
RUN apt-get $APT_CONFS install build-essential
RUN apt-get $APT_CONFS install wget
RUN apt-get $APT_CONFS install git
RUN apt-get $APT_CONFS install python3
RUN apt-get $APT_CONFS install python3-dev
RUN apt-get $APT_CONFS install python3-daemon
RUN apt-get $APT_CONFS install python3-pip
RUN apt-get $APT_CONFS install python3-venv
RUN apt-get $APT_CONFS install pylint
RUN apt-get $APT_CONFS install inkscape
RUN apt-get $APT_CONFS install pandoc
# Minimal LaTeX for pandoc -> PDF reports (plain markdown: no tables/images/math,
# so texlive-latex-extra is intentionally omitted).
RUN apt-get $APT_CONFS install texlive-latex-base
RUN apt-get $APT_CONFS install texlive-latex-recommended
RUN apt-get $APT_CONFS install texlive-fonts-recommended
# lmodern.sty is needed by pandoc's default template; it is a standalone package
# only *recommended* by texlive-fonts-recommended, so install it explicitly.
RUN apt-get $APT_CONFS install lmodern
RUN apt-get $APT_CONFS install python3-coverage
RUN apt-get $APT_CONFS install flex
RUN apt-get $APT_CONFS install bison
# m4 is bison's runtime skeleton processor: pybison shells out to `bison` at
# import time, which invokes `m4`. It is normally pulled in transitively, but a
# minimal image (or a container reset) can lack it, and then pybison segfaults
# with no obvious cause -- so pin it explicitly as a first-class dependency.
RUN apt-get $APT_CONFS install m4
# APKeep backend (apkeep/): JDK 11 + Maven to build/run it in the integration tier.
RUN apt-get $APT_CONFS install openjdk-11-jdk-headless
RUN apt-get $APT_CONFS install maven
# libnetplumber binding (net_plumber/python): pybind11 headers (python3-dev above).
RUN apt-get $APT_CONFS install pybind11-dev
RUN apt-get $APT_CONFS install liblog4cxx15
RUN apt-get $APT_CONFS install liblog4cxx-dev
RUN apt-get $APT_CONFS install libcppunit-1.15-0
RUN apt-get $APT_CONFS install libcppunit-dev
# ad6 backend (ad6/): SAT solver binaries the solver adapters shell out to
# (src/solver/minisat.py, src/solver/clasp.py). pycosat (below) is the
# in-process default and needs no binary; minisat/clasp are the sensitivity-
# check solvers (AD6_PLAN.md §2.4).
RUN apt-get $APT_CONFS install minisat
RUN apt-get $APT_CONFS install clasp
# ad6 encoding microbenchmark harness (ad6_encoding_bench/, AD6_ENCODING_PLAN.md §3):
# the modern CDCL engines Axis 0 times ad6's own unmodified DIMACS through, and that
# Axis 1 uses for its equisatisfiability self-check between ad6's naive CNF converter
# and a standard Tseitin one. ADVISORY, and deliberately so: no ./test.sh tier needs
# them, so `./test.sh doctor` reports them as [warn] and does NOT fail on their absence
# (see apt_advisory() there). Declared here anyway because the alternative is what
# actually happened -- a container reset removed both, doctor had no opinion about them
# because they were not declared, and Axis 0 was left silently unrunnable until someone
# went looking (AD6_ENCODING_PLAN.md §3.1a).
RUN apt-get $APT_CONFS install cadical
RUN apt-get $APT_CONFS install cryptominisat

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip3 install wheel
RUN pip3 install graphviz==0.21
RUN pip3 install filelock==3.29.4
RUN pip3 install pyparsing==3.3.2
RUN pip3 install cachetools==7.1.4
RUN pip3 install dd==0.6.0
# pybison is a NATIVE build (needs flex/bison/m4 above); pin it so the parser it
# compiles at runtime is reproducible. --no-binary is load-bearing, not
# belt-and-braces: PyPI now ships a prebuilt cp312 manylinux wheel, and pip
# prefers it by default, but that wheel SEGFAULTS at runtime in
# BisonParser.__init__ (via fave/iptables/parser_singleton.py) and takes the
# whole pytest process down with it. Built from source against this image's own
# flex/bison it works. Keep --no-binary on any pybison version bump.
RUN pip3 install --no-binary :all: pybison==0.6.4
# JPype1 drives the APKeep backend in-process (fave/apkeep/lib_apkeep.py). Pinned:
# the JVM+pybison combo is what crashed after the 2026-08-17 container reset, so
# the exact backend-binding version is load-bearing for reproducible timings.
RUN pip3 install JPype1==1.7.1
# ad6 backend (ad6/): lxml (Kripke/SAT-instance XML), yappi (profiling, main.py
# --profile), pycosat (default in-process SAT solver, native build needs
# python3-dev above). python-sat (PySAT) drives fave_bridge.py's persistent
# incremental-solving session (src/solver/incremental.py, AD6_PLAN.md §6 /
# AD6_ENCODING_PLAN.md §§3.4-3.10) via Minisat22's real native incremental
# library API -- ~100-490x faster than the old per-query architecture on
# real benchmarks. Only ever ships "dev"-tagged releases on PyPI; that is
# this package's normal versioning scheme, not a pin onto an unstable build.
RUN pip3 install lxml==6.1.2
RUN pip3 install yappi==1.7.6
RUN pip3 install pycosat==0.6.6
RUN pip3 install python-sat==1.9.dev15

COPY . $DIRPATH/

# Build with -fPIC so the same objects link both the net_plumber executable and
# the libnetplumber shared module; then build the binding (LIBNP_ASSUME_PIC=1
# reuses these PIC objects instead of rebuilding).
RUN cd net_plumber/build && \
    make DEBUG_FLAGS=-fPIC all && \
    make install && \
    cd ../.. && \
    LIBNP_ASSUME_PIC=1 bash net_plumber/python/build_libnetplumber.sh

ENV PYTHONPATH=$DIRPATH/fave
RUN python3 fave/test/unit_tests.py

RUN cd fave && \
    bash examples/example.sh && \
    cd ..

RUN cd fave && \
    python3 bench/wl_example/benchmark.py \
    cd ..

RUN cd fave && \
    python3 bench/wl_ifi/benchmark.py \
    cd ..
