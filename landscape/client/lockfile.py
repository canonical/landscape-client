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
        # XXX Twisted assumes PIDs don't get reused, which is incorrect.
        # As such, we pre-check that any existing lock file isn't
        # associated to a live process, and that any associated
        # process is from landscape. Otherwise, clean up the lock file,
        # considering it to be locked to a recycled PID.
        #
        # Although looking for the process name may seem fragile, it's the
        # most acurate info we have since:
        # * some process run as root, so the UID is not a reference
        # * process may not be spawned by systemd, so cgroups are not reliable
        # * python executable is not a reference
        clean = True
        try:
            pid = os.readlink(self.name)
            ps_name = get_process_name(int(pid))
            if not ps_name.startswith("landscape"):
                os.remove(self.name)
                clean = False
        except Exception:
            # We can't figure the lock state, let FilesystemLock figure it
            # out normally.
            pass

        result = super(PatchedFilesystemLock, self).lock()
        self.clean = self.clean and clean
        return result


def get_process_name(pid):
    """Return a process name from a pid."""
    stat_path = "/proc/{}/stat".format(pid)
    with open(stat_path) as stat_file:
        stat = stat_file.read()
    return stat.partition("(")[2].rpartition(")")[0]
