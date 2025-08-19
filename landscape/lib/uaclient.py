import logging

from landscape.client import IS_CORE
from landscape.client import IS_SNAP

if not IS_SNAP and not IS_CORE:
    from uaclient.status import status
    from uaclient.config import UAConfig


def get_pro_status():
    """Calls uaclient.status to get pro information."""
    try:
        config = UAConfig()
        pro_info = status(config)
        return pro_info
    except NameError:
        logging.warning(
            "Tried to use uaclient in SNAP or CORE environment, skipping call"
        )
        return {}
    except Exception:
        logging.warning(
            "Could not get pro information for computer"
        )
        return {}


def attach_pro(token):
    """Attaches a pro token to current machine."""
    ### TODO when creating activity for attaching pro
