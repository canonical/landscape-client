import os

IS_SNAP = os.getenv("LANDSCAPE_CLIENT_SNAP")
IS_CORE = os.getenv("LANDSCAPE_CLIENT_CORE")

USER = "root" if IS_SNAP else "landscape"
GROUP = "root" if IS_SNAP else "landscape"

DEFAULT_CONFIG = (
    "/etc/landscape-client.conf" if IS_SNAP else "/etc/landscape/client.conf"
)
