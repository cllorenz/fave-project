# Container for building, testing, and benchmarking FaVe

FROM ubuntu:24.04
LABEL Description="This image is used to build, test, and benchmark the FaVe verification system."

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
RUN apt-get $APT_CONFS install python3-coverage
RUN apt-get $APT_CONFS install flex
RUN apt-get $APT_CONFS install bison
RUN apt-get $APT_CONFS install liblog4cxx15
RUN apt-get $APT_CONFS install liblog4cxx-dev
RUN apt-get $APT_CONFS install libcppunit-1.15-0
RUN apt-get $APT_CONFS install libcppunit-dev

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip3 install wheel
RUN pip3 install graphviz
RUN pip3 install filelock
RUN pip3 install pyparsing
RUN pip3 install cachetools
RUN pip3 install dd
RUN pip3 install pybison

COPY . $DIRPATH/

RUN cd net_plumber/build && \
    make all && \
    make install && \
    cd ../..

ENV PYTHONPATH=$DIRPATH/fave
RUN python3 fave/test/unit_tests.py

#RUN bash fave/example/example.sh
