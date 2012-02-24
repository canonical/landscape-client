import os

from landscape import VERSION
from landscape.broker.transport import HTTPTransport, PayloadRecorder
from landscape.lib.fetch import PyCurlError
from landscape.lib.fs import create_file, read_file
from landscape.lib import bpickle

from landscape.tests.helpers import (
    LandscapeTest, LogKeeperHelper, MockerTestCase)

from twisted.web import server, resource
from twisted.internet import reactor
from twisted.internet.ssl import DefaultOpenSSLContextFactory
from twisted.internet.threads import deferToThread


def sibpath(path):
    return os.path.join(os.path.dirname(__file__), path)


PRIVKEY = sibpath("private.ssl")
PUBKEY = sibpath("public.ssl")
BADPRIVKEY = sibpath("badprivate.ssl")
BADPUBKEY = sibpath("badpublic.ssl")


def fake_curl(payload, param2, param3):
    """Stub out the curl network call."""
    class Curly(object):
        def getinfo(self, param1):
            return 200
    return (Curly(), bpickle.dumps("%s response" % payload))


class DataCollectingResource(resource.Resource):
    request = content = None

    def getChild(self, request, name):
        return self

    def render(self, request):
        self.request = request
        self.content = request.content.read()
        return bpickle.dumps("Great.")


class HTTPTransportTest(LandscapeTest):

    helpers = [LogKeeperHelper]

    def setUp(self):
        super(HTTPTransportTest, self).setUp()
        self.ports = []

    def tearDown(self):
        super(HTTPTransportTest, self).tearDown()
        for port in self.ports:
            port.stopListening()

    def test_get_url(self):
        url = "http://example/ooga"
        transport = HTTPTransport(None, url)
        self.assertEqual(transport.get_url(), url)

    def test_set_url(self):
        transport = HTTPTransport(None, "http://example/ooga")
        transport.set_url("http://example/message-system")
        self.assertEqual(transport.get_url(), "http://example/message-system")

    def test_request_data(self):
        """
        When a request is sent with HTTPTransport.exchange, it should
        include the (optional) computer ID, a user agent, and the
        message API version as HTTP headers, and the payload as a
        bpickled request body.
        """
        r = DataCollectingResource()
        port = reactor.listenTCP(0, server.Site(r), interface="127.0.0.1")
        self.ports.append(port)
        transport = HTTPTransport(
            None, "http://localhost:%d/" % (port.getHost().port,))
        result = deferToThread(transport.exchange, "HI", computer_id="34",
                               message_api="X.Y")

        def got_result(ignored):
            self.assertEqual(r.request.received_headers["x-computer-id"],
                             "34")
            self.assertEqual(r.request.received_headers["user-agent"],
                             "landscape-client/%s" % (VERSION,))
            self.assertEqual(r.request.received_headers["x-message-api"],
                             "X.Y")
            self.assertEqual(bpickle.loads(r.content), "HI")
        result.addCallback(got_result)
        return result

    def test_ssl_verification_positive(self):
        """
        The client transport should complete an upload of messages to
        a host which provides SSL data which can be verified by the
        public key specified.
        """
        r = DataCollectingResource()
        context_factory = DefaultOpenSSLContextFactory(PRIVKEY, PUBKEY)
        port = reactor.listenSSL(0, server.Site(r), context_factory,
                                 interface="127.0.0.1")
        self.ports.append(port)
        transport = HTTPTransport(
            None, "https://localhost:%d/" % (port.getHost().port,),
            PUBKEY)
        result = deferToThread(transport.exchange, "HI", computer_id="34",
                               message_api="X.Y")

        def got_result(ignored):
            self.assertEqual(r.request.received_headers["x-computer-id"],
                             "34")
            self.assertEqual(r.request.received_headers["user-agent"],
                             "landscape-client/%s" % (VERSION,))
            self.assertEqual(r.request.received_headers["x-message-api"],
                             "X.Y")
            self.assertEqual(bpickle.loads(r.content), "HI")
        result.addCallback(got_result)
        return result

    def test_ssl_verification_negative(self):
        """
        If the SSL server provides a key which is not verified by the
        specified public key, then the client should immediately end
        the connection without uploading any message data.
        """
        self.log_helper.ignore_errors(PyCurlError)
        r = DataCollectingResource()
        context_factory = DefaultOpenSSLContextFactory(BADPRIVKEY,
                                                       BADPUBKEY)
        port = reactor.listenSSL(0, server.Site(r), context_factory,
                                 interface="127.0.0.1")
        self.ports.append(port)
        transport = HTTPTransport(None, "https://localhost:%d/"
                                  % (port.getHost().port,), pubkey=PUBKEY)

        result = deferToThread(transport.exchange, "HI", computer_id="34",
                               message_api="X.Y")

        def got_result(ignored):
            self.assertEqual(r.request, None)
            self.assertEqual(r.content, None)
            self.assertTrue("server certificate verification failed"
                            in self.logfile.getvalue())
        result.addCallback(got_result)
        return result

    def test_payload_recording_works(self):
        """
        When C{HTTPTransport} is configured with a payload recorder, exchanges
        with the server should be saved to the filesystem.
        """
        path = self.makeDir()
        recorder = PayloadRecorder(path)

        def static_filename():
            return "filename"
        recorder.get_payload_filename = static_filename

        transport = HTTPTransport(None, "http://localhost",
                                  payload_recorder=recorder)

        transport._curl = fake_curl

        transport.exchange("pay load")

        file_path = os.path.join(path, static_filename())
        self.assertEqual("pay load", bpickle.loads(read_file(file_path)))

    def test_exchange_works_without_payload_recording(self):
        """
        When C{HTTPTransport} is configured without a payload recorder,
        exchanges with the server should still complete.
        """
        transport = HTTPTransport(None, "http://localhost")
        self.called = False

        def fake_curl(param1, param2, param3):
            """Stub out the curl network call."""
            self.called = True

            class Curly(object):
                def getinfo(self, param1):
                    return 200
            return (Curly(), bpickle.dumps("pay load response"))

        transport._curl = fake_curl

        transport.exchange("pay load")

        self.assertTrue(self.called)


class PayloadRecorderTest(MockerTestCase):

    def test_get_payload_filename(self):
        """
        L{PayloadRecorder.get_payload_filename} should return a filename that
        is equal to the number of seconds since it was created.
        """
        mock = self.mocker.replace("time.time")
        mock()
        self.mocker.result(0.0)
        mock()
        self.mocker.result(12.3456)
        self.mocker.replay()
        recorder = PayloadRecorder(None)

        payload_name = recorder.get_payload_filename()

        self.assertEqual("12.346", payload_name)

    def test_get_payload_filename_no_duplicates(self):
        """
        L{PayloadRecorder.get_payload_filename} should not generate duplicate
        payload names.
        """
        mock = self.mocker.replace("time.time")
        mock()
        self.mocker.result(0.0)
        mock()
        self.mocker.result(12.345)
        mock()
        self.mocker.result(12.345)
        self.mocker.replay()

        recorder = PayloadRecorder(None)

        payload_name_1 = recorder.get_payload_filename()
        payload_name_2 = recorder.get_payload_filename()

        self.assertEqual("12.345", payload_name_1)
        self.assertEqual("12.346", payload_name_2)

    def test_save(self):
        """L{PayloadRecorder.save} should save the payload to the filesystem.
        """
        path = self.makeDir()
        recorder = PayloadRecorder(path)

        def static_filename():
            return "filename"
        recorder.get_payload_filename = static_filename
        recorder.save("payload data")
        file_path = os.path.join(path, static_filename())
        self.assertEqual("payload data", read_file(file_path))

    def test_create_destination_dir(self):
        """
        L{PayloadRecorder} should create the destination directory if it does
        not exist.
        """
        path = self.makeDir()
        os.rmdir(path)
        PayloadRecorder(path)
        self.assertTrue(os.path.isdir(path))

    def test_delete_old_payloads(self):
        """
        L{PayloadRecorder} should remove all files from the destination
        directory before writing new files.
        """
        path = self.makeDir()
        create_file(os.path.join(path, "one"), "one")
        create_file(os.path.join(path, "two"), "two")
        PayloadRecorder(path)
        self.assertEqual([], os.listdir(path))
