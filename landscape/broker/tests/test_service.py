import os

from landscape.tests.helpers import LandscapeTest
from landscape.broker.tests.helpers import BrokerConfigurationHelper
from landscape.broker.service import BrokerService
from landscape.broker.transport import HTTPTransport
from landscape.broker.amp import RemoteBrokerConnector
from landscape.reactor import FakeReactor

from twisted.internet import reactor, defer
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
    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super(DnsSrvLookupTest, self).setUp()
        self.service = BrokerService(self.config)

    def test_with_server_found(self):
        fake_result = FakeResolverResult()
        fake_result.type = dns.SRV
        fake_result.payload.target = "a.b.com"
        fake_resolver = FakeResolver()
        fake_resolver.results = [[fake_result]]

        def check(result):
            self.assertEquals("a.b.com", result)

        d = self.service._lookup_server_record(fake_resolver)
        d.addCallback(check)
        return d

    def test_with_server_not_found(self):
        fake_resolver = FakeResolver()
        fake_resolver.results = [[]]

        def check(result):
            self.assertEquals("", result)

        d = self.service._lookup_server_record(fake_resolver)
        d.addCallback(check)
        return d


class DnsNameLookupTest(LandscapeTest):
    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super(DnsNameLookupTest, self).setUp()
        self.service = BrokerService(self.config)

    def test_with_name_found(self):
        fake_resolver = FakeResolver()
        fake_resolver.name = "a.b.com"

        def check(result):
            self.assertEquals("a.b.com", result)

        d = self.service._lookup_hostname(None, fake_resolver)
        d.addCallback(check)
        return d

    def test_with_name_not_found(self):
        fake_resolver = FakeResolver()
        fake_resolver.name = None

        def check(result):
            self.assertEquals(None, result)

        d = self.service._lookup_hostname(None, fake_resolver)
        d.addCallback(check)
        return d


class BrokerServiceTest(LandscapeTest):

    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super(BrokerServiceTest, self).setUp()
        self.service = BrokerService(self.config)

    def test_persist(self):
        """
        A L{BrokerService} instance has a proper C{persist} attribute.
        """
        self.assertEqual(
            self.service.persist.filename,
            os.path.join(self.config.data_path, "broker.bpickle"))

    def test_transport(self):
        """
        A L{BrokerService} instance has a proper C{transport} attribute.
        """
        self.assertTrue(isinstance(self.service.transport, HTTPTransport))
        self.assertEqual(self.service.transport.get_url(), self.config.url)

    def test_message_store(self):
        """
        A L{BrokerService} instance has a proper C{message_store} attribute.
        """
        self.assertEqual(self.service.message_store.get_accepted_types(), ())

    def test_identity(self):
        """
        A L{BrokerService} instance has a proper C{identity} attribute.
        """
        self.assertEqual(self.service.identity.account_name, "some_account")

    def test_exchanger(self):
        """
        A L{BrokerService} instance has a proper C{exchanger} attribute.
        """
        self.assertEqual(self.service.exchanger.get_exchange_intervals(),
                         (60, 900))

    def test_pinger(self):
        """
        A L{BrokerService} instance has a proper C{pinger} attribute. Its
        interval value is configured with the C{ping_interval} value.
        """
        self.assertEqual(self.service.pinger.get_url(), self.config.ping_url)
        self.assertEqual(30, self.service.pinger.get_interval())
        self.config.ping_interval = 20
        service = BrokerService(self.config)
        self.assertEqual(20, service.pinger.get_interval())

    def test_registration(self):
        """
        A L{BrokerService} instance has a proper C{registration} attribute.
        """
        self.assertEqual(self.service.registration.should_register(), False)

    def test_wb_exit(self):
        """
        A L{BrokerService} instance registers an handler for the C{post-exit}
        event that makes the Twisted reactor stop.
        """
        reactor.stop = self.mocker.mock()
        reactor.stop()
        self.mocker.replay()
        self.service.reactor.fire("post-exit")

    def test_start_stop(self):
        """
        The L{BrokerService.startService} method makes the process start
        listening to the broker socket, and starts the L{Exchanger} and
        the L{Pinger} as well.
        """
        self.service.exchanger.start = self.mocker.mock()
        self.service.exchanger.start()
        self.service.pinger.start = self.mocker.mock()
        self.service.pinger.start()
        self.service.exchanger.stop = self.mocker.mock()
        self.service.exchanger.stop()
        self.mocker.replay()
        self.service.startService()
        reactor = FakeReactor()
        connector = RemoteBrokerConnector(reactor, self.config)
        connected = connector.connect()
        connected.addCallback(lambda remote: remote.get_server_uuid())
        connected.addCallback(lambda x: connector.disconnect())
        connected.addCallback(lambda x: self.service.stopService())
        connected.addCallback(lambda x: self.service.port.stopListening())
        return connected
