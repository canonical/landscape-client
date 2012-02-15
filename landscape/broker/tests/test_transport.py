import os

from landscape import VERSION
from landscape.broker.transport import HTTPTransport, PayloadRecorder
from landscape.configuration import (
    fetch_base64_ssl_public_certificate, print_text)
from landscape.broker.config import BrokerConfiguration
from landscape.broker.dnslookup import discover_server
from landscape.lib.fetch import fetch, PyCurlError
from landscape.lib.fs import create_file, read_file
from landscape.lib import bpickle
from landscape.tests.mocker import ANY

from landscape.tests.helpers import (
    LandscapeTest, LogKeeperHelper, MockerTestCase)

from twisted.web import server, resource
from twisted.internet import reactor
from twisted.internet.threads import blockingCallFromThread
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
        self.config_filename = self.makeFile("[client]\n")
        self.config = BrokerConfiguration()

    def tearDown(self):
        super(HTTPTransportTest, self).tearDown()
        for port in self.ports:
            port.stopListening()

    def test_get_url(self):
        url = "http://example/ooga"
        transport = HTTPTransport(None, url, self.config)
        self.assertEqual(transport.get_url(), url)

    def test_set_url(self):
        transport = HTTPTransport(None, "http://example/ooga", self.config)
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
            None, "http://localhost:%d/" % (port.getHost().port,), self.config)
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
            self.config, PUBKEY)
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
                                  % (port.getHost().port,), self.config,
                                  pubkey=PUBKEY)

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

        transport = HTTPTransport(None, "http://localhost", self.config,
                                  payload_recorder=recorder)

        transport._curl = fake_curl

        transport.exchange("pay load")

        file_path = os.path.join(path, static_filename())
        self.assertEqual("pay load", bpickle.loads(read_file(file_path)))

    def test_autodiscover_config_write_with_pubkey(self):
        """
        When server_autodiscover is set True, and the config.ssl_public_key
        already exists, ensure we update and write the config file with the
        discovered server urls.
        """
        discover_mock = self.mocker.replace(blockingCallFromThread,
            passthrough=False)
        discover_mock(None, discover_server, None, "", "")
        self.mocker.result("fakehostname")
        self.mocker.replay()

        self.config.load(["--config", self.config_filename,
                          "--ssl-public-key", PUBKEY,
                          "--server-autodiscover=true"])

        transport = HTTPTransport(None, self.config.url, self.config,
            pubkey=self.config.ssl_public_key,
            server_autodiscover=self.config.server_autodiscover)
        transport._curl = fake_curl

        # Validate appropriate initial config options
        self.assertEquals("https://landscape.canonical.com/message-system",
                          transport._url)
        self.assertEquals(PUBKEY, transport._pubkey)
        self.assertTrue(transport._server_autodiscover)

        transport.exchange("pay load")

        # Reload config to validate config.write() was called with changes
        self.config.load(["--config", self.config_filename])
        self.assertFalse(self.config.server_autodiscover)
        self.assertEquals("https://fakehostname/message-system",
                         self.config.url)
        self.assertEquals("http://fakehostname:8081/ping",
                         self.config.ping_url)
        self.assertEquals(PUBKEY, self.config.ssl_public_key)

    def test_autodiscover_config_write_without_pubkey(self):
        """
        When server_autodiscover is set True, and the config does not have an
        ssl_public_key defined. HTTPTransport should attempt to fetch the
        custom CA cert from the discovered server.
        """
        base64_cert = "base64:  MTIzNDU2Nzg5MA==" # encoded from 1234567890

        # To store the 'discovered' cert
        data_path = self.makeDir()

        key_filename = os.path.join(data_path,
            os.path.basename(self.config_filename + ".ssl_public_key"))


        discover_mock = self.mocker.replace(blockingCallFromThread,
            passthrough=False)
        discover_mock(None, discover_server, None, "", "")
        self.mocker.result("fakehostname")

        fetch_ca_mock = self.mocker.replace(
            fetch_base64_ssl_public_certificate, passthrough=False)

        fetch_ca_mock("fakehostname", on_info=ANY, on_error=ANY)
        self.mocker.result(base64_cert)

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Writing SSL CA certificate to %s..." % key_filename)
        
        self.mocker.replay()

        self.config.load(["--config", self.config_filename,
                          "--data-path", data_path,
                          "--server-autodiscover=true"])

        transport = HTTPTransport(None, self.config.url, self.config,
            server_autodiscover=self.config.server_autodiscover)
        transport._curl = fake_curl

        # Validate appropriate initial config options
        self.assertEquals(None, self.config.ssl_public_key)

        transport.exchange("pay load")

        # Reload config to validate config.write() was called with changes
        self.config.load(["--config", self.config_filename])
        self.assertFalse(self.config.server_autodiscover)
        self.assertEquals("https://fakehostname/message-system",
                         self.config.url)
        self.assertEquals("http://fakehostname:8081/ping",
                         self.config.ping_url)
        self.assertEquals(key_filename, self.config.ssl_public_key)
        self.assertEqual("1234567890", open(key_filename, "r").read())
    
    def test_exchange_works_without_payload_recording(self):
        """
        When C{HTTPTransport} is configured without a payload recorder,
        exchanges with the server should still complete.
        """
        transport = HTTPTransport(None, "http://localhost", self.config)
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
