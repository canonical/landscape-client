from landscape.tests.helpers import LandscapeTest
from landscape.broker.dnslookup import lookup_server_record, lookup_hostname

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
        self.payload = Payload()


class FakeResolver(object):
    """
    A fake resolver that mimics L{twisted.names.client.Resolver}
    """
    def __init__(self):
        self.results = None
        self.name = None

    def lookupService(self, arg1):
        deferred = defer.Deferred()
        deferred.callback(self.results)
        return deferred

    def getHostByName(self, arg1):
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
        fake_result.payload.target = "a.b.com"
        fake_resolver = FakeResolver()
        fake_resolver.results = [[fake_result]]

        def check(result):
            self.assertEquals("a.b.com", result)

        d = lookup_server_record(fake_resolver)
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
            self.assertEquals("", result)

        d = lookup_server_record(fake_resolver)
        d.addCallback(check)
        return d

    def test_with_resolver_error(self):
        """A resolver error triggers error handling code."""
        bad_resolver = BadResolver()

        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.info")
        logging_mock("SRV lookup of _landscape._tcp.mylandscapehost.com "
                     "failed.")
        self.mocker.replay()

        error_result = []
        def check_error(result):
            error_result.append(result.value)

        d = lookup_server_record(bad_resolver)
        d.addErrback(check_error)

        self.assertIsInstance(error_result[0], ResolverError)


class DnsNameLookupTest(LandscapeTest):
    def test_with_name_found(self):
        """
        Looking up a DNS name record should return the result of the lookup.
        """
        fake_resolver = FakeResolver()
        fake_resolver.name = "a.b.com"

        def check(result):
            self.assertEquals("a.b.com", result)

        d = lookup_hostname(None, fake_resolver)
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
            self.assertEquals(None, result)

        d = lookup_hostname(None, fake_resolver)
        d.addCallback(check)
        return d

    def test_with_resolver_error(self):
        """A resolver error triggers error handling code."""
        bad_resolver = BadResolver()

        # The failure should be properly logged
        logging_mock = self.mocker.replace("logging.info")
        logging_mock("Name lookup of landscape.localdomain failed.")
        self.mocker.replay()

        error_result = []
        def check_error(result):
            error_result.append(result.value)

        d = lookup_hostname(None, bad_resolver)
        d.addErrback(check_error)

        self.assertIsInstance(error_result[0], ResolverError)
