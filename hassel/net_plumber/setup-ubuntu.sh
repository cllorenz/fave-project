#!/bin/bash
sudo apt-get install liblog4cxx10v5
sudo apt-get install liblog4cxx-dev
sudo apt-get install libcppunit-1.14-0
sudo apt-get install libcppunit-dev

git clone https://github.com/jgcoded/BuDDy.git
cd BuDDy
sh configure
make
sudo make install
cd ..
