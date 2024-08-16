"""Utility functions for sending a registration message to a server.

These are intended to be used directly and synchronously - without involving
other machinery, i.e. the Broker, and therefore exist outside of the usual
message exchange scheduling system. Callers are responsible for ensuring
exchange state is consistent when using these functions.
"""
from dataclasses import asdict
from dataclasses import dataclass
import json
import logging
from typing import Any

from landscape.client.broker.registration import Identity
from landscape.client.exchange import exchange_messages
from landscape.client.manager.ubuntuproinfo import get_ubuntu_pro_info

from landscape.lib.fetch import HTTPCodeError
from landscape.lib.fetch import PyCurlError
from landscape.lib.network import get_fqdn
from landscape.lib.vm_info import get_container_info
from landscape.lib.vm_info import get_vm_info


@dataclass
class ClientRegistrationInfo:
    """The information required by the server to register a client."""

    access_group: str
    account_name: str
    computer_title: str

    container_info: str | None = None
    hostagent_uid: str | None = None
    hostname: str | None = None
    juju_info: None = None  # We don't send Juju info currently.
    registration_password: str | None = None
    tags: str | None = None
    ubuntu_pro_info: str | None = None
    vm_info: bytes | None = None

    @classmethod
    def from_identity(
        cls: type["ClientRegistrationInfo"],
        identity: Identity,
    ) -> "ClientRegistrationInfo":
        return cls(
            identity.access_group,
            identity.account_name,
            identity.computer_title,
            container_info=get_container_info(),
            hostagent_uid=identity.hostagent_uid,
            hostname=get_fqdn(),
            registration_password=identity.registration_key,
            tags=identity.tags,
            ubuntu_pro_info=json.dumps(get_ubuntu_pro_info()),
            vm_info=get_vm_info(),
        )


class RegistrationException(Exception):
    """Exception raised when registration fails for any reason."""


@dataclass
class RegistrationInfo:
    """The persistable information returned from the server after a
    registration message is accepted.
    """

    insecure_id: int
    secure_id: str
    server_uuid: str


def register(
    client_info: ClientRegistrationInfo, server_url: str
) -> RegistrationInfo:
    """Sends a registration message to the server at `server_url`, returning
    registration info if successful.

    :raises RegistrationException: if the registration fails for any reason.
    """
    message = _create_message(client_info)
    logging.debug(f"Sending registration message: {message}")

    try:
        response = exchange_messages(message, server_url)
    except HTTPCodeError as e:
        if e.http_code == 404:
            # Most likely cause is that we are trying to speak to a server with
            # an API version that it does not support.
            raise RegistrationException(
                "\nWe were unable to contact the server or it is "
                "an incompatible server version.\n"
                "Please check your server URL and version."
            ) from e

        raise  # Other exceptions are unexpected and should propagate.
    except PyCurlError as e:
        if e.error_code == 60:
            raise RegistrationException(
                "\nThe server's SSL information is incorrect or fails "
                "signature verification!\n"
                "If the server is using a self-signed certificate, please "
                "ensure you supply it with the --ssl-public-key parameter."
            ) from e

        raise  # Other exceptions are unexpected and should propagate.

    if not response.messages:
        raise RegistrationException("No messages in registration response.")

    # Iterate over the response messages to extract the insecure and secure
    # IDs.
    client_ids = None
    for response_message in response.messages:
        client_ids = _handle_message(response_message)

        if client_ids is not None:
            break
    else:
        raise RegistrationException(
            "Did not receive ID information in registration response."
        )

    secure_id, insecure_id = client_ids

    return RegistrationInfo(
        insecure_id=insecure_id,
        secure_id=secure_id,
        server_uuid=response.server_uuid,
    )


def _create_message(
    client_info: ClientRegistrationInfo,
) -> dict[str, list[dict[str, Any]]]:
    """Serializes `client_info` into a registration message suitable for
    message exchange. Values that are `None` are stripped.
    """
    message = {k: v for k, v in asdict(client_info).items() if v is not None}
    message["type"] = "register"

    return {"messages": [message]}


def _handle_message(message: dict[str, Any]) -> tuple[str, int] | None:
    """Parses a single message in the server's response to the registration
    message.

    :returns: Pair of insecure ID and secure ID for the registered client.
    :raises RegistrationException: If the message implies registration did not
        succeed.
    """
    match message:
        case {"type": "registration", "info": "unknown-account"}:
            raise RegistrationException(
                "Invalid account name or registration key."
            )
        case {"type": "registration", "info": "max-pending-computers"}:
            raise RegistrationException(
                "Maximum number of computers pending approval reached. "
                "Log in to your Landscape server account page to manage "
                "pending computer approvals."
            )
        case {"type": "set-id", "id": secure_id, "insecure-id": insecure_id}:
            return secure_id, insecure_id
        case _:
            return None
