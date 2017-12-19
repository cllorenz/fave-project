#!/usr/bin/env python2

import socket
import os
import sys

UDS_ADDR = "/tmp/np_aggregator.socket"

class Aggregator(object):
    BUF_SIZE = 4096

    def run(self):
        # open new unix domain socket
        uds = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        uds.bind(UDS_ADDR)

        uds.listen(1)

        while True:
            # accept connections on unix domain socket
            try:
                conn,addr = uds.accept()
            except socket.error:
                break

            # receive data from unix domain socket
            nbytes = Aggregator.BUF_SIZE
            data = ""
            while nbytes == Aggregator.BUF_SIZE:
                tmp = conn.recv(Aggregator.BUF_SIZE)
                nbytes = len(tmp)
                data += tmp
            if not data:
                break


def main(argv):
    aggregator = Aggregator()
    try:
        os.unlink(UDS_ADDR)
    except OSError:
        if os.path.exists(UDS_ADDR):
            raise

    aggregator.run()

if __name__ == "__main__":
    main(sys.argv[1:])
