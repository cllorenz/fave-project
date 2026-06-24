#!/usr/bin/env python3

from typing import Any

class AbstractVerificationEngine(object):
    def add_generator(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def add_generators_bulk(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def add_link(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def add_links_bulk(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def add_probe(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def add_rules(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def add_slice(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def add_tables(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def add_wiring(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def check_anomalies(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def delete_generator(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def delete_probe(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def del_slice(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def dump_flows(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def dump_flow_trees(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def dump_pipes(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def dump_plumbing_network(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def remove_link(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def stop(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()
