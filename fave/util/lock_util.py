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
            lock_file_fd = os.open(self._lock_file, open_mode)
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
