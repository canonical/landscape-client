"""Utility functions for exchanging messages synchronously with a Landscape
Server instance.
"""

import logging
import time
from dataclasses import dataclass
from pprint import pformat
from typing import Any

import pycurl

from landscape import SERVER_API, VERSION
from landscape.lib import bpickle
from landscape.lib.fetch import fetch
from landscape.lib.format import format_delta


@dataclass
class ServerResponse:
    """The HTTP response from the server after a message exchange."""

    server_api: str
    server_uuid: bytes
    messages: list[dict[str, Any]]
    client_accepted_types_hash: bytes | None = None
    next_exchange_token: bytes | None = None
    next_expected_sequence: int | None = None


def exchange_messages(
    payload: dict,
    server_url: str,
    *,
    cainfo: str | None = None,
    computer_id: str | None = None,
    exchange_token: bytes | None = None,
    server_api: str = SERVER_API.decode(),
    http_client: str = "pycurl",
    ssl_client_cert: str | None = None,
    ssl_client_private_key: str | None = None,
) -> ServerResponse:
    """Sends `payload` via HTTP(S) to `server_url`, parsing and returning the
    response.

    :param payload: The object to send. It must be `bpickle`-compatible.
    :param server_url: The URL to which the payload will be sent.
    :param cainfo: Any additional certificate authority information to be used
        to verify an HTTPS connection.
    :param computer_id: The computer ID to send the message as.
    :param exchange_token: Token included in the exchange to prove client
        identity.
    :param http_client: The HTTP client to use ('pycurl' or 'urllib').
    :param ssl_client_cert: Path to a client certificate for mutual TLS.
    :param ssl_client_private_key: Path to the private key of
        `ssl_client_cert`.
    """
    start_time = time.time()
    logging.debug(f"Sending payload:\n{pformat(payload)}")

    data = bpickle.dumps(payload)
    headers = {
        "X-Message-API": server_api,
        "User-Agent": f"landscape-client/{VERSION}",
        "Content-Type": "application/octet-stream",
    }

    if computer_id:
        headers["X-Computer-ID"] = computer_id

    if exchange_token:
        headers["X-Exchange-Token"] = exchange_token.decode()

    curl = None
    if http_client == "pycurl":
        curl = pycurl.Curl()

    try:
        response_bytes = fetch(
            server_url,
            post=True,
            data=data,
            headers=headers,
            cainfo=cainfo,
            curl=curl,
            http_client=http_client,
            ssl_client_cert=ssl_client_cert,
            ssl_client_private_key=ssl_client_private_key,
        )
    except Exception:
        logging.exception(f"Error contacting the server at {server_url}.")
        if http_client != "urllib":
            logging.warning("Set http_client = urllib for a more detailed error.")
        raise

    logging.info(
        f"Sent {len(data)} bytes and received {len(response_bytes)} bytes in "
        f"{format_delta(time.time() - start_time)}"
    )

    try:
        response = bpickle.loads(response_bytes)
    except Exception:
        logging.exception(f"Server returned invalid data: {response_bytes!r}")
        raise

    logging.debug(f"Received payload:\n{pformat(response)}")

    return ServerResponse(
        response["server-api"],
        response["server-uuid"],
        response["messages"],
        response.get("client-accepted-types-hash"),
        response.get("next-exchange-token"),
        response.get("next-expected-sequence"),
    )
