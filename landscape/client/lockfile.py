import errno
import os

from twisted.python import lockfile


def patch_lockfile():
    if lockfile.FilesystemLock is PatchedFilesystemLock:
        return
    lockfile.FilesystemLock = PatchedFilesystemLock


class PatchedFilesystemLock(lockfile.FilesystemLock):
    """
    Patched Twisted's FilesystemLock.lock to handle PermissionError
    when trying to lock.
    """

    def lock(self):
        try:
            return super(PatchedFilesystemLock, self).lock()
        except OSError as e:
            if e.errno != errno.EPERM:
                raise
            # XXX Ideally, twisted would name the process and check if
            # processes match the expected name before killing them.
            # Landscape-client runs as a separate user, so this issue should be
            # mitigated, though it does get permission errors trying to kill a
            # recycled PID. (LP: #1870087)
            #
            # Workaround is to remove the current lock file on such error and
            # then retry locking.
            os.remove(self.name)
            return super(PatchedFilesystemLock, self).lock()
