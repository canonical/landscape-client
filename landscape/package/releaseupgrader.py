import os
import sys


class ReleaseUpgrader(object):
    """Perform release upgrades."""

    queue_name = "release-upgrader"


def find_release_upgrader_command():
    dirname = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(dirname, "landscape-release-upgrader")
