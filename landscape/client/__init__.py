import os

IS_SNAP = os.getenv("LANDSCAPE_CLIENT_SNAP")
IS_CORE = os.getenv("SNAP_SAVE_DATA") is not None

USER = "root" if IS_SNAP else "landscape"
GROUP = "root" if IS_SNAP else "landscape"

DEFAULT_CONFIG = (
    os.environ["SNAP_COMMON"] + "/etc/landscape-client.conf"
    if IS_SNAP
    else "/etc/landscape/client.conf"
)
