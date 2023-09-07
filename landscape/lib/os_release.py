"""Get information from os-release."""
import os

OS_RELEASE_FILENAME = "/etc/os-release"
OS_RELEASE_FILENAME_FALLBACK = "/usr/lib/os-release"
OS_RELEASE_FILE_KEYS = {
    "NAME": "distributor-id",
    "PRETTY_NAME": "description",
    "VERSION_ID": "release",
    "VERSION_CODENAME": "code-name",
}


def parse_os_release(os_release_filename=None):
    """
    Returns a C{dict} holding information about the system LSB release
    by attempting to parse C{os_release_filename} if specified. If no
    filename is provided /etc/os-release will be used or
    /usr/lib/os-release as a fallback as indicated in os-release
    at Freedesktop.org

    @raises: A FileNotFoundError if C{filename} does not exist.
    """
    info = {}

    if os_release_filename is None:
        os_release_filename = OS_RELEASE_FILENAME
        if not os.path.exists(os_release_filename) or not os.access(
            os_release_filename,
            os.R_OK,
        ):
            os_release_filename = OS_RELEASE_FILENAME_FALLBACK

    with open(os_release_filename) as fd:
        for line in fd:
            key, value = line.split("=")

            if key in OS_RELEASE_FILE_KEYS:
                key = OS_RELEASE_FILE_KEYS[key.strip()]
                value = value.strip().strip('"')
                info[key] = value

    return info
