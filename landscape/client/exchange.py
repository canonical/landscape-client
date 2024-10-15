"""Utility functions for exchanging messages synchronously with a Landscape
Server instance.
"""
from dataclasses import dataclass
import logging
from pprint import pformat
import time
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import pycurl

from landscape import SERVER_API
from landscape import VERSION
from landscape.lib import bpickle
from landscape.lib.fetch import fetch
from landscape.lib.format import format_delta


@dataclass
class ServerResponse:
    """The HTTP response from the server after a message exchange."""

    server_api: str
    server_uuid: bytes
    messages: List[Dict[str, Any]]
    client_accepted_types_hash: Optional[bytes] = None
    next_exchange_token: Optional[bytes] = None
    next_expected_sequence: Optional[int] = None


def exchange_messages(
    payload: dict,
    server_url: str,
    *,
    cainfo: Optional[str] = None,
    computer_id: Optional[str] = None,
    exchange_token: Optional[bytes] = None,
    server_api: str = SERVER_API.decode(),
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

    curl = pycurl.Curl()

    try:
        response_bytes = fetch(
            server_url,
            post=True,
            data=data,
            headers=headers,
            cainfo=cainfo,
            curl=curl,
        )
    except Exception:
        logging.exception(f"Error contacting the server at {server_url}.")
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
