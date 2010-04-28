import fcntl
import time
import os


class LockError(Exception):
    """Raised when unable to lock a file."""


def lock_path(path, timeout=0):
    fd = os.open(path, os.O_CREAT)
    flags = fcntl.fcntl(fd, fcntl.F_GETFD, 0)
    flags |= fcntl.FD_CLOEXEC
    fcntl.fcntl(fd, fcntl.F_SETFD, flags)

    started = time.time()

    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            if started < time.time() - timeout:
                raise LockError("Couldn't obtain lock")
        else:
            break
        time.sleep(0.1)

    def unlock_path():
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    return unlock_path
