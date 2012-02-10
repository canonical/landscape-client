from landscape.tests.helpers import LandscapeTest
from landscape.broker.dnslookup import (lookup_server_record, lookup_hostname,
                                        discover_server)

from twisted.internet import defer
from twisted.names import dns
from twisted.names.error import ResolverError


class FakeResolverResult(object):
    """
    A fake resolver result returned by L{FakeResolver}.

    @param type: The result type L{twisted.names.dns.SRV}
    @param payload: The result contents
    """
    def __init__(self):
        self.type = None

        class Payload(object):
            """
            A payload result returned by fake resolver.

            @param target: The result of the lookup
            """
            def __init__(self):
                self.target = ""

        class Target(object):
            """
            A payload target returned by fake resolver.

            @param name: The name contained by the target.
            """
            def __init__(self):
                self.name = ""

        self.payload = Payload()
        self.payload.target = Target()


class FakeResolver(object):
    """
    A fake resolver that mimics L{twisted.names.client.Resolver}
    """
    def __init__(self):
        self.results = None
        self.name = None
        self.queried = None

    def lookupService(self, arg1):
        self.queried = arg1
        deferred = defer.Deferred()
        deferred.callback(self.results)
        return deferred

    def getHostByName(self, arg1):
        self.queried = arg1
        deferred = defer.Deferred()
        deferred.callback(self.name)
        return deferred


class BadResolver(object):
    """
    A resolver that mimics L{twisted.names.client.Resolver} and always returns
    an error.
    """
    def lookupService(self, arg1):
        deferred = defer.Deferred()
        deferred.errback(ResolverError("Couldn't connect"))
        return deferred

    def getHostByName(self, arg1):
        deferred = defer.Deferred()
        deferred.errback(ResolverError("Couldn't connect"))
        return deferred


class DnsSrvLookupTest(LandscapeTest):
    def test_with_server_found(self):
        """
        Looking up a DNS SRV record should return the result of the lookup.
        """
        fake_result = FakeResolverResult()
        fake_result.type = dns.SRV
        fake_result.payload.target.name = "a.b.com"
        fake_resolver = FakeResolver()
        fake_resolver.results = [[fake_result]]
        query_string = "_landscape._tcp.mylandscapehost.com"

        def check(result):
            self.assertEqual(fake_resolver.queried, query_string)
            self.assertEqual("a.b.com", result)

        d = lookup_server_record(fake_resolver, query_string)
        d.addCallback(check)
        return d

    def test_with_server_not_found(self):
        """
        Looking up a DNS SRV record and finding nothing exists should return
        an empty string.
        """
        fake_resolver = FakeResolver()
        fake_resolver.results = [[]]

        def check(result):
            self.assertEqual("", result)

        d = lookup_server_record(fake_resolver,
                                 "_landscape._tcp.mylandscapehost.com")
        d.addCallback(check)
        return d

    def test_with_resolver_error(self):
        """A resolver error triggers error handling code."""
        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.info")
        logging_mock("SRV lookup of _landscape._tcp.mylandscapehost.com "
                     "failed.")
        self.mocker.replay()

        d = lookup_server_record(BadResolver(),
                                 "_landscape._tcp.mylandscapehost.com")
        self.assertFailure(d, ResolverError)
        return d


class DnsNameLookupTest(LandscapeTest):
    def test_with_name_found(self):
        """
        Looking up a DNS name record should return the result of the lookup.
        """
        fake_resolver = FakeResolver()
        fake_resolver.name = "a.b.com"
        query_string = "landscape.localdomain"

        def check(result):
            self.assertEqual(fake_resolver.queried, query_string)
            self.assertEqual("a.b.com", result)

        d = lookup_hostname(None, fake_resolver, query_string)
        d.addCallback(check)
        return d

    def test_with_name_not_found(self):
        """
        Looking up a DNS NAME record and not finding a result should return
        None.
        """
        fake_resolver = FakeResolver()
        fake_resolver.name = None

        def check(result):
            self.assertEqual(None, result)

        d = lookup_hostname(None, fake_resolver, "landscape.localdomain")
        d.addCallback(check)
        return d

    def test_with_resolver_error(self):
        """A resolver error triggers error handling code."""
        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.info")
        logging_mock("Name lookup of landscape.localdomain failed.")
        self.mocker.replay()

        d = lookup_hostname(None, BadResolver(), "landscape.localdomain")
        self.assertFailure(d, ResolverError)
        return d


class DiscoverServerTest(LandscapeTest):
    def test_srv_lookup(self):
        """The DNS name of the server is found using a SRV lookup."""
        fake_result = FakeResolverResult()
        fake_result.type = dns.SRV
        fake_result.payload.target.name = "a.b.com"
        fake_resolver = FakeResolver()
        fake_resolver.results = [[fake_result]]

        d = discover_server(fake_resolver)

        def check(result):
            self.assertEqual("a.b.com", result)

        d.addCallback(check)
        return d

    def test_a_name_lookup(self):
        """The DNS name of the server is found using an A name lookup."""
        fake_resolver = FakeResolver()
        fake_resolver.name = "x.y.com"

        d = discover_server(fake_resolver)

        def check(result):
            self.assertEqual("x.y.com", result)

        d.addCallback(check)
        return d

    def test_failed_lookup(self):
        """A resolver error is returned when server autodiscovery fails."""
        d = lookup_server_record(BadResolver(), "landscape.localdomain")
        self.assertFailure(d, ResolverError)
        return d
