#!/usr/bin/env python3

from typing import Any, Dict, Optional, Set, Tuple

#: TODO item 31's provenance vocabulary -- WHOSE CODE produced a number. It is
#: a separate axis from the accommodations: one says whose code runs, the other
#: how much of the workload the tool supports as published, and a cell can be
#: the authors' code with a FaVe extension.
#:
#:   `authors`            the authors' code, unmodified. No backend today.
#:   `authors+fave`       the authors' code with FaVe changes, stated in a
#:                        change record and stamped with the upstream import.
#:   `first-party`        the tool's author is FaVe's author. Declared BECAUSE
#:                        the comparison's author is also the tool's.
#:   `reimpl-literature`  our implementation from the publications alone, under
#:                        a clean-room protocol. A slow number from one of these
#:                        is ours, never the original tool's.
IMPLS = ('authors', 'authors+fave', 'first-party', 'reimpl-literature')


class UpdateRefused(NotImplementedError):
    """ A model change this engine cannot apply to the model it has built.

    Raised instead of accepting the change and answering from the model as it
    was. An adapter that buffers the model and builds once (APKeep), or whose
    deletion only edits bookkeeping the built model never reads, would otherwise
    keep returning the PRE-update verdict with no error -- a wrong answer that
    looks like a right one, and the first thing TODO item 31's incremental axis
    would have measured. Refused, never approximated: the aggregator reports it
    through the request's barrier, so the caller sees it.
    """


class AbstractVerificationEngine(object):
    """ What every verification backend must answer, including WHOSE it is.

    **Provenance is declared here, by the engine, and never typed by hand into
    a table** (TODO item 31: *"the value comes from the backend ... so a table
    cannot mislabel a row"*). Until 2026-10-02 only VeriFlow-FR stamped one, so
    `bench/cell_run.py` recorded `impl: null` for three of the four backends
    and said so; that is what these two attributes close.

    A subclass sets `IMPL` to one of `IMPLS` and, where it is a fork, `UPSTREAM`
    to the import it is a fork OF -- which is the other half of what makes an
    `authors+fave` cell checkable, since without it the claim names no baseline.
    `test/test_backend_provenance.py` fails if a concrete engine declares
    neither.
    """

    #: One of `IMPLS`; None only on this abstract base.
    IMPL: Optional[str] = None

    #: The upstream commit this is a fork of, for `authors+fave`. None for a
    #: first-party or clean-room engine, which are forks of nothing.
    UPSTREAM: Optional[str] = None

    def provenance(self) -> Dict[str, Any]:
        """ Whose code this is. Merged into every `configuration_stamp`. """
        stamp: Dict[str, Any] = {'impl': self.IMPL}
        if self.UPSTREAM:
            stamp['upstream'] = self.UPSTREAM
        return stamp

    def configuration_stamp(self) -> Dict[str, Any]:
        """ The measurement-affecting choices behind this engine's answers.

        The aggregator logs it next to the backend name, and `cell_run.py`
        reads it back out of that log into the result cell. An engine with no
        configuration to declare still reports its provenance, which is why
        this has a default rather than being abstract.
        """
        return self.provenance()

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

    # --- incremental updates (INCREMENTAL_PLAN.md §6.2) ----------------------
    #
    # Applied directly to a BUILT engine, bypassing the aggregator. A rule is
    # identified by (node, tid, idx); a modify is a delete followed by an
    # insert. The defaults are the SOUND ones: an engine that has not
    # implemented an update refuses it, and an engine that cannot say what an
    # update affected says so (None), which makes the caller re-verify every
    # check -- never fewer.

    def insert_rule(self, rule: Any) -> None:
        """ Insert one rule into a table the built model already has. """
        raise UpdateRefused(
            "%s: insert_rule is not implemented" % type(self).__name__)

    def delete_rule(self, node: str, tid: str, idx: int) -> None:
        """ Delete the rule (node, tid, idx) from the built model. """
        raise UpdateRefused(
            "%s: delete_rule is not implemented" % type(self).__name__)

    def set_link(self, sport: str, dport: str, up: bool) -> None:
        """ Bring the link sport -> dport (FaVe port names) up or down. """
        raise UpdateRefused(
            "%s: set_link is not implemented" % type(self).__name__)

    def track_affected(self, on: bool) -> None:
        """ Start or stop recording what updates affect. A no-op for an
        engine that cannot record it; `take_affected` then returns None. """

    def take_affected(self) -> Optional[Set[Tuple[str, str]]]:
        """ The (source, probe) NAME pairs whose compliance checks the updates
        since the last call can have changed, then forget them. None means
        "unknown": every check must be re-verified. """
        return None

    def stop(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()
