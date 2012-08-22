from landscape.tests.helpers import LandscapeTest, FakeBrokerServiceHelper

from twisted.internet.defer import fail

from landscape.lib.bpickle import dumps
from landscape.lib.fetch import fetch
from landscape.broker.ping import PingClient, Pinger


class FakePageGetter(object):
    """An fake web client."""

    def __init__(self, response):
        self.response = response
        self.fetches = []

    def get_page(self, url, post, headers, data):
        """
        A method which is supposed to act like a limited version of
        L{landscape.lib.fetch.fetch}.

        Record attempts to get pages, and return a deferred with pre-cooked
        data.
        """
        self.fetches.append((url, post, headers, data))
        return dumps(self.response)

    def failing_get_page(self, url, post, headers, data):
        """
        A method which is supposed to act like a limited version of
        L{landscape.lib.fetch.fetch}.

        Record attempts to get pages, and return a deferred with pre-cooked
        data.
        """
        raise AssertionError("That's a failure!")


class PingClientTest(LandscapeTest):

    helpers = [FakeBrokerServiceHelper]

    def test_default_get_page(self):
        """
        The C{get_page} argument to L{PingClient} should be optional, and
        default to L{twisted.web.client.getPage}.
        """
        client = PingClient(None, None, None)
        self.assertEqual(client.get_page, fetch)

    def test_ping(self):
        """
        L{PingClient} should be able to send a web request to a specified URL
        about a particular insecure ID.
        """
        client = FakePageGetter(None)
        self.broker_service.identity.insecure_id = 10
        url = "http://localhost/ping"
        pinger = PingClient(self.broker_service.reactor, url,
                            self.broker_service.identity,
                            get_page=client.get_page)
        pinger.ping()
        self.assertEqual(
            client.fetches,
            [(url, True, {"Content-Type": "application/x-www-form-urlencoded"},
              "insecure_id=10")])

    def test_ping_no_insecure_id(self):
        """
        If a L{PingClient} does not have an insecure-id yet, then the ping
        should not happen.
        """
        client = FakePageGetter(None)
        url = "http://localhost/ping"
        pinger = PingClient(self.broker_service.reactor,
                            url, self.broker_service.identity,
                            get_page=client.get_page)
        d = pinger.ping()
        d.addCallback(self.assertEqual, False)
        self.assertEqual(client.fetches, [])

    def test_respond(self):
        """
        The L{PingClient.ping} fire the Deferred it returns with True if the
        web request indicates that the computer has messages.
        """
        self.broker_service.identity.insecure_id = 23
        client = FakePageGetter({"messages": True})
        pinger = PingClient(self.broker_service.reactor,
                            None, self.broker_service.identity,
                            get_page=client.get_page)
        d = pinger.ping()
        d.addCallback(self.assertEqual, True)

    def test_errback(self):
        """
        If a L{PingClient} does not have an insecure-id yet, then the ping
        should not happen.
        """
        self.broker_service.identity.insecure_id = 23
        client = FakePageGetter(None)
        url = "http://localhost/ping"
        pinger = PingClient(self.broker_service.reactor,
                            url, self.broker_service.identity,
                            get_page=client.failing_get_page)
        d = pinger.ping()
        failures = []

        def errback(failure):
            failures.append(failure)
        d.addErrback(errback)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].getErrorMessage(), "That's a failure!")
        self.assertEqual(failures[0].type, AssertionError)


class PingerTest(LandscapeTest):

    helpers = [FakeBrokerServiceHelper]

    # Tell the Plugin helper to not add a MessageExchange plugin, to interfere
    # with our code which asserts stuff about when *our* plugin fires
    # exchanges.
    install_exchanger = False

    def setUp(self):
        super(PingerTest, self).setUp()

        class MockConfig(object):
            ping_url = "http://localhost:8081/whatever"
            ping_interval = 10
            
            def write(self):
                pass
        
        self.config = MockConfig()
        self.page_getter = FakePageGetter(None)

        def factory(reactor, url, insecure_id):
            return PingClient(reactor, url, insecure_id,
                              get_page=self.page_getter.get_page)
        self.pinger = Pinger(self.broker_service.reactor,
                             self.broker_service.identity,
                             self.broker_service.exchanger,
                             self.config, ping_client_factory=factory)

    def test_default_ping_client(self):
        """
        The C{ping_client_factory} argument to L{Pinger} should be optional,
        and default to L{PingClient}.
        """
        self.config.ping_url = "http://foo.com/"
        pinger = Pinger(self.broker_service.reactor,
                        self.broker_service.identity,
                        self.broker_service.exchanger,
                        self.config)
        self.assertEqual(pinger.ping_client_factory, PingClient)

    def test_occasional_ping(self):
        """
        The L{Pinger} should be able to occasionally ask if there are
        messages.
        """
        self.pinger.start()
        self.broker_service.identity.insecure_id = 23
        self.broker_service.reactor.advance(9)
        self.assertEqual(len(self.page_getter.fetches), 0)
        self.broker_service.reactor.advance(1)
        self.assertEqual(len(self.page_getter.fetches), 1)

    def test_load_insecure_id(self):
        """
        If the insecure-id has already been saved when the plugin is
        registered, it should immediately start pinging.
        """
        self.broker_service.identity.insecure_id = 42
        self.pinger.start()
        self.broker_service.reactor.advance(10)
        self.assertEqual(len(self.page_getter.fetches), 1)

    def test_response(self):
        """
        When a ping indicates there are messages, an exchange should occur.
        """
        self.pinger.start()
        self.broker_service.identity.insecure_id = 42
        self.page_getter.response = {"messages": True}

        # 70 = ping delay + urgent exchange delay
        self.broker_service.reactor.advance(70)

        self.assertEqual(len(self.broker_service.transport.payloads), 1)

    def test_negative_response(self):
        """
        When a ping indicates there are no messages, no exchange should occur.
        """
        self.pinger.start()
        self.broker_service.identity.insecure_id = 42
        self.page_getter.response = {"messages": False}
        self.broker_service.reactor.advance(10)
        self.assertEqual(len(self.broker_service.transport.payloads), 0)

    def test_ping_error(self):
        """
        When the web interaction fails for some reason, a message
        should be logged.
        """
        self.log_helper.ignore_errors(ZeroDivisionError)
        self.broker_service.identity.insecure_id = 42

        class BadPingClient(object):
            def __init__(self, *args, **kwargs):
                self.url = args[1]

            def ping(self):
                return fail(ZeroDivisionError("Couldn't fetch page"))

        self.config.ping_url = "http://foo.com/"
        pinger = Pinger(self.broker_service.reactor,
                        self.broker_service.identity,
                        self.broker_service.exchanger,
                        self.config,
                        ping_client_factory=BadPingClient)
        pinger.start()

        self.broker_service.reactor.advance(30)

        log = self.logfile.getvalue()
        self.assertTrue("Error contacting ping server at "
                        "http://foo.com/" in log,
                        log)
        self.assertTrue("ZeroDivisionError" in log)
        self.assertTrue("Couldn't fetch page" in log)

    def test_get_interval(self):
        self.assertEqual(self.pinger.get_interval(), 10)

    def test_set_intervals_handling(self):
        self.pinger.start()

        self.broker_service.reactor.fire("message",
                                         {"type": "set-intervals", "ping": 73})
        self.assertEqual(self.pinger.get_interval(), 73)

        # The server may set specific intervals only, not including the ping.
        self.broker_service.reactor.fire("message", {"type": "set-intervals"})
        self.assertEqual(self.pinger.get_interval(), 73)

        self.broker_service.identity.insecure_id = 23
        self.broker_service.reactor.advance(72)
        self.assertEqual(len(self.page_getter.fetches), 0)
        self.broker_service.reactor.advance(1)
        self.assertEqual(len(self.page_getter.fetches), 1)

    def test_get_url(self):
        self.assertEqual(self.pinger.get_url(),
                         "http://localhost:8081/whatever")

    def test_set_url(self):
        url = "http://example.com/mysuperping"
        self.pinger.set_url(url)
        self.pinger.start()
        self.broker_service.identity.insecure_id = 23
        self.broker_service.reactor.advance(10)
        self.assertEqual(self.page_getter.fetches[0][0], url)

    def test_set_url_after_start(self):
        url = "http://example.com/mysuperping"
        self.pinger.start()
        self.pinger.set_url(url)
        self.broker_service.identity.insecure_id = 23
        self.broker_service.reactor.advance(10)
        self.assertEqual(self.page_getter.fetches[0][0], url)
