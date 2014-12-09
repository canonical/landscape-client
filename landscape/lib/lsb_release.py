"""Get information from /etc/lsb_release."""

LSB_RELEASE_FILENAME = "/etc/lsb-release"
LSB_RELEASE_INFO_KEYS = {"DISTRIB_ID": "distributor-id",
                         "DISTRIB_DESCRIPTION": "description",
                         "DISTRIB_RELEASE": "release",
                         "DISTRIB_CODENAME": "code-name"}


def parse_lsb_release(lsb_release_filename):
    """Return a C{dict} holding information about the system LSB release.

    @raises: An IOError exception if C{lsb_release_filename} could not be read.
    """
    fd = open(lsb_release_filename, "r")
    info = {}
    try:
        for line in fd:
            key, value = line.split("=")
            if key in LSB_RELEASE_INFO_KEYS:
                key = LSB_RELEASE_INFO_KEYS[key.strip()]
                value = value.strip().strip('"')
                info[key] = value
    finally:
        fd.close()
    return info
