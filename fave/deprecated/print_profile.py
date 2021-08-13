#!/usr/bin/env python2

import pstats
p = pstats.Stats('aggregator.profile')
p.sort_stats('cumulative').print_stats()
