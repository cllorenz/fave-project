#!/usr/bin/env bash

if [ -f /usr/bin/apt-get ]; then
    sudo apt-get --no-install-recommends install redis-server
    sudo apt-get --no-install-recommends install python3
    sudo apt-get --no-install-recommends install python3-pip
    sudo apt-get --no-install-recommends install python3-lxml
    sudo apt-get --no-install-recommends install python3-setuptools
    sudo apt-get --no-install-recommends install python3-dev
    sudo apt-get --no-install-recommends install python3-numpy
    sudo apt-get --no-install-recommends install python3-redis
    sudo apt-get --no-install-recommends install python3-cherrypy3
    sudo apt-get --no-install-recommends install gringo
    #sudo apt-get --no-install-recommends install minisat
elif [ -f /usr/bin/pacman ]; then
    sudo pacman -S redis
    sudo pacman -S python3
    sudo pacman -S python-redis
    sudo pacman -S python-pip
    sudo pacman -S python-lxml
    sudo pacman -S clingo
    sudo pip3 install pycosat
    sudo pip3 install cherrypy
    sudo pip3 install numpy
    sudo pip3 install yappi
else
    echo "No packet manager found. Abort!"
    return 0
fi

#sudo pip3 install pycosat
#sudo pip3 install numpy
#sudo pip3 install redis
#sudo pip3 install cherrypy
#
wget http://minisat.se/downloads/minisat-2.2.0.tar.gz
tar xfz minisat-2.2.0.tar.gz
cd minisat
export MROOT=`pwd`
cd core
make rs
sudo cp minisat_static /usr/bin/minisat
cd ..
cd ..
rm -rf minisat*
