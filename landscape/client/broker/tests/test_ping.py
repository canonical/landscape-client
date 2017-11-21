from landscape.client.tests.helpers import LandscapeTest

from twisted.internet.defer import fail

from landscape.lib import bpickle
from landscape.lib.fetch import fetch
from landscape.lib.testing import FakeReactor
from landscape.client.broker.ping import PingClient, Pinger
from landscape.client.broker.tests.helpers import ExchangeHelper


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
        return bpickle.dumps(self.response)

    def failing_get_page(self, url, post, headers, data):
        """
        A method which is supposed to act like a limited version of
        L{landscape.lib.fetch.fetch}.

        Record attempts to get pages, and return a deferred with pre-cooked
        data.
        """
        raise AssertionError("That's a failure!")


class PingClientTest(LandscapeTest):

    def setUp(self):
        super(PingClientTest, self).setUp()
        self.reactor = FakeReactor()

    def test_default_get_page(self):
        """
        The C{get_page} argument to L{PingClient} should be optional, and
        default to L{twisted.web.client.getPage}.
        """
        client = PingClient(self.reactor)
        self.assertEqual(client.get_page, fetch)

    def test_ping(self):
        """
        L{PingClient} should be able to send a web request to a specified URL
        about a particular insecure ID.
        """
        client = FakePageGetter(None)
        url = "http://localhost/ping"
        insecure_id = 10
        pinger = PingClient(self.reactor, get_page=client.get_page)
        pinger.ping(url, insecure_id)
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
        pinger = PingClient(self.reactor, get_page=client.get_page)
        d = pinger.ping("http://ping/url", None)
        d.addCallback(self.assertEqual, False)
        self.assertEqual(client.fetches, [])

    def test_respond(self):
        """
        The L{PingClient.ping} fire the Deferred it returns with True if the
        web request indicates that the computer has messages.
        """
        client = FakePageGetter({"messages": True})
        pinger = PingClient(self.reactor, get_page=client.get_page)
        d = pinger.ping("http://ping/url", 23)
        d.addCallback(self.assertEqual, True)

    def test_errback(self):
        """
        If the HTTP request fails the deferred returned by L{PingClient.ping}
        fires back with an error.
        """
        client = FakePageGetter(None)
        pinger = PingClient(self.reactor, get_page=client.failing_get_page)
        d = pinger.ping("http://ping/url", 23)
        failures = []

        def errback(failure):
            failures.append(failure)
        d.addErrback(errback)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].getErrorMessage(), "That's a failure!")
        self.assertEqual(failures[0].type, AssertionError)


class PingerTest(LandscapeTest):

    helpers = [ExchangeHelper]

    # Tell the Plugin helper to not add a MessageExchange plugin, to interfere
    # with our code which asserts stuff about when *our* plugin fires
    # exchanges.
    install_exchanger = False

    def setUp(self):
        super(PingerTest, self).setUp()
        self.page_getter = FakePageGetter(None)

        def factory(reactor):
            return PingClient(reactor, get_page=self.page_getter.get_page)

        self.config.ping_url = "http://localhost:8081/whatever"
        self.config.ping_interval = 10

        self.pinger = Pinger(self.reactor,
                             self.identity,
                             self.exchanger,
                             self.config,
                             ping_client_factory=factory)

    def test_default_ping_client(self):
        """
        The C{ping_client_factory} argument to L{Pinger} should be optional,
        and default to L{PingClient}.
        """
        pinger = Pinger(self.reactor,
                        self.identity,
                        self.exchanger,
                        self.config)
        self.assertEqual(pinger.ping_client_factory, PingClient)

    def test_occasional_ping(self):
        """
        The L{Pinger} should be able to occasionally ask if there are
        messages.
        """
        self.pinger.start()
        self.identity.insecure_id = 23
        self.reactor.advance(9)
        self.assertEqual(len(self.page_getter.fetches), 0)
        self.reactor.advance(1)
        self.assertEqual(len(self.page_getter.fetches), 1)

    def test_load_insecure_id(self):
        """
        If the insecure-id has already been saved when the plugin is
        registered, it should immediately start pinging.
        """
        self.identity.insecure_id = 42
        self.pinger.start()
        self.reactor.advance(10)
        self.assertEqual(len(self.page_getter.fetches), 1)

    def test_response(self):
        """
        When a ping indicates there are messages, an exchange should occur.
        """
        self.pinger.start()
        self.identity.insecure_id = 42
        self.page_getter.response = {"messages": True}

        # 70 = ping delay + urgent exchange delay
        self.reactor.advance(70)

        self.assertEqual(len(self.transport.payloads), 1)

    def test_negative_response(self):
        """
        When a ping indicates there are no messages, no exchange should occur.
        """
        self.pinger.start()
        self.identity.insecure_id = 42
        self.page_getter.response = {"messages": False}
        self.reactor.advance(10)
        self.assertEqual(len(self.transport.payloads), 0)

    def test_ping_error(self):
        """
        When the web interaction fails for some reason, a message
        should be logged.
        """
        self.log_helper.ignore_errors(ZeroDivisionError)
        self.identity.insecure_id = 42

        class BadPingClient(object):
            def __init__(self, *args, **kwargs):
                pass

            def ping(self, url, secure_id):
                self.url = url
                return fail(ZeroDivisionError("Couldn't fetch page"))

        self.config.ping_url = "http://foo.com/"
        pinger = Pinger(self.reactor,
                        self.identity,
                        self.exchanger,
                        self.config,
                        ping_client_factory=BadPingClient)
        pinger.start()

        self.reactor.advance(30)

        log = self.logfile.getvalue()
        self.assertIn("Error contacting ping server at http://foo.com/", log)
        self.assertIn("ZeroDivisionError", log)
        self.assertIn("Couldn't fetch page", log)

    def test_get_interval(self):
        self.assertEqual(self.pinger.get_interval(), 10)

    def test_set_intervals_handling(self):
        self.pinger.start()

        self.reactor.fire("message", {"type": "set-intervals", "ping": 73})
        self.assertEqual(self.pinger.get_interval(), 73)

        # The server may set specific intervals only, not including the ping.
        self.reactor.fire("message", {"type": "set-intervals"})
        self.assertEqual(self.pinger.get_interval(), 73)

        self.identity.insecure_id = 23
        self.reactor.advance(72)
        self.assertEqual(len(self.page_getter.fetches), 0)
        self.reactor.advance(1)
        self.assertEqual(len(self.page_getter.fetches), 1)

    def test_get_url(self):
        self.assertEqual(self.pinger.get_url(),
                         "http://localhost:8081/whatever")

    def test_config_url(self):
        """
        The L{Pinger} uses the ping URL set in the given configuration.
        """
        self.identity.insecure_id = 23
        url = "http://example.com/mysuperping"
        self.config.ping_url = url
        self.pinger.start()
        self.reactor.advance(10)
        self.assertEqual(self.page_getter.fetches[0][0], url)

    def test_reschedule(self):
        """
        Each time a ping is completed the L{Pinger} schedules a new ping using
        the current ping interval.
        """
        self.identity.insecure_id = 23
        self.pinger.start()
        self.reactor.advance(10)
        self.assertEqual(1, len(self.page_getter.fetches))
        self.reactor.advance(10)
        self.assertEqual(2, len(self.page_getter.fetches))

    def test_reschedule_with_ping_interval_change(self):
        """
        If the ping interval changes, new pings will be scheduled accordingly.
        """
        self.identity.insecure_id = 23
        self.pinger.start()
        self.reactor.advance(5)
        # Simulate interval changing in the meantime
        self.config.ping_interval = 20
        self.reactor.advance(5)
        self.assertEqual(1, len(self.page_getter.fetches))
        # The new interval is 20, so after only 10 seconds nothing happens
        self.reactor.advance(10)
        self.assertEqual(1, len(self.page_getter.fetches))
        # After another 10 seconds we reach the 20 seconds interval and the
        # ping is triggered
        self.reactor.advance(10)
        self.assertEqual(2, len(self.page_getter.fetches))

    def test_change_url_after_start(self):
        """
        If the C{ping_url} set in the configuration is changed after the
        pinger has started, the target HTTP url will adjust accordingly.
        """
        url = "http://example.com/mysuperping"
        self.pinger.start()
        self.config.ping_url = url
        self.identity.insecure_id = 23
        self.reactor.advance(10)
        self.assertEqual(self.page_getter.fetches[0][0], url)

    def test_ping_doesnt_ping_if_stopped(self):
        """If the L{Pinger} is stopped, no pings are performed."""
        self.pinger.start()
        self.pinger.stop()
        self.reactor.advance(10)
        self.assertEqual([], self.page_getter.fetches)
