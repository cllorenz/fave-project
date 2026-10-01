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
    # Minimal LaTeX for pandoc -> PDF reports (`pandoc report.md -o report.pdf`
    # needs pdflatex). The generated report is plain markdown (headings, lists,
    # inline code; no tables/images/math), so texlive-latex-extra is omitted.
    # lmodern.sty is needed by pandoc's default template and is only
    # *recommended* by texlive-fonts-recommended, so install it explicitly
    # (otherwise --no-install-recommends skips it).
    sudo apt-get $APT_CONFS install texlive-latex-base
    sudo apt-get $APT_CONFS install texlive-latex-recommended
    sudo apt-get $APT_CONFS install texlive-fonts-recommended
    sudo apt-get $APT_CONFS install lmodern
    sudo apt-get $APT_CONFS install liblog4cxx15
    sudo apt-get $APT_CONFS install liblog4cxx-dev
    sudo apt-get $APT_CONFS install libcppunit-1.15-0
    sudo apt-get $APT_CONFS install libcppunit-dev

    # DELIBERATELY a bare `python3`, and the one exception to the
    # `PYTHON="${PYTHON:-python3}"` rule every other script in this repo follows:
    # this line CREATES the venv, so it must run the system interpreter. Honouring
    # $PYTHON here would let an already-resolved venv build a venv of itself.
    python3 -m venv "$HOME/.venv"

    # Address the venv's pip BY PATH rather than by putting it on $PATH.
    # This used to read `export PATH="~/.venv/bin:$PATH"`, and bash performs no
    # tilde expansion inside double quotes -- so the entry was the literal string
    # `~/.venv/bin`, a directory that does not exist, and every `pip3` below ran
    # the SYSTEM interpreter's pip instead. On Ubuntu 24.04 that now fails outright
    # with `error: externally-managed-environment`, so the documented setup path
    # installed none of what it lists. Fixed 2026-10-01 (TODO item 35).
    VENV_PIP="$HOME/.venv/bin/pip"
    "$VENV_PIP" install wheel

    # ONE list, not two. These seven used to be spelled out here and had already
    # drifted from requirements.txt in both directions (this list had no pytest,
    # no coverage, no mypy; that file has no pybison). requirements.txt is the
    # wheel-only set every tier needs; the native extras below are its documented
    # exceptions, and the reasons live in that file's header.
    "$VENV_PIP" install -r "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/requirements.txt"

    # pybison MUST be built from source: the prebuilt cp312 wheel segfaults at
    # runtime inside BisonParser.__init__ (see the Dockerfile). `--no-binary :all:`
    # applies to every package in its own pip command, which is why this is a line
    # of its own rather than appended above.
    "$VENV_PIP" install --no-binary :all: pybison==0.6.4
    # JPype1 drives the APKeep/NDD backends; pycosat is ad6's in-process SAT solver
    # and ships no wheel (hence python3-dev, installed above).
    "$VENV_PIP" install JPype1==1.7.1 pycosat==0.6.6
fi
