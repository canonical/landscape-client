"""
The purpose of this library is to act as a wrapper over the uaclient library
for landscape. Given the uaclient library is not available in snap/core
environments this allows for us to use our wrapper methods that will have
safety checks to ensure we are allowed to use the uaclient methods.
"""

import logging

from landscape.client import IS_CORE, IS_SNAP

try:
    if IS_CORE or IS_SNAP:  # pragma: no cover
        uaclient = None
    else:
        from uaclient.api.u.pro.attach.token.full_token_attach.v1 import (
            FullTokenAttachOptions,
            full_token_attach,
        )
        from uaclient.api.u.pro.detach.v1 import detach
        from uaclient.api.u.pro.status.is_attached.v1 import is_attached
        from uaclient.config import UAConfig
        from uaclient.exceptions import (
            AttachInvalidTokenError,
            ConnectivityError,
            ContractAPIError,
            LockHeldError,
            UbuntuProError,
        )
        from uaclient.status import status

        uaclient = 1
except ImportError:  # pragma: no cover
    uaclient = None


class ProManagementError(Exception):
    message = "Error managing pro."

    def __init__(self, message: str | None = None):
        if message:
            self.message = message

    def __str__(self):
        return self.message


class ConnectivityException(ProManagementError):
    message = "Not possible to connect to contracts service."


class ContractAPIException(ProManagementError):
    message = "Unexpected error in the contracts service interaction."


class LockHeldException(ProManagementError):
    message = "Another client process is holding the lock on the machine."


class InvalidTokenException(ProManagementError):
    message = "Invalid pro token provided."


class ProNotAttachedError(ProManagementError):
    message = "Pro is not attached on this machine."


UACLIENT_ERROR_MESSAGE = (
    "The ubuntu advantage library is not available or not up to date."  # noqa
)


def get_pro_status():
    """Calls uaclient.status to get pro information."""
    if uaclient is None:
        logging.warning(UACLIENT_ERROR_MESSAGE)
        return {}
    try:
        config = UAConfig()
        pro_info = status(config)
        return pro_info
    except Exception:
        logging.warning("Could not get pro information for computer.")
        return {}


def attach_pro(token):
    """Attaches a pro token to current machine."""
    if uaclient is None:
        logging.warning(UACLIENT_ERROR_MESSAGE)
        raise ProManagementError(UACLIENT_ERROR_MESSAGE)

    try:
        options = FullTokenAttachOptions(token=token, auto_enable_services=False)
        full_token_attach(options)
    except AttachInvalidTokenError:
        raise InvalidTokenException
    except ConnectivityError:
        raise ConnectivityException
    except ContractAPIError:
        raise ContractAPIException
    except LockHeldError:
        raise LockHeldException
    except UbuntuProError:
        raise ProManagementError


def detach_pro():
    if uaclient is None:
        logging.warning(UACLIENT_ERROR_MESSAGE)
        raise ProManagementError(UACLIENT_ERROR_MESSAGE)

    try:
        result = is_attached()
        if not result.is_attached:
            raise ProNotAttachedError

        detach()
    except UbuntuProError:
        raise ProManagementError
