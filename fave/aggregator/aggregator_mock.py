#!/usr/bin/env python2

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

""" This module offers a mock for the FaVe aggregator.
"""

import socket
import os

from util.aggregator_utils import FAVE_DEFAULT_UNIX

def main():
    """ Starts mocking by accepting all incoming FaVe events.
    """

    try:
        os.unlink(FAVE_DEFAULT_UNIX)
    except OSError:
        if os.path.exists(FAVE_DEFAULT_UNIX):
            raise

    buf_size = 4096

    # open new unix domain socket
    uds = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    uds.bind(FAVE_DEFAULT_UNIX)

    uds.listen(1)

    while True:
        # accept connections on unix domain socket
        try:
            conn = uds.accept()[0]
        except socket.error:
            break

        # receive data from unix domain socket
        nbytes = buf_size
        data = ""
        while nbytes == buf_size:
            tmp = conn.recv(buf_size)
            nbytes = len(tmp)
            data += tmp
        if not data:
            break


if __name__ == "__main__":
    main()
