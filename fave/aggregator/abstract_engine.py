#!/usr/bin/env python3

class AbstractVerificationEngine(object):
    def add_generator(self, *args, **kwargs):
        raise NotImplementedError()

    def add_generators_bulk(self, *args, **kwargs):
        raise NotImplementedError()

    def add_link(self, *args, **kwargs):
        raise NotImplementedError()

    def add_links_bulk(self, *args, **kwargs):
        raise NotImplementedError()

    def add_probe(self, *args, **kwargs):
        raise NotImplementedError()

    def add_rules(self, *args, **kwargs):
        raise NotImplementedError()

    def add_slice(self, *args, **kwargs):
        raise NotImplementedError()

    def add_tables(self, *args, **kwargs):
        raise NotImplementedError()

    def add_wiring(self, *args, **kwargs):
        raise NotImplementedError()

    def check_anomalies(self, *args, **kwargs):
        raise NotImplementedError()

    def delete_generator(self, *args, **kwargs):
        raise NotImplementedError()

    def delete_probe(self, *args, **kwargs):
        raise NotImplementedError()

    def del_slice(self, *args, **kwargs):
        raise NotImplementedError()

    def dump_flows(self, *args, **kwargs):
        raise NotImplementedError()

    def dump_flow_trees(self, *args, **kwargs):
        raise NotImplementedError()

    def dump_pipes(self, *args, **kwargs):
        raise NotImplementedError()

    def dump_plumbing_network(self, *args, **kwargs):
        raise NotImplementedError()

    def remove_link(self, *args, **kwargs):
        raise NotImplementedError()

    def stop(self, *args, **kwargs):
        raise NotImplementedError()
