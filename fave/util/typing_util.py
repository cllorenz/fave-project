#!/usr/bin/env python3

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

""" Shared typing aliases for the FaVe type-checking migration (TODO item 6).
"""

from typing import Any, Dict

# A decoded JSON object. The model classes' from_json factories accept either a
# JSON string or an already-decoded object; the public parameter type is
# therefore Union[str, JSONDict] (Optional where an empty value is allowed).
# Promote to TypedDict per record later if per-field precision is wanted.
JSONDict = Dict[str, Any]
