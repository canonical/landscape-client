"""
The purpose of this library is to act as a wrapper over the uaclient library
for landscape. Given the uaclient library is not available in snap/core
environments this allows for us to use our wrapper methods that will have
safety checks to ensure we are allowed to use the uaclient methods.
"""

import logging
import os
import tempfile
from contextlib import contextmanager

from landscape.client.environment import IS_CORE, IS_SNAP

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


@contextmanager
def uaclient_environment(data_path: str | None = None):
    """Ensure XDG_CACHE_HOME (and HOME if needed) points to a writable
    location (such as Landscape's data_path) so uaclient does not attempt
    to write cache files to an inaccessible user home directory.
    """
    cache_dir = None
    if data_path:
        cache_dir = os.path.join(data_path, "cache")
    elif not os.environ.get("XDG_CACHE_HOME"):
        default_dir = "/var/lib/landscape/client"
        if os.path.isdir(default_dir) and os.access(default_dir, os.W_OK):
            cache_dir = os.path.join(default_dir, "cache")
        else:
            cache_dir = os.path.join(tempfile.gettempdir(), "landscape-cache")

    orig_xdg = os.environ.get("XDG_CACHE_HOME")
    orig_home = os.environ.get("HOME")
    try:
        if cache_dir:
            try:
                os.makedirs(cache_dir, exist_ok=True)
            except OSError:
                pass
            os.environ["XDG_CACHE_HOME"] = cache_dir
        if data_path and (orig_home is None or not os.access(orig_home, os.W_OK)):
            os.environ["HOME"] = data_path
        yield
    finally:
        if orig_xdg is not None:
            os.environ["XDG_CACHE_HOME"] = orig_xdg
        elif cache_dir and "XDG_CACHE_HOME" in os.environ:
            os.environ.pop("XDG_CACHE_HOME", None)
        if orig_home is not None:
            os.environ["HOME"] = orig_home
        elif data_path and "HOME" in os.environ and orig_home is None:
            os.environ.pop("HOME", None)


def get_pro_status(data_path: str | None = None):
    """Calls uaclient.status to get pro information."""
    if uaclient is None:
        logging.warning(UACLIENT_ERROR_MESSAGE)
        return {}
    try:
        with uaclient_environment(data_path):
            config = UAConfig()
            pro_info = status(config)
            return pro_info
    except Exception:
        logging.warning("Could not get pro information for computer.")
        return {}


def attach_pro(token, data_path: str | None = None):
    """Attaches a pro token to current machine."""
    if uaclient is None:
        logging.warning(UACLIENT_ERROR_MESSAGE)
        raise ProManagementError(UACLIENT_ERROR_MESSAGE)

    try:
        with uaclient_environment(data_path):
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


def detach_pro(data_path: str | None = None):
    if uaclient is None:
        logging.warning(UACLIENT_ERROR_MESSAGE)
        raise ProManagementError(UACLIENT_ERROR_MESSAGE)

    try:
        with uaclient_environment(data_path):
            result = is_attached()
            if not result.is_attached:
                raise ProNotAttachedError

            detach()
    except UbuntuProError:
        raise ProManagementError
