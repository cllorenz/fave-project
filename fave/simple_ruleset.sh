ip6tables -P INPUT DROP
ip6tables -P FORWARD DROP
ip6tables -P OUTPUT DROP

ip6tables -A FORWARD -d 2001:db8::1 -j ACCEPT
ip6tables -A FORWARD -d 2001:db8::2 -j ACCEPT

