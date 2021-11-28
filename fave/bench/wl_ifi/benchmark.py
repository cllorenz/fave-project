#!/usr/bin/env python2

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

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

""" This module benchmarks FaVe using the IFI workload.
"""

import os
import logging

from bench.generic_benchmark import GenericBenchmark


class IFIBenchmark(GenericBenchmark):
    """ This class provides the IFI benchmark.
    """

    def _pre_preparation(self):
        os.system("python2 bench/wl_ifi/cisco_to_inventory.py")



if __name__ == '__main__':
    IFIBenchmark("bench/wl_ifi", logger=logging.getLogger('ifi')).run()


#        serverlist = []
#
#        try:
#            # get hosts from slurm environment variables
#            serverlist = parallel_utils.get_serverlist()
#        except Exception as e:
#            # slurm environment variables not defined or parsing failed
#            # build default serverlist
#            hostname = socket.gethostname()
#            host_ip = socket.gethostbyname(hostname)
#
#            cur_port = 44001
#
#            for no in range(0,tds):
#                serverlist.append({'host': host_ip, 'port': str(cur_port + no)})
#
#            for server in serverlist:
#                sockopt = "-s %s -p %s" % (server['host'], server['port'])
#                os.system("bash scripts/start_np.sh -l bench/wl_ifi/np.conf %s" % sockopt)
#
#        aggr_args = [("%s:%s" % (server['host'], server['port'])) for server in serverlist]
#        os.system(
#            "bash scripts/start_aggr.sh -S %s -u" % ','.join(aggr_args)
#        )

#    import netplumber.dump_np as dumper
#    dumper.main(["-o", os.environ.get('np_flows_output_directory', 'np_dump'), "-a", "-n", "-p", "-f", "-t"] + (['-u'] if use_unix else []))

#    import test.check_flows as checker
#    checker.main(["-b", "-r", "-c", ";".join(checks), '-d', os.environ.get('np_flows_output_directory', 'np_dump')])

#    os.system("rm -f {}/.lock".format(os.environ.get('np_flows_output_directory', 'np_dump')))
