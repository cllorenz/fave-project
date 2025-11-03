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

#pacman --version 2> /dev/null
#if [ $? -eq 0 ]; then
#    sudo pacman -S python3
#    sudo pacman -S python3-daemon
#    sudo pacman -S python3-pip
#    sudo pacman -S python3-pylint
#    sudo pacman -S inkscape
#    sudo pacman -S python3-coverage
#    sudo pacman -S flex
#    sudo pacman -S bison
#    sudo pacman -S pandoc
##    sudo ln -s /usr/bin/python3-coverage /usr/bin/coverage2
#    sudo pip3 install graphviz
#    sudo pip3 install filelock
#    sudo pip3 install pyparsing
#    sudo pip3 install cachetools
#    sudo pip3 install dd
#    sudo pip3 install pybison
#fi

apt-get --version 2> /dev/null
if [ $? -eq 0 ]; then
    export APT_CONFS="--no-install-recommends -y"
    sudo apt-get $APT_CONFS install apt-utils
    sudo apt-get $APT_CONFS install build-essential
    sudo apt-get $APT_CONFS install wget
    sudo apt-get $APT_CONFS install git
    sudo apt-get $APT_CONFS install python3
    sudo apt-get $APT_CONFS install python3-dev
    sudo apt-get $APT_CONFS install python3-daemon
    sudo apt-get $APT_CONFS install python3-pip
    sudo apt-get $APT_CONFS install python3-venv
    sudo apt-get $APT_CONFS install pylint
    sudo apt-get $APT_CONFS install inkscape
    sudo apt-get $APT_CONFS install python3-coverage
    sudo apt-get $APT_CONFS install flex
    sudo apt-get $APT_CONFS install bison
    sudo apt-get $APT_CONFS install pandoc
    sudo apt-get $APT_CONFS install liblog4cxx15
    sudo apt-get $APT_CONFS install liblog4cxx-dev
    sudo apt-get $APT_CONFS install libcppunit-1.15-0
    sudo apt-get $APT_CONFS install libcppunit-dev

    python3 -m venv ~/.venv
    export PATH="~/.venv/bin:$PATH"

    pip3 install wheel
    pip3 install graphviz
    pip3 install filelock
    pip3 install pyparsing
    pip3 install cachetools
    pip3 install dd
    pip3 install pybison
fi
