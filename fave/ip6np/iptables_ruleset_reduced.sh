ip6tables -P INPUT DROP
ip6tables -P FORWARD DROP
ip6tables -P OUTPUT DROP

ip6tables -A INPUT -i lo -j ACCEPT

ip6tables -A INPUT -p icmpv6 -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type time-exceeded -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type parameter-problem -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-solicitation -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbour-advertisement -j ACCEPT

ip6tables -A INPUT -p tcp --dport 22 -j ACCEPT
ip6tables -A INPUT -p tcp --dport 80 -j ACCEPT


ip6tables -A OUTPUT -o lo -j ACCEPT
ip6tables -A OUTPUT -p icmpv6 -j ACCEPT

ip6tables -A FORWARD -p icmpv6 --icmpv6-type destination-unreachable -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type packet-too-big -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type ttl-zero-during-transit -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-header-type -j ACCEPT
ip6tables -A FORWARD -p icmpv6 --icmpv6-type unknown-option -j ACCEPT

ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 0 ! --rt-segsleft 0 -j DROP
ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 2 ! --rt-segsleft 1 -j DROP
ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 0 --rt-segsleft 0 -j DROP
ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt --rt-type 2 --rt-segsleft 1 -j DROP
ip6tables -A FORWARD -m ipv6header --header ipv6-route -m rt ! --rt-segsleft 0 -j DROP

ip6tables -A FORWARD -p tcp --dport 80 -j ACCEPT
ip6tables -A FORWARD -p udp --dport 80 -j ACCEPT

