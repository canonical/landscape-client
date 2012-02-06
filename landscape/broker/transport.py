"""Low-level server communication."""
import os
import time
import logging
import pprint

import pycurl
from twisted.internet.threads import blockingCallFromThread

from landscape.lib.fetch import fetch
from landscape.lib.fs import create_file
from landscape.lib import bpickle
from landscape.log import format_delta
from landscape import SERVER_API, VERSION
from landscape.broker.dnslookup import discover_server


class HTTPTransport(object):
    """Transport makes a request to exchange message data over HTTP.

    @param url: URL of the remote Landscape server message system.
    @param pubkey: SSH public key used for secure communication.
    @param payload_recorder: PayloadRecorder used for recording exchanges
        with the server.  If C{None}, exchanges will not be recorded.
    @param server_autodiscovery: Server autodiscovery is performed if True,
        otherwise server autodiscover is not done.
    @param autodiscover_srv_query_string: If server autodiscovery is done, this
        string will be sent to the DNS server when making a SRV query.
    @param autodiscover_a_query_string: If server autodiscovery is done, this
        string will be sent to the DNS server when making an A query.
    """

    def __init__(self, reactor, url, pubkey=None, payload_recorder=None,
                 server_autodiscover=False, autodiscover_srv_query_string="",
                 autodiscover_a_query_string=""):
        self._reactor = reactor
        self._url = url
        self._pubkey = pubkey
        self._payload_recorder = payload_recorder
        self._server_autodiscover = server_autodiscover
        self._autodiscover_srv_query_string = autodiscover_srv_query_string
        self._autodiscover_a_query_string = autodiscover_a_query_string

    def get_url(self):
        """Get the URL of the remote message system."""
        return self._url

    def set_url(self, url):
        """Set the URL of the remote message system."""
        self._url = url

    def _curl(self, payload, computer_id, message_api):
        if self._server_autodiscover:
            result = blockingCallFromThread(self._reactor, discover_server,
                                            autodiscover_srv_query_string,
                                            autodiscover_a_query_string)
            if result is not None:
                self._url = "https://%s/message-system" % result
            else:
                logging.warn("Autodiscovery failed.  Falling back to previous "
                             "settings.")

        headers = {"X-Message-API": message_api,
                   "User-Agent": "landscape-client/%s" % VERSION,
                   "Content-Type": "application/octet-stream"}
        if computer_id:
            headers["X-Computer-ID"] = computer_id
        curl = pycurl.Curl()
        return (curl, fetch(self._url, post=True, data=payload,
                            headers=headers, cainfo=self._pubkey, curl=curl))

    def exchange(self, payload, computer_id=None, message_api=SERVER_API):
        """Exchange message data with the server.

        @param payload: The object to send, it must be L{bpickle}-compatible.
        @param computer_id: The computer ID to send the message as (see
            also L{Identity}).

        @type: C{dict}
        @return: The server's response to sent message or C{None} in case
            of error.

        @note: This code is thread safe (HOPEFULLY).

        """
        spayload = bpickle.dumps(payload)
        if self._payload_recorder is not None:
            self._payload_recorder.save(spayload)
        try:
            start_time = time.time()
            if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                logging.debug("Sending payload:\n%s", pprint.pformat(payload))

            curly, data = self._curl(spayload, computer_id, message_api)
            logging.info("Sent %d bytes and received %d bytes in %s.",
                         len(spayload), len(data),
                         format_delta(time.time() - start_time))
        except:
            logging.exception("Error contacting the server at %s." % self._url)
            return None

        code = curly.getinfo(pycurl.RESPONSE_CODE)
        if code != 200:
            logging.error("Server returned non-expected result: %d" % (code,))
            return None

        try:
            response = bpickle.loads(data)
            if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                logging.debug("Received payload:\n%s",
                              pprint.pformat(response))
        except:
            logging.exception("Server returned invalid data: %r" % data)
            return None

        return response


class PayloadRecorder(object):
    """
    L{PayloadRecorder} records client exchanges with the server to disk for
    later playback.

    Exchange payloads will be stored one per file, where the file name is
    the elapsed time since the client was started.

    @param destination_dir - The directory to record exchanges in.
    """

    def __init__(self, destination_dir):
        self._time_offset = time.time()
        self._destination_dir = destination_dir
        self._last_payload_time = -1
        if self._destination_dir is not None:
            self._create_destination_dir(self._destination_dir)
            self._delete_old_payloads()

    def _create_destination_dir(self, destination_dir):
        """Create the destination directory if it does not exist.

        @param destination_dir: The directory to be created.
        """
        if not os.path.exists(destination_dir):
            os.mkdir(destination_dir)

    def _delete_old_payloads(self):
        """Delete payloads lying around from a previous session."""
        for filename in os.listdir(self._destination_dir):
            file_path = os.path.join(self._destination_dir, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)

    def save(self, payload):
        """Persist the given payload to disk.

        @param payload: The payload to be persisted.
        """
        payload_name = self.get_payload_filename()
        create_file(os.path.join(self._destination_dir, payload_name),
                    payload)

    def get_payload_filename(self):
        """
        Generate a payload filename.  This method ensures that payloads
        will have a unique name.
        """
        payload_time = time.time() - self._time_offset
        last_payload_time = '%.3f' % self._last_payload_time
        this_payload_time = '%.3f' % payload_time
        if last_payload_time == this_payload_time:
            payload_time = payload_time + 0.001
        self._last_payload_time = payload_time
        return '%.3f' % payload_time


class FakeTransport(object):
    """Fake transport for testing purposes."""

    def __init__(self, reactor=None, url=None, pubkey=None,
                 payload_recorder=None, server_autodiscover=False,
                 autodiscover_srv_query_string="",
                 autodiscover_a_query_string=""):
        self._pubkey = pubkey
        self._payload_recorder = payload_recorder
        self.payloads = []
        self.responses = []
        self._current_response = 0
        self.next_expected_sequence = 0
        self.computer_id = None
        self.message_api = None
        self.extra = {}
        self._url = url
        self._reactor = reactor
        self._server_autodiscover = server_autodiscover
        self._autodiscover_srv_query_string = autodiscover_srv_query_string
        self._autodiscover_a_query_string = autodiscover_a_query_string

    def get_url(self):
        return self._url

    def set_url(self, url):
        self._url = url

    def exchange(self, payload, computer_id=None, message_api=SERVER_API):
        self.payloads.append(payload)
        self.computer_id = computer_id
        self.message_api = message_api
        self.next_expected_sequence += len(payload.get("messages", []))

        if self._current_response < len(self.responses):
            response = self.responses[self._current_response]
            self._current_response += 1
        else:
            response = []

        result = {"next-expected-sequence": self.next_expected_sequence,
                  "messages": response}
        result.update(self.extra)
        return result
