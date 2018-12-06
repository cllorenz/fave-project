#!/usr/bin/env python2

""" This module provides utilities for model reconstruction, rule calculations,
    and port string normalization.
"""

import json

from aggregator_abstract import AbstractAggregator

from netplumber.model import Model
from ip6np.packet_filter import PacketFilterModel
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
            "switch" : SwitchModel,
            "switch_command" : SwitchCommand,
            "topology_command" : TopologyCommand,
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


#@profile_method
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
        return (tab<<16)+model.ports[port]
    except KeyError:
        return (tab<<16)+1


def calc_rule_index(t_idx, r_idx):
    """ Calculates the rule index within a table

    Keyword arguments:
    t_idx -- a table index
    r_idx -- a rule index within the table
    """
    return (t_idx<<16)+r_idx


def normalize_port(port):
    """ Normalizes a port's name

    Keyword arguments:
    port -- a port name
    """
    return port.replace('.', '_')
