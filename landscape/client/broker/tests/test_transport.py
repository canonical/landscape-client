import os

from twisted.internet import reactor
from twisted.internet.ssl import DefaultOpenSSLContextFactory
from twisted.internet.threads import deferToThread
from twisted.web import resource
from twisted.web import server

from landscape import VERSION
from landscape.client.broker.transport import HTTPTransport
from landscape.client.tests.helpers import LandscapeTest
from landscape.lib import bpickle
from landscape.lib.fetch import PyCurlError
from landscape.lib.testing import LogKeeperHelper


def sibpath(path):
    return os.path.abspath(os.path.join(os.path.dirname(__file__), path))


PRIVKEY = sibpath("private.ssl")
PUBKEY = sibpath("public.ssl")
BADPRIVKEY = sibpath("badprivate.ssl")
BADPUBKEY = sibpath("badpublic.ssl")


class DataCollectingResource(resource.Resource):

    request = content = None

    def getChild(self, request, name):  # noqa: N802
        return self

    def render(self, request):
        self.request = request
        self.content = request.content.read()
        return bpickle.dumps("Great.")


class HTTPTransportTest(LandscapeTest):

    helpers = [LogKeeperHelper]

    def setUp(self):
        super().setUp()
        self.ports = []

    def tearDown(self):
        super().tearDown()
        for port in self.ports:
            port.stopListening()

    def request_with_payload(self, payload):
        resource = DataCollectingResource()
        port = reactor.listenTCP(
            0,
            server.Site(resource),
            interface="127.0.0.1",
        )
        self.ports.append(port)
        transport = HTTPTransport(
            None,
            f"http://localhost:{port.getHost().port:d}/",
        )
        result = deferToThread(
            transport.exchange,
            payload,
            computer_id="34",
            exchange_token=b"abcd-efgh",
            message_api=b"X.Y",
        )

        def got_result(ignored):
            try:
                get_header = resource.request.requestHeaders.getRawHeaders
            except AttributeError:
                # For backwards compatibility with Twisted versions
                # without requestHeaders
                def get_header(header):
                    return [resource.request.received_headers[header]]

            self.assertEqual(get_header("x-computer-id"), ["34"])
            self.assertEqual(get_header("x-exchange-token"), ["abcd-efgh"])
            self.assertEqual(
                get_header("user-agent"),
                [f"landscape-client/{VERSION}"],
            )
            self.assertEqual(get_header("x-message-api"), ["X.Y"])
            self.assertEqual(bpickle.loads(resource.content), payload)

        result.addCallback(got_result)
        return result

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
        return self.request_with_payload(payload="HI")

    def test_request_data_unicode(self):
        """
        When a payload contains unicode characters they are properly handled
        by bpickle.
        """
        return self.request_with_payload(payload="проба")

    def test_ssl_verification_positive(self):
        """
        The client transport should complete an upload of messages to
        a host which provides SSL data which can be verified by the
        public key specified.
        """
        resource = DataCollectingResource()
        context_factory = DefaultOpenSSLContextFactory(PRIVKEY, PUBKEY)
        port = reactor.listenSSL(
            0,
            server.Site(resource),
            context_factory,
            interface="127.0.0.1",
        )
        self.ports.append(port)
        transport = HTTPTransport(
            None,
            f"https://localhost:{port.getHost().port:d}/",
            PUBKEY,
        )
        result = deferToThread(
            transport.exchange,
            "HI",
            computer_id="34",
            message_api=b"X.Y",
        )

        def got_result(ignored):
            try:
                get_header = resource.request.requestHeaders.getRawHeaders
            except AttributeError:
                # For backwards compatibility with Twisted versions
                # without requestHeaders
                def get_header(header):
                    return [resource.request.received_headers[header]]

            self.assertEqual(get_header("x-computer-id"), ["34"])
            self.assertEqual(
                get_header("user-agent"),
                [f"landscape-client/{VERSION}"],
            )
            self.assertEqual(get_header("x-message-api"), ["X.Y"])
            self.assertEqual(bpickle.loads(resource.content), "HI")

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
        context_factory = DefaultOpenSSLContextFactory(BADPRIVKEY, BADPUBKEY)
        port = reactor.listenSSL(
            0,
            server.Site(r),
            context_factory,
            interface="127.0.0.1",
        )
        self.ports.append(port)
        transport = HTTPTransport(
            None,
            f"https://localhost:{port.getHost().port:d}/",
            pubkey=PUBKEY,
        )

        result = deferToThread(
            transport.exchange,
            "HI",
            computer_id="34",
            message_api=b"X.Y",
        )

        def got_result(failure):
            self.assertIs(r.request, None)
            self.assertIs(r.content, None)
            self.assertEqual(failure.value.error_code, 60)

        result.addErrback(got_result)
        return result
