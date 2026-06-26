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

""" This module provides a lazily-initialised global PyBison iptables parser.

Importing this module -- and therefore topology/aggregator_service, which
import PARSER -- must NOT build the PyBison parser or import `bison`: building
it eagerly pulled the native flex/bison dependency into every importer,
breaking the pure-Python `fast` test tier (e.g. test_aggregator, which drives
the aggregator via injection seams and never parses iptables). The parser is
therefore built on first *use* (PARSER.parse(...)), which is the only thing
consumers do with it -- so `import bison` happens only when iptables are
actually parsed (integration/e2e, where PyBison is installed).
"""

from typing import Any


class _LazyParser:
    """ Transparent proxy that constructs the real IP6TablesParser (importing
    `bison`) on first attribute access and forwards everything to it. """

    _parser: Any = None

    @classmethod
    def _instance(cls) -> Any:
        if cls._parser is None:
            from iptables.parser import IP6TablesParser
            cls._parser = IP6TablesParser()
        return cls._parser

    def __getattr__(self, name: str) -> Any:
        # Only reached for attributes not found on the proxy itself (e.g.
        # .parse), so this forwards real parser calls and triggers the build.
        return getattr(_LazyParser._instance(), name)


PARSER: Any = _LazyParser()
