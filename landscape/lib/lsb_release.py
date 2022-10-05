"""Get information from /usr/bin/lsb_release."""

LSB_RELEASE_FILENAME = "/usr/bin/lsb_release"
LSB_RELEASE_INFO_KEYS = {"distributor-id": "-si",
                         "release": "-sr",
                         "code-name": "-sc",
                         "description": "-sd"}

import subprocess

def parse_lsb_release(lsb_release_filename):
    """Return a C{dict} holding information about the system LSB release.
    @raises: An OSError exception if C{lsb_release_filename} does not exist.
    """
    info = {}
    for key in LSB_RELEASE_INFO_KEYS:
        value = subprocess.check_output([LSB_RELEASE_FILENAME] + [LSB_RELEASE_INFO_KEYS[key.strip()]])
        info[key.strip()] = value.strip().strip('"')
    return info
