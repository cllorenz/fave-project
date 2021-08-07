#!/usr/bin/env python2

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

""" This module provides utilities for model reconstruction, rule calculations,
    and port string normalization.
"""

import json

from aggregator_abstract import AbstractAggregator

from netplumber.model import Model
from netplumber.slice import SlicingCommand
from ip6np.packet_filter import PacketFilterModel
from ip6np.snapshot_packet_filter import SnapshotPacketFilterModel, StateCommand
from openflow.switch import SwitchModel, SwitchCommand
from topology.topology import LinksModel, TopologyCommand
from topology.generator import GeneratorModel
from topology.probe import ProbeModel


def model_from_json(j):
    """ Reconstructs a model from a JSON object.

    Keyword arguments:
    j -- a JSON object
    """

    AbstractAggregator.LOGGER.debug('reconstruct model')
    try:
        models = {
            "model" : Model,
            "packet_filter" : PacketFilterModel,
            "snapshot_packet_filter" : SnapshotPacketFilterModel,
            "switch" : SwitchModel,
            "switch_command" : SwitchCommand,
            "state_command" : StateCommand,
            "topology_command" : TopologyCommand,
            "slicing_command" : SlicingCommand,
            "links" : LinksModel,
            "generator" : GeneratorModel,
            "probe" : ProbeModel
        }
        model = models[j["type"]]

    except KeyError:
        AbstractAggregator.LOGGER.error(
            "model type not implemented: %s", j["type"]
        )
        raise Exception("model type not implemented: %s" % j["type"])

    else:
        return model.from_json(j)


def model_from_string(jsons):
    """ Reconstructs a model from a JSON string.

    Keyword arguments:
    jsons -- a json string
    """
    model_from_json(json.loads(jsons))


def calc_port(tab, model, port):
    """ Calculates a port number for a table.

    Keyword arguments:
    tab -- a table id
    model -- the model inheriting the table
    port -- the port index in the table
    """
    try:
        return (tab<<16)+model.port_index(port)
    except KeyError:
        return (tab<<16)+1


def calc_rule_index(r_idx, t_idx=0, n_idx=0):
    """ Calculates the rule index within a table

    Keyword arguments:
    t_idx -- a table index
    r_idx -- a rule index within the table
    n_idx -- an optional index for negation expanded rules
    """

    assert t_idx < 2**32
    assert r_idx < 2**24
    assert n_idx < 2**12

    return (t_idx<<32)+(r_idx<<12)+n_idx


def normalize_port(port):
    """ Normalizes a port's name

    Keyword arguments:
    port -- a port name
    """
    return port.replace('.', '_')
