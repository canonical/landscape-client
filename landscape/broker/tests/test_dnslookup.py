from landscape.tests.helpers import LandscapeTest
from landscape.broker.dnslookup import lookup_server_record, lookup_hostname

from twisted.internet import defer
from twisted.names import dns


class FakeResolverResult(object):
    def __init__(self):
        self.type = None

        class Payload(object):

            def __init__(self):
                self.target = ""
        self.payload = Payload()


class FakeResolver(object):
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


class DnsSrvLookupTest(LandscapeTest):
    def test_with_server_found(self):
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
        fake_resolver = FakeResolver()
        fake_resolver.results = [[]]

        def check(result):
            self.assertEquals("", result)

        d = lookup_server_record(fake_resolver)
        d.addCallback(check)
        return d


class DnsNameLookupTest(LandscapeTest):
    def test_with_name_found(self):
        fake_resolver = FakeResolver()
        fake_resolver.name = "a.b.com"

        def check(result):
            self.assertEquals("a.b.com", result)

        d = lookup_hostname(None, fake_resolver)
        d.addCallback(check)
        return d

    def test_with_name_not_found(self):
        fake_resolver = FakeResolver()
        fake_resolver.name = None

        def check(result):
            self.assertEquals(None, result)

        d = lookup_hostname(None, fake_resolver)
        d.addCallback(check)
        return d
