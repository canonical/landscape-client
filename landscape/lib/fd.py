"""A utility module which has FD-related functions.

This module mostly exists for L{clean_fds}, so it can be imported without
accidentally getting a reactor or something else that might create a critical
file descriptor.
"""

import os
import resource


def clean_fds():
    """Close all non-stdio file descriptors.

    This should be called at the beginning of a program to avoid inheriting any
    unwanted file descriptors from the invoking process.  Unfortunately, this
    is really common in unix!
    """
    rlimit_nofile = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    total_descriptors = min(4096, rlimit_nofile)
    for fd in range(3, total_descriptors):
        try:
            os.close(fd)
        except OSError:
            pass
