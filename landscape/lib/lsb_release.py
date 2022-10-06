"""Get information from /usr/bin/lsb_release."""
import os
from subprocess import CalledProcessError, check_output

LSB_RELEASE = "/usr/bin/lsb_release"
LSB_RELEASE_FILENAME = "/etc/lsb_release"
LSB_RELEASE_FILE_KEYS = {
    "DISTRIB_ID": "distributor-id",
    "DISTRIB_DESCRIPTION": "description",
    "DISTRIB_RELEASE": "release",
    "DISTRIB_CODENAME": "code-name",
}


def parse_lsb_release(lsb_release_filename=None):
    """
    Returns a C{dict} holding information about the system LSB release.
    Reads from C{lsb_release_filename} if it exists, else calls
    C{LSB_RELEASE}
    """
    if lsb_release_filename and os.path.exists(lsb_release_filename):
        return parse_lsb_release_file(lsb_release_filename)

    with open(os.devnull, 'w') as FNULL:
        try:
            lsb_info = check_output([LSB_RELEASE, "-as"], stderr=FNULL)
        except (CalledProcessError, FileNotFoundError):
            # Fall back to reading file, even if it doesn't exist.
            return parse_lsb_release_file(lsb_release_filename)
        else:
            dist, desc, release, code_name, _ = lsb_info.decode().split("\n")

            return {
                "distributor-id": dist,
                "release": release,
                "code-name": code_name,
                "description": desc,
            }


def parse_lsb_release_file(filename):
    """
    Returns a C{dict} holding information about the system LSB release
    by attempting to parse C{filename}.

    @raises: A FileNotFoundError if C{filename} does not exist.
    """
    info = {}

    with open(filename) as fd:
        for line in fd:
            key, value = line.split("=")

            if key in LSB_RELEASE_FILE_KEYS:
                key = LSB_RELEASE_FILE_KEYS[key.strip()]
                value = value.strip().strip('"')
                info[key] = value

    return info
