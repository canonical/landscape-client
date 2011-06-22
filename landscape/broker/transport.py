"""Low-level server communication."""
import os
import time
import logging
import pprint

import pycurl

from landscape.lib.fetch import fetch
from landscape.lib import bpickle
from landscape.log import format_delta
from landscape import SERVER_API, VERSION


class HTTPTransport(object):
    """Transport makes a request to exchange message data over HTTP."""

    def __init__(self, url, pubkey=None):
        """
        @param url: URL of the remote Landscape server message system.
        @param pubkey: SSH public key used for secure communication.
        """
        self._url = url
        self._pubkey = pubkey
        self._exchange_recorder = PayloadRecorder('/tmp/landscape-replay')


    def get_url(self):
        """Get the URL of the remote message system."""
        return self._url

    def set_url(self, url):
        """Set the URL of the remote message system."""
        self._url = url

    def _curl(self, payload, computer_id, message_api):
        headers= {"X-Message-API": message_api,
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
        self._exchange_recorder.save(spayload)
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
    """
    
    def __init__(self, destination_dir):
        """
        @param destination_dir - The directory to record exchanges in.
        """
        self._time = time.time
        self._time_offset = self._time()
        self.destination_dir = destination_dir
        self.last_payload_time = -1
        if self.destination_dir != None:
            self._create_destination_dir(self.destination_dir)
            self._delete_old_payloads()

    def _create_destination_dir(self, destination_dir):
        """Create the destination directory if it does not exist.

        @param destination_dir: The directory to be created.
        """
        if not os.path.exists(destination_dir):
            os.mkdir(destination_dir)
        
    def _delete_old_payloads(self):
        """Delete payloads lying around from a previous session."""
        for file in os.listdir(self.destination_dir):
            if os.path.isfile(self.destination_dir + '/' + file):
                os.unlink(self.destination_dir + '/' + file)

    def save(self, payload):
        """Persist the given payload to disk.

        @param payload: The payload to be persisted.
        """
        
        payload_name = self.get_payload_name()
        file(self.destination_dir + '/' + payload_name, 'w').write(payload)

    def get_payload_name(self):
        """
        Generate a payload filename.  This method ensures that payloads
        will have a unique name.
        """
        payload_time = self._time() - self._time_offset
        if self.last_payload_time == payload_time:
            payload_time = payload_time + .001
        self.last_payload_time = payload_time
        return str(payload_time)


class FakeTransport(object):
    """Fake transport for testing purposes."""

    def __init__(self, url=None, pubkey=None):
        self._pubkey = pubkey
        self.payloads = []
        self.responses = []
        self._current_response = 0
        self.next_expected_sequence = 0
        self.computer_id = None
        self.message_api = None
        self.extra = {}
        self._url = url

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
