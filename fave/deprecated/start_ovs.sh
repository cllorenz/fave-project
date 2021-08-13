#!/usr/bin/env sh

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

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

# initialization ("convert" for upgrade)
#sudo ovsdb-tool create /etc/openvswitch/conf.db /usr/share/openvswitch/vswitch.ovsschema

sudo modprobe openvswitch
sudo mkdir -p /var/run/openvswitch
sudo ovsdb-server --remote=punix:/var/run/openvswitch/db.sock --remote=db:Open_vSwitch,Open_vSwitch,manager_options --pidfile --detach
sudo ovs-vsctl --no-wait init
sudo ovs-vswitchd --pidfile --detach
