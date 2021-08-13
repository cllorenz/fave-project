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

NPADDR=127.0.0.1
NPPORT=1234

TMPDIR=/tmp/np
mkdir -p $TMPDIR

echo "start linter tests..."
bash test/lint_test.sh

echo "start unit tests..."
PYTHONPATH=. python2-coverage run test/unit_tests.py
python2-coverage report

echo -n "start netplumber tests..."
net_plumber --test
echo "ok"

echo -n "regressions... "
PYTHONPATH=. python2 test/test_rpc.py
echo "ok"

echo "example network..."
bash examples/example.sh
