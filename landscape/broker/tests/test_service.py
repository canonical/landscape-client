import os

from twisted.internet import reactor

from landscape.tests.helpers import LandscapeTest
from landscape.broker.tests.helpers import BrokerConfigurationHelper
from landscape.broker.service import BrokerService
from landscape.broker.transport import HTTPTransport
from landscape.broker.amp import RemoteBrokerConnector
from landscape.reactor import FakeReactor


class BrokerServiceTest(LandscapeTest):

    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super(BrokerServiceTest, self).setUp()
        self.service = BrokerService(self.config)

    def test_persist(self):
        """
        A L{BrokerService} instance has a proper C{persist} attribute.
        """
        self.assertEquals(
            self.service.persist.filename,
            os.path.join(self.config.data_path, "broker.bpickle"))

    def test_transport(self):
        """
        A L{BrokerService} instance has a proper C{transport} attribute.
        """
        self.assertTrue(isinstance(self.service.transport, HTTPTransport))
        self.assertEquals(self.service.transport.get_url(), self.config.url)

    def test_message_store(self):
        """
        A L{BrokerService} instance has a proper C{message_store} attribute.
        """
        self.assertEquals(self.service.message_store.get_accepted_types(), ())

    def test_identity(self):
        """
        A L{BrokerService} instance has a proper C{identity} attribute.
        """
        self.assertEquals(self.service.identity.account_name, "some_account")

    def test_exchanger(self):
        """
        A L{BrokerService} instance has a proper C{exchanger} attribute.
        """
        self.assertEquals(self.service.exchanger.get_exchange_intervals(),
                          (60, 900))

    def test_pinger(self):
        """
        A L{BrokerService} instance has a proper C{pinger} attribute.
        """
        self.assertEquals(self.service.pinger.get_url(), self.config.ping_url)

    def test_registration(self):
        """
        A L{BrokerService} instance has a proper C{registration} attribute.
        """
        self.assertEquals(self.service.registration.should_register(), False)

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
        return connected
