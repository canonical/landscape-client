import os

from mock import Mock

from landscape.client.tests.helpers import LandscapeTest
from landscape.client.broker.tests.helpers import BrokerConfigurationHelper
from landscape.client.broker.service import BrokerService
from landscape.client.broker.transport import HTTPTransport
from landscape.client.broker.amp import RemoteBrokerConnector
from landscape.lib.testing import FakeReactor


class BrokerServiceTest(LandscapeTest):

    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super(BrokerServiceTest, self).setUp()

        class FakeBrokerService(BrokerService):
            reactor_factory = FakeReactor

        self.service = FakeBrokerService(self.config)

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

    def test_start_stop(self):
        """
        The L{BrokerService.startService} method makes the process start
        listening to the broker socket, and starts the L{Exchanger} and
        the L{Pinger} as well.
        """
        self.service.exchanger.start = Mock()
        self.service.pinger.start = Mock()
        self.service.exchanger.stop = Mock()

        self.service.startService()
        reactor = FakeReactor()
        connector = RemoteBrokerConnector(reactor, self.config)
        connected = connector.connect()
        connected.addCallback(lambda remote: remote.get_server_uuid())
        connected.addCallback(lambda x: connector.disconnect())
        connected.addCallback(lambda x: self.service.stopService())

        self.service.exchanger.start.assert_called_with()
        self.service.pinger.start.assert_called_with()
        self.service.exchanger.stop.assert_called_with()
