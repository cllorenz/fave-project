# FaVe - Fast Formal Security Verification

This repo includes the codebase of FaVe.

 - fave/ -> includes the modeling pipeline and a set of management tools
 - hassel/net_plumber/ -> includes the NetPlumber verification backend


## First steps

First, one needs to install some dependencies to compile NetPlumber. The script

    #> hassel/net_plumber/setup-ubuntu.sh

performs the necessary steps on an Ubuntu machine. Afterwards, one needs to switch to

    $> cd hassel/net_plumber/Ubuntu-NetPlumber-Release/

and then compile NetPlumber using

    $> make all

Then, it is quite convenient to link the `net_plumber` binary to some `$PATH` directory like `/usr/bin`.


To set up FaVe one can use the script

    #> fave/setup.sh.

Afterwards, one can test the installation running

    $> PYTHONPATH=fave python2 fave/test/example.sh

Typically, a session comprises of two processes: `aggregator.py` and `net_plumber`. These can be stopped or started using their respective scripts in `fave/scripts`. If one process dies one needs to restart both - first NetPlumber and then FaVe. Logfile are stored in `/tmp/np`.