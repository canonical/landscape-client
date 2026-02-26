import logging
import os

IS_SNAP = os.getenv("LANDSCAPE_CLIENT_SNAP")
IS_CORE = os.getenv("SNAP_SAVE_DATA") is not None

USER = os.getenv("LANDSCAPE_CLIENT_USER")
if USER and os.getenv("LANDSCAPE_CLIENT_BUILDING"):
    GROUP = USER
else:
    USER = "root" if IS_SNAP else "landscape"
    GROUP = "root" if IS_SNAP else "landscape"

DEFAULT_CONFIG = (
    "/etc/landscape-client.conf" if IS_SNAP else "/etc/landscape/client.conf"
)

UA_DATA_DIR = (
    "/var/lib/snapd/hostfs/var/lib/ubuntu-advantage"
    if IS_SNAP
    else "/var/lib/ubuntu-advantage"
)

FILE_MODE = os.getenv("LANDSCAPE_CLIENT_FILE_MODE", "640")
try:
    FILE_MODE = int(FILE_MODE, base=8) & 0o777
except ValueError:
    logging.warning("Found invalid FILE_MODE: %s", FILE_MODE)
    logging.warning("Using FILE_MODE 640")
    FILE_MODE = 0o640

DIRECTORY_MODE = os.getenv("LANDSCAPE_CLIENT_DIRECTORY_MODE", "750")
try:
    DIRECTORY_MODE = int(DIRECTORY_MODE, base=8) & 0o777
except ValueError:
    logging.warning("Found invalid DIRECTORY_MODE: %s", DIRECTORY_MODE)
    logging.warning("Using DIRECTORY_MODE 750")
    DIRECTORY_MODE = 0o750
