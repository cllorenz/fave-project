#!/usr/bin/env sh

# initialization ("convert" for upgrade)
#sudo ovsdb-tool create /etc/openvswitch/conf.db /usr/share/openvswitch/vswitch.ovsschema

sudo modprobe openvswitch
sudo mkdir -p /var/run/openvswitch
sudo ovsdb-server --remote=punix:/var/run/openvswitch/db.sock --remote=db:Open_vSwitch,Open_vSwitch,manager_options --pidfile --detach
sudo ovs-vsctl --no-wait init
sudo ovs-vswitchd --pidfile --detach
