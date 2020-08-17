#!/usr/bin/env bash

pacman --version 2> /dev/null
if [ $? -eq 0 ]; then
    sudo pacman -S python2-daemon
    sudo pacman -S python2-pip
    sudo pacman -S python2-pylint
    sudo pacman -S inkscape
    sudo pacman -S python2-coverage
    sudo pacman -S flex
    sudo pacman -S bison
    sudo ln -s /usr/bin/python2-coverage /usr/bin/coverage2
fi

apt-get --version 2> /dev/null
if [ $? -eq 0 ]; then
    sudo apt-get install python2
    sudo apt-get install python2-dev
    sudo apt-get install python2-pip
    sudo apt-get install python-daemon
    sudo apt-get install python-pip
    sudo apt-get install pylint
    sudo apt-get install inkscape
    sudo apt-get install python-coverage
    sudo apt-get install flex
    sudo apt-get install bison
fi

sudo pip2 install antlr4-python2-runtime
sudo pip2 install graphviz
sudo pip2 install filelock
sudo pip2 install pyparsing
sudo pip2 install cachetools

wget http://www.cosc.canterbury.ac.nz/greg.ewing/python/Pyrex/Pyrex-0.9.9.tar.gz
tar xfz Pyrex-0.9.9.tar.gz
cd Pyrex-0.9.9
sudo python2 setup.py install
cd ..

git clone https://github.com/smvv/pybison.git
cd pybison
sudo python2 setup.py install
cd ..
