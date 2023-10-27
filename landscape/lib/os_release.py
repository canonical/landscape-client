"""Get information from os-release."""
import os

OS_RELEASE_FILENAME = "/var/lib/snapd/hostfs/etc/os-release"
OS_RELEASE_FILENAME_FALLBACK = "/etc/os-release"
OS_RELEASE_FILENAME_SECONDARY_FALLBACK = "/usr/lib/os-release"
OS_RELEASE_FILE_KEYS = {
    "NAME": "distributor-id",
    "PRETTY_NAME": "description",
    "VERSION_ID": "release",
    "VERSION_CODENAME": "code-name",
}


def get_os_filename():
    """
    Provide the appropriate file for os release info.
    If a snap, we want the host os so need to use
    /var/lib/snapd/hostfs/etc/os-release, if not a snap
    /etc/os-release will be used as first fallback or
    /usr/lib/os-release as a fallback as indicated in os-release
    at Freedesktop.org
    """

    os_filename = OS_RELEASE_FILENAME

    if not os.path.exists(os_filename) or not os.access(
        os_filename,
        os.R_OK,
    ):
        os_filename = OS_RELEASE_FILENAME_FALLBACK

        if not os.path.exists(os_filename) or not os.access(
            os_filename,
            os.R_OK,
        ):
            os_filename = OS_RELEASE_FILENAME_FALLBACK

    return os_filename


def parse_os_release(os_release_filename=None):
    """
    Returns a C{dict} holding information about the system LSB release
    by attempting to parse C{os_release_filename} if specified. If no
    filename is provided

    @raises: A FileNotFoundError if C{filename} does not exist.
    """
    info = {}

    if os_release_filename is None:
        os_release_filename = get_os_filename()

    with open(os_release_filename) as fd:
        for line in fd:
            key, value = line.split("=")

            if key in OS_RELEASE_FILE_KEYS:
                key = OS_RELEASE_FILE_KEYS[key.strip()]
                value = value.strip().strip('"')
                info[key] = value

    return info
