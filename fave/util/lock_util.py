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

from filelock import SoftFileLock

class PreLockedFileLock(SoftFileLock):
    """ This class provides a pre locked file lock.
    """

    def __init__(self, lock_file, timeout=-1):
        super(PreLockedFileLock, self).__init__(lock_file, timeout)

        open_mode = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        try:
            lock_file_fd = os.open(self.lock_file, open_mode)
        except (IOError, OSError):
            pass
        else:
            self._lock_file_fd = lock_file_fd


    def release(self, force=True):
        """ Releases the file lock.

        :arg bool force:
            If true, the lock counter is ignored and the lock is released in
            every case.
        """
        return super(PreLockedFileLock, self).release(force)


class PersistentFileLock(SoftFileLock):
    """ This class provides a persistent file lock.
    """

    def __del__(self):
        return None
