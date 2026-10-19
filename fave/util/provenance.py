#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2026 Claas Lorenz <claas_lorenz@genua.de>

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

""" What a measured cell ran: the engines' build artifacts and the inputs, by
sha256 (INCREMENTAL_PLAN.md D17.7, as V5's cells and `ARTIFACTS.txt` stamp
them). A hash that changes between cells of one campaign is a finding: a
worktree once swapped the main tree's jar mid-campaign. """

import hashlib
import json
import os
from typing import Any, Dict, Iterable, List, Optional


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as raw:
        for block in iter(lambda: raw.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _hashed(paths: Iterable[Optional[str]]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for path in paths:
        if path:
            out[os.path.relpath(path)] = sha256_file(path) if os.path.isfile(path) else None
    return out


def artifact_paths() -> List[Optional[str]]:
    """ The engines' built artifacts, as this process would load them: the
    APKeep and NDD jars, `libnetplumber` and `libveriflow_fr`. Imported
    lazily, so a missing native library is a None, not an error. """
    paths: List[Optional[str]] = []
    try:
        from apkeep import lib_apkeep
        paths += [lib_apkeep._APKEEP_JAR, lib_apkeep._NDD_JAR]   # pylint: disable=protected-access
    except ImportError:
        pass
    for module, attr in (('netplumber.lib_adapter', 'libnetplumber'),
                         ('veriflow.adapter', 'libveriflow_fr')):
        try:
            lib = getattr(__import__(module, fromlist=[attr]), attr, None)
        except ImportError:
            lib = None
        paths.append(getattr(lib, '__file__', None))
    return paths


def artifacts() -> Dict[str, Optional[str]]:
    """ relative path -> sha256 of every engine artifact present. """
    return _hashed(artifact_paths())


def input_paths(prefix: str, names: Dict[str, str], checks: Optional[str]) -> List[str]:
    """ A workload's inputs: its role files (`names`: role -> file name), its
    check set, and every device configuration its topology names. """
    paths = [os.path.join(prefix, name) for name in names.values()]
    if checks:
        paths.append(checks)
    try:
        with open(os.path.join(prefix, names['topology'])) as raw:
            devices = json.load(raw).get('devices', [])
    except (OSError, ValueError, KeyError):
        devices = []
    for device in devices:
        for item in device[2:]:
            if isinstance(item, str) and os.path.isfile(item):
                paths.append(item)
    return sorted(set(paths))


def inputs(prefix: str, names: Dict[str, str], checks: Optional[str]) -> Dict[str, Optional[str]]:
    """ relative path -> sha256 of every input of the workload. """
    return _hashed(input_paths(prefix, names, checks))


def engine_stamps(configuration: Dict[str, Any]) -> Dict[str, Any]:
    """ V5's top-level stamps from an engine's configuration stamp: `impl`,
    `upstream`, the remaining options, and the JVM heap cap. """
    options = {k: v for k, v in configuration.items() if k not in ('impl', 'upstream')}
    return {'impl': configuration.get('impl'), 'upstream': configuration.get('upstream'),
            'engine_options': options, 'jvm_xmx': os.environ.get('FAVE_JVM_XMX')}
