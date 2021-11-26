#!/usr/bin/env python2

""" This module benchmarks FaVe with the UP workload.
"""

import os
import logging

from bench.generic_benchmark import GenericBenchmark

class UPBenchmark(GenericBenchmark):
    """ This class provides the UP benchmark.
    """

    def _pre_preparation(self):
        os.system("bash scripts/generate-pgf-ruleset.sh bench/wl_up")
        os.system("bash scripts/generate-host-rulesets.sh bench/wl_up")
        os.system("bash scripts/generate-clients-rulesets.sh bench/wl_up")


if __name__ == "__main__":
    UPBenchmark("bench/wl_up", logger=logging.getLogger("up")).run()


#    serverlist = []
#
#    try:
#        # get hosts from slurm environment variables
#        serverlist = parallel_utils.get_serverlist()
#        print('using slurm nodelist as serverlist')
#    except Exception as e:
#        # slurm environment variables not defined or parsing failed
#        # build default serverlist
#        print(repr(e))
#        print('no slurm nodelist found, using default serverlist')
#        hostname = socket.gethostname()
#        print(hostname)
#        host_ip = socket.gethostbyname(hostname)
#        print(host_ip)
#
#        cur_port = int(os.environ.get('start_port', 44001))
#
#        tds = 1
#        if len(sys.argv) == 2:
#            try:
#                tds = int(sys.argv[1])
#            except Exception as e:
#                print(repr(e))
#
#        for no in range(0,tds):
#            if use_tcp_np:
#                serverlist.append({'host': host_ip, 'port': str(cur_port + no)})
#            else:
#                serverlist.append('/dev/shm/np%d.socket' % no)
#
#        for server in serverlist:
#            if use_tcp_np:
#                sockopt = "-s %s -p %s" % (server['host'], server['port'])
#            else:
#                sockopt = "-u %s" % server
#            print("bash scripts/start_np.sh -l bench/wl_up/np.conf %s" % sockopt)
#            os.system("bash scripts/start_np.sh -l bench/wl_up/np.conf %s" % sockopt)
#
#    print(serverlist)
#
#    if use_tcp_np:
#        aggr_args = [("%s:%s" % (server['host'], server['port'])) for server in serverlist]
#    else:
#        aggr_args = serverlist

#    dumper.main(["-o", os.environ.get('np_flows_output_directory', 'np_dump'), "-a", "-n", "-t"] + (['-u'] if use_unix else []))
#
#    os.system("bash scripts/stop_fave.sh %s" % ("-u" if use_unix else ""))

# XXX: from golombek
#    import test.check_flows as checker
#    checker.main(["-b", "-r", "-c", ";".join(checks), '-d', os.environ['np_flows_output_directory']])
