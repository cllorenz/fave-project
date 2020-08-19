#!/usr/bin/env bash

FFFUU_OUT=tum.log
FAVE_IN=tum-ruleset

echo "iptables -P FORWARD DROP" > $FAVE_IN
grep -E "^\(-.*\)$" $FFFUU_OUT | \
  tr -d '\(\)' | \
  sed 's/ --dpts \[1:65535\]//g' | \
  sed 's/ --dpts \[1024:65535\]//g' | \
  sed -r 's/--dpts \[([[:digit:]]{1,5})\]/--dport \1/g' | \
  sed -r 's/--dpts \[([[:digit:]]{1,5}:[[:digit:]]{1,5})\]/--dports \1/g' | \
  sed -r 's/([[:digit:]]{1,3}(\.[[:digit:]]{1,3}){3}(\/[[:digit:]]{1,2})?),/\1/g' | \
  sed 's/\],//g' | \
  sed -r 's/(NEW|UNTRACKED|icmp|[[:digit:]]{1,5}),/\1/g' | \
  sed 's/, /,/g' | \
  tr -d '\[\]' | \
  sed 's/TCP_//g' | \
  sed 's/^/iptables -A FORWARD /' >> $FAVE_IN
