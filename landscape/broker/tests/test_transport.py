import os
import shutil

from landscape import VERSION
from landscape.broker.transport import HTTPTransport, PayloadRecorder
from landscape.lib.fetch import PyCurlError
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
        transport = HTTPTransport(url)
        self.assertEquals(transport.get_url(), url)

    def test_set_url(self):
        transport = HTTPTransport("http://example/ooga")
        transport.set_url("http://example/message-system")
        self.assertEquals(transport.get_url(), "http://example/message-system")

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
            "http://localhost:%d/" % (port.getHost().port,))
        result = deferToThread(transport.exchange, "HI", computer_id="34",
                               message_api="X.Y")

        def got_result(ignored):
            self.assertEquals(r.request.received_headers["x-computer-id"],
                              "34")
            self.assertEquals(r.request.received_headers["user-agent"],
                              "landscape-client/%s" % (VERSION,))
            self.assertEquals(r.request.received_headers["x-message-api"],
                              "X.Y")
            self.assertEquals(bpickle.loads(r.content), "HI")
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
            "https://localhost:%d/" % (port.getHost().port,), PUBKEY)
        result = deferToThread(transport.exchange, "HI", computer_id="34",
                               message_api="X.Y")

        def got_result(ignored):
            self.assertEquals(r.request.received_headers["x-computer-id"],
                              "34")
            self.assertEquals(r.request.received_headers["user-agent"],
                              "landscape-client/%s" % (VERSION,))
            self.assertEquals(r.request.received_headers["x-message-api"],
                              "X.Y")
            self.assertEquals(bpickle.loads(r.content), "HI")
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
        transport = HTTPTransport("https://localhost:%d/"
                                  % (port.getHost().port,),
                                  pubkey=PUBKEY)

        result = deferToThread(transport.exchange, "HI", computer_id="34",
                               message_api="X.Y")

        def got_result(ignored):
            self.assertEquals(r.request, None)
            self.assertEquals(r.content, None)
            self.assertTrue("server certificate verification failed"
                            in self.logfile.getvalue())
        result.addCallback(got_result)
        return result


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
        recorder = PayloadRecorder(False, None)

        payload_name = recorder.get_payload_filename()

        self.assertEquals("12.346", payload_name)

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

        recorder = PayloadRecorder(False, None)

        payload_name_1 = recorder.get_payload_filename()
        payload_name_2 = recorder.get_payload_filename()

        self.assertEquals("12.345", payload_name_1)
        self.assertEquals("12.346", payload_name_2)

    def test_save_should_do_nothing_when_not_recording(self):
        """
        L{PayloadRecorder.save} should do nothing when recording is not
        enabled.
        """
        recorder = PayloadRecorder(False, None)
        recorder.get_payload_filename = self.fail

        recorder.save("the whales")

    def test_save(self):
        """L{PayloadRecorder.save} should save the payload to the filesystem.
        """
        recorder = PayloadRecorder(True, "./tmp")

        def static_filename():
            return "filename"
        recorder.get_payload_filename = static_filename

        recorder.save("payload data")

        self.assertEquals("payload data", file("./tmp/filename").read())
        shutil.rmtree("./tmp")

    def test_create_destination_dir(self):
        """
        L{PayloadRecorder._create_destination_dir} should create the
        destination directory.
        """
        mock = self.mocker.replace("os.path.exists")
        mock("/tmp/foo")
        self.mocker.result(False)

        mock = self.mocker.replace("os.mkdir")
        mock("/tmp/foo")
        self.mocker.result(True)

        self.mocker.replay()

        recorder = PayloadRecorder(False, None)

        recorder._create_destination_dir("/tmp/foo")

    def test_create_destination_dir_existing(self):
        """
        L{PayloadRecorder._create_destination_dir} should do nothing when the
        destination directory exists.
        """

        mock = self.mocker.replace("os.path.exists")
        mock("/")
        self.mocker.result(True)
        self.mocker.replay()

        recorder = PayloadRecorder(False, None)

        recorder._create_destination_dir("/")

    def test_delete_old_payloads(self):
        """
        L{PayloadRecorder._delete_old_payloads} should remove all files from
        the destination directory.
        """
        mock = self.mocker.replace("os.listdir")
        mock("/tmp/somedir")
        self.mocker.result(["one", "two"])

        mock = self.mocker.replace("os.path.isfile")
        mock("/tmp/somedir/one")
        self.mocker.result(True)

        mock("/tmp/somedir/two")
        self.mocker.result(False)

        mock = self.mocker.replace("os.unlink")
        mock("/tmp/somedir/one")

        self.mocker.replay()

        recorder = PayloadRecorder(False, "/tmp/somedir")

        recorder._delete_old_payloads()
