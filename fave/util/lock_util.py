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

""" This module provides classes for a pre locked as well as a persistent file
    lock.
"""

import os

from typing import Optional

from filelock import SoftFileLock

class PreLockedFileLock(SoftFileLock):
    """ This class provides a pre locked file lock: constructing it holds the
    lock file (creating it if absent), and `release` removes it.

    It keeps its own descriptor rather than planting one in `filelock`'s
    internals. It once set `self._lock_file_fd`, which `filelock` 3.29 no longer
    reads, so `release()` was a no-op: the dump's `.lock` and an open
    descriptor survived every request (TODO item 53).
    """

    def __init__(self, lock_file: str, timeout: float = -1) -> None:
        super(PreLockedFileLock, self).__init__(lock_file, timeout)

        self._prelocked_fd: Optional[int] = None
        open_mode = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        try:
            self._prelocked_fd = os.open(self.lock_file, open_mode)
        except (IOError, OSError):
            pass


    def release(self, force: bool = True) -> None:
        """ Releases the file lock: closes its descriptor and removes the file.

        :arg bool force:
            Kept for the base class's signature; a pre-held lock has no
            counter, so it is released in every case.
        """
        del force
        if self._prelocked_fd is not None:
            os.close(self._prelocked_fd)
            self._prelocked_fd = None
        try:
            os.remove(self.lock_file)
        except FileNotFoundError:
            pass


class PersistentFileLock(SoftFileLock):
    """ This class provides a persistent file lock.
    """

    def __del__(self) -> None:
        return None
