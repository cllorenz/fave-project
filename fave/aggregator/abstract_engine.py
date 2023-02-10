#!/usr/bin/env python3

class AbstractVerificationEngine(object):
    def add_generator(self):
        raise NotImplementedError()

    def add_generators_bulk(self):
        raise NotImplementedError()

    def add_link(self):
        raise NotImplementedError()

    def add_links_bulk(self):
        raise NotImplementedError()

    def add_probe(self):
        raise NotImplementedError()

    def add_rules(self):
        raise NotImplementedError()

    def add_slice(self):
        raise NotImplementedError()

    def add_tables(self):
        raise NotImplementedError()

    def add_wiring(self):
        raise NotImplementedError()

    def check_anomalies(self):
        raise NotImplementedError()

    def delete_generator(self):
        raise NotImplementedError()

    def delete_probe(self):
        raise NotImplementedError()

    def del_slice(self):
        raise NotImplementedError()

    def dump_flows(self):
        raise NotImplementedError()

    def dump_flow_trees(self):
        raise NotImplementedError()

    def dump_pipes(self):
        raise NotImplementedError()

    def dump_plumbing_network(self):
        raise NotImplementedError()

    def remove_link(self):
        raise NotImplementedError()

    def stop(self):
        raise NotImplementedError()
