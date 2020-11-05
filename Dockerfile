# Container for building, testing, and benchmarking FaVe

FROM debian
LABEL Description="This image is used to build, test, and benchmark the FaVe verification system."

ENV APT_CONFS="--no-install-recommends -y"
ENV DIRPATH=/home/fave-code
WORKDIR $DIRPATH

RUN apt-get update
RUN apt-get $APT_CONFS install apt-utils
RUN apt-get $APT_CONFS install build-essential
RUN apt-get $APT_CONFS install wget
RUN apt-get $APT_CONFS install git
RUN apt-get $APT_CONFS install python2
RUN apt-get $APT_CONFS install python2-dev
RUN apt-get $APT_CONFS install python-pip
RUN apt-get $APT_CONFS install python-daemon
RUN apt-get $APT_CONFS install python3-pip
RUN apt-get $APT_CONFS install pylint
RUN apt-get $APT_CONFS install inkscape
RUN apt-get $APT_CONFS install python-coverage
RUN apt-get $APT_CONFS install flex
RUN apt-get $APT_CONFS install bison
RUN apt-get $APT_CONFS install liblog4cxx10v5
RUN apt-get $APT_CONFS install liblog4cxx-dev
RUN apt-get $APT_CONFS install libcppunit-1.14-0
RUN apt-get $APT_CONFS install libcppunit-dev

RUN git clone https://github.com/jgcoded/BuDDy.git && \
    cd BuDDy && \
    sh configure && \
    make && \
    make install && \
    cd ..

RUN pip2 install wheel
RUN pip2 install graphviz
RUN pip2 install filelock
RUN pip2 install pyparsing
RUN pip2 install cachetools
RUN pip2 install dd

RUN wget http://www.cosc.canterbury.ac.nz/greg.ewing/python/Pyrex/Pyrex-0.9.9.tar.gz && \
    tar xfz Pyrex-0.9.9.tar.gz && \
    cd Pyrex-0.9.9 && \
    python2 setup.py install && \
    cd ..

RUN git clone https://github.com/smvv/pybison.git && \
    cd pybison && \
    python2 setup.py install && \
    cd ..

COPY fave-code $DIRPATH/
