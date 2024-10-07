"""Low-level server communication."""
from dataclasses import asdict
import uuid
from typing import Optional
from typing import Union

from landscape import SERVER_API
from landscape.client.exchange import exchange_messages
from landscape.lib.compat import unicode


class HTTPTransport:
    """Transport makes a request to exchange message data over HTTP.

    @param url: URL of the remote Landscape server message system.
    @param pubkey: SSH public key used for secure communication.
    """

    def __init__(self, reactor, url, pubkey=None):
        self._reactor = reactor
        self._url = url
        self._pubkey = pubkey

    def get_url(self):
        """Get the URL of the remote message system."""
        return self._url

    def set_url(self, url):
        """Set the URL of the remote message system."""
        self._url = url

    def exchange(
        self,
        payload: dict,
        computer_id: Optional[str] = None,
        exchange_token: Optional[bytes] = None,
        message_api: bytes = SERVER_API,
    ) -> Union[dict, None]:
        """Exchange message data with the server.

        :param payload: The object to send. It must be `bpickle`-compatible.
        :param computer_id: The computer ID to send the message as.
        :param exchange_token: Token included in the exchange to prove client

        :return: The server's response to the sent message or `None` if there
            was an error.

        :note: This code is thread safe (HOPEFULLY).
        """
        try:
            response = exchange_messages(
                payload,
                self._url,
                cainfo=self._pubkey,
                computer_id=computer_id,
                exchange_token=exchange_token,
                server_api=message_api.decode(),
            )
        except Exception:
            return None

        # Return `ServerResponse` as a dictionary
        #  converting the field names back to kebab case
        #  which (imo) is better than mixing snake_case & kebab-case
        #  in landscape.client.broker.exchange.MessageExchange.
        return asdict(
            response,
            dict_factory=lambda data: {
                k.replace("_", "-"): v for k, v in data
            },
        )


class FakeTransport:
    """Fake transport for testing purposes."""

    def __init__(self, reactor=None, url=None, pubkey=None):
        self._pubkey = pubkey
        self.payloads = []
        self.responses = []
        self._current_response = 0
        self.next_expected_sequence = 0
        self.computer_id = None
        self.exchange_token = None
        self.message_api = None
        self.extra = {}
        self._url = url
        self._reactor = reactor

    def get_url(self):
        return self._url

    def set_url(self, url):
        self._url = url

    def exchange(
        self,
        payload,
        computer_id=None,
        exchange_token=None,
        message_api=SERVER_API,
    ):
        self.payloads.append(payload)
        self.computer_id = computer_id
        self.exchange_token = exchange_token
        self.message_api = message_api
        self.next_expected_sequence += len(payload.get("messages", []))

        if self._current_response < len(self.responses):
            response = self.responses[self._current_response]
            self._current_response += 1
        else:
            response = []

        if isinstance(response, Exception):
            raise response

        result = {
            "next-expected-sequence": self.next_expected_sequence,
            "next-exchange-token": unicode(uuid.uuid4()),
            "messages": response,
        }
        result.update(self.extra)
        return result
