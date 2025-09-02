import logging

from landscape.client import IS_CORE
from landscape.client import IS_SNAP

if not IS_SNAP and not IS_CORE:
    from uaclient.api.u.pro.attach.token.full_token_attach.v1 import (
        full_token_attach,
        FullTokenAttachOptions,
    )
    from uaclient.config import UAConfig
    from uaclient.exceptions import (
        ConnectivityError,
        ContractAPIError,
        LockHeldError,
        UbuntuProError,
    )
    from uaclient.status import status


class AttachProError(Exception):
    message = "Could not attach pro."


class ConnectivityException(AttachProError):
    message = "Not possible to connect to contracts service."


class ContractAPIException(AttachProError):
    message = "Unexpected error in the contracts service interaction."


class LockHeldException(AttachProError):
    message = "Another client process is holding the lock on the machine."


def get_pro_status():
    """Calls uaclient.status to get pro information."""
    try:
        config = UAConfig()
        pro_info = status(config)
        return pro_info
    except NameError:
        logging.warning(
            "Tried to use uaclient in SNAP or CORE environment, skipping call."
        )
        return {}
    except Exception:
        logging.warning(
            "Could not get pro information for computer."
        )
        return {}


async def attach_pro(token):
    """Attaches a pro token to current machine."""
    try:
        options = FullTokenAttachOptions(
            token=token,
            auto_enable_services=False
        )
        full_token_attach(options)
    except NameError:
        logging.warning(
            "Tried to use uaclient in SNAP or CORE environment, skipping call."
        )
        raise AttachProError
    except ConnectivityError:
        raise ConnectivityException
    except ContractAPIError:
        raise ContractAPIException
    except LockHeldError:
        raise LockHeldException
    except UbuntuProError:
        raise AttachProError
