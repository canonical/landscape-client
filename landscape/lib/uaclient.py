"""
The purpose of this library is to act as a wrapper over the uaclient library
for landscape. Given the uaclient library is not available in snap/core
environments this allows for us to use our wrapper methods that will have
safety checks to ensure we are allowed to use the uaclient methods.
"""
import logging

try:
    uaclient = 1
    from uaclient.api.u.pro.attach.token.full_token_attach.v1 import (
        full_token_attach,
        FullTokenAttachOptions,
    )
    from uaclient.config import UAConfig
    from uaclient.exceptions import (
        AttachInvalidTokenError,
        ConnectivityError,
        ContractAPIError,
        LockHeldError,
        UbuntuProError,
    )
    from uaclient.status import status
except ImportError:  # pragma: no cover
    uaclient = None


class AttachProError(Exception):
    message = "Could not attach pro."

    def __str__(self):
        return self.message


class ConnectivityException(AttachProError):
    message = "Not possible to connect to contracts service."


class ContractAPIException(AttachProError):
    message = "Unexpected error in the contracts service interaction."


class LockHeldException(AttachProError):
    message = "Another client process is holding the lock on the machine."


class InvalidTokenException(AttachProError):
    message = "Invalid pro token provided."


def get_pro_status():
    """Calls uaclient.status to get pro information."""
    if uaclient is None:
        logging.warning(
            "The ubuntu advantage library is not available or not up to date."
        )
        return {}
    try:
        config = UAConfig()
        pro_info = status(config)
        return pro_info
    except Exception:
        logging.warning(
            "Could not get pro information for computer."
        )
        return {}


def attach_pro(token):
    """Attaches a pro token to current machine."""
    if uaclient is None:
        logging.warning(
            "The ubuntu advantage library is not available or not up to date."
        )
        raise AttachProError

    try:
        options = FullTokenAttachOptions(
            token=token,
            auto_enable_services=False
        )
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
        raise AttachProError
