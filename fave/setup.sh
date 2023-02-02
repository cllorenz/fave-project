#!/usr/bin/env bash

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

pacman --version 2> /dev/null
if [ $? -eq 0 ]; then
    sudo pacman -S python3
    sudo pacman -S python3-daemon
    sudo pacman -S python3-pip
    sudo pacman -S python3-pylint
    sudo pacman -S inkscape
    sudo pacman -S python3-coverage
    sudo pacman -S flex
    sudo pacman -S bison
    sudo pacman -S pandoc
#    sudo ln -s /usr/bin/python3-coverage /usr/bin/coverage2
fi

apt-get --version 2> /dev/null
if [ $? -eq 0 ]; then
    sudo apt-get install python3
    sudo apt-get install python3-dev
    sudo apt-get install python-daemon
    sudo apt-get install python-pip
    sudo apt-get install pylint
    sudo apt-get install inkscape
    sudo apt-get install python-coverage
    sudo apt-get install flex
    sudo apt-get install bison
    sudo apt-get install pandoc
fi

sudo pip3 install graphviz
sudo pip3 install filelock
sudo pip3 install pyparsing
sudo pip3 install cachetools
sudo pip3 install dd
sudo pip3 install pybison

#wget http://www.cosc.canterbury.ac.nz/greg.ewing/python/Pyrex/Pyrex-0.9.9.tar.gz
#tar xfz Pyrex-0.9.9.tar.gz
#cd Pyrex-0.9.9
#2to3 -x import -w -n .
#sudo python3 setup.py install
#cd ..
#rm Pyrex.0.9.9.tar.gz
#sudo rm -rf Pyrex-0.9.9
#
#git clone https://github.com/smvv/pybison.git
#cd pybison
#sudo python3 setup.py install
#cd ..
#sudo rm -rf pybison
