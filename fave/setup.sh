#!/usr/bin/env bash

pacman --version 2> /dev/null
if [ $? -eq 0 ]; then
    sudo pacman -S python2-daemon
    sudo pacman -S python2-pip
    sudo pacman -S python2-pylint
    sudo pacman -S inkscape
    sudo pacman -S python2-coverage
    sudo ln -s /usr/bin/python2-coverage /usr/bin/coverage2
fi

apt-get --version 2> /dev/null
if [ $? -eq 0 ]; then
    sudo apt-get install python-daemon
    sudo apt-get install python-pip
    sudo apt-get install pylint
    sudo apt-get install inkscape
    sudo apt-get install python-coverage
fi

sudo pip2 install antlr4-python2-runtime
sudo pip2 install graphviz
