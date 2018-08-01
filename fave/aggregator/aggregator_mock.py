#!/usr/bin/env python2

""" This module offers a mock for the FaVe aggregator.
"""

import socket
import os

from fave.aggregator.aggregator_commons import UDS_ADDR

def main():
    """ Starts mocking by accepting all incoming FaVe events.
    """

    try:
        os.unlink(UDS_ADDR)
    except OSError:
        if os.path.exists(UDS_ADDR):
            raise

    buf_size = 4096

    # open new unix domain socket
    uds = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    uds.bind(UDS_ADDR)

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
