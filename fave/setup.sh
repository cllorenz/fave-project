#!/usr/bin/env bash

pacman --version
if [ $? -eq 0 ]; then
    sudo pacman -S python2-daemon
    sudo pacman -S python2-pip
    sudo pacman -S python2-pylint
    sudo pacman -S inkscape
    sudo pacman -S python2-coverage
fi

apt-get --version
if [ $? -eq 0 ]; then
    sudo apt-get install python-daemon
    sudo apt-get install python-pip
    sudo apt-get install pylint
    sudo apt-get install inkscape
    sudo apt-get install python-coverage
fi

sudo pip2 install antlr4-python2-runtime
sudo pip2 install graphviz
