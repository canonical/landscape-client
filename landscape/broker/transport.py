"""Low-level server communication."""
import time
import logging
import pprint
import uuid

import pycurl

from landscape.lib.fetch import fetch
from landscape.lib import bpickle
from landscape.log import format_delta
from landscape import SERVER_API, VERSION


class HTTPTransport(object):
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

    def _curl(self, payload, computer_id, exchange_token, message_api):
        headers = {"X-Message-API": message_api,
                   "User-Agent": "landscape-client/%s" % VERSION,
                   "Content-Type": "application/octet-stream"}
        if computer_id:
            headers["X-Computer-ID"] = computer_id
        if exchange_token:
            headers["X-Exchange-Token"] = str(exchange_token)
        curl = pycurl.Curl()
        return (curl, fetch(self._url, post=True, data=payload,
                            headers=headers, cainfo=self._pubkey, curl=curl))

    def exchange(self, payload, computer_id=None, exchange_token=None,
                 message_api=SERVER_API):
        """Exchange message data with the server.

        @param payload: The object to send, it must be L{bpickle}-compatible.
        @param computer_id: The computer ID to send the message as (see
            also L{Identity}).
        @param exchange_token: The token that the server has given us at the
            last exchange. It's used to prove that we are still the same
            client.

        @type: C{dict}
        @return: The server's response to sent message or C{None} in case
            of error.

        @note: This code is thread safe (HOPEFULLY).

        """
        spayload = bpickle.dumps(payload)
        start_time = time.time()
        if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
            logging.debug("Sending payload:\n%s", pprint.pformat(payload))
        try:
            curly, data = self._curl(spayload, computer_id, exchange_token,
                                     message_api)
        except:
            logging.exception("Error contacting the server at %s." % self._url)
            raise
        else:
            logging.info("Sent %d bytes and received %d bytes in %s.",
                         len(spayload), len(data),
                         format_delta(time.time() - start_time))

        try:
            response = bpickle.loads(data)
        except:
            logging.exception("Server returned invalid data: %r" % data)
            return None
        else:
            if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                logging.debug(
                    "Received payload:\n%s", pprint.pformat(response))

        return response


class FakeTransport(object):
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

    def exchange(self, payload, computer_id=None, exchange_token=None,
                 message_api=SERVER_API):
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

        result = {"next-expected-sequence": self.next_expected_sequence,
                  "next-exchange-token": unicode(uuid.uuid4()),
                  "messages": response}
        result.update(self.extra)
        return result
