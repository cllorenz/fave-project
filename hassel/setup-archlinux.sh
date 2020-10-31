#!/bin/bash

# make, gcc, etc.
sudo pacman -S base-devel

# lib4cxx
wget https://aur.archlinux.org/cgit/aur.git/snapshot/log4cxx.tar.gz
tar xfvz log4cxx.tar.gz
cd log4cxx
makepkg -si

cd ..
rm -rf log4cxx
rm log4cxx.tar.gz

# cppunit
sudo pacman -S cppunit
