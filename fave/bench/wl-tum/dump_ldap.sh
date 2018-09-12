#!/bin/bash

#not exported
#  description

echo ldapoptions: $@ >&2

# $@ - eigene Argumente
# -b <searchbase> - spezifiziert eine eigene Suchbasis
#    cn=<common>  - Common Name
#    ou=<orgunit> - Organizational Unit
#    dc=<domcomp> - Domain Component
#    dn=<distname>- Distinguished Name
# Quellen:
# https://stackoverflow.com/questions/18756688/what-are-cn-ou-dc-in-an-ldap-search
# https://en.wikipedia.org/wiki/LDAP_Data_Interchange_Format

ldapsearch $@ -b "ou=machines,dc=net,dc=in,dc=tum,dc=de" cn ipHostNumber macAddress NetInTumIp6 NetInTumBootmode NetInTumPf NetInTumAdditionalHostName

ldapsearch $@ -b "ou=vlans,dc=net,dc=in,dc=tum,dc=de" objectClass NetInTumVlan NetInTumIpPrefix NetInTumAdditionalName NetInTumPf

ldapsearch $@ -b "ou=pfgroups,dc=net,dc=in,dc=tum,dc=de" cn NetInTumPfGroupMember


