"""Deployment code for the monitor."""

import os

from landscape.client.service import LandscapeService, run_landscape_service
from landscape.client.amp import ComponentPublisher
from landscape.client.broker.registration import RegistrationHandler, Identity
from landscape.client.broker.config import BrokerConfiguration
from landscape.client.broker.transport import HTTPTransport
from landscape.client.broker.exchange import MessageExchange
from landscape.client.broker.exchangestore import ExchangeStore
from landscape.client.broker.ping import Pinger
from landscape.client.broker.store import get_default_message_store
from landscape.client.broker.server import BrokerServer


class BrokerService(LandscapeService):
    """The core C{Service} of the Landscape Broker C{Application}.

    The Landscape broker service handles all the communication between the
    client and server.  When started it creates and runs all necessary
    components to exchange messages with the Landscape server.

    @cvar service_name: C{broker}

    @ivar persist_filename: Path to broker-specific persistent data.
    @ivar persist: A L{Persist} object saving and loading data from
        C{self.persist_filename}.
    @ivar message_store: A L{MessageStore} used by the C{exchanger} to
        queue outgoing messages.
    @ivar transport: An L{HTTPTransport} used by the C{exchanger} to deliver
        messages.
    @ivar identity: The L{Identity} of the Landscape client the broker runs on.
    @ivar exchanger: The L{MessageExchange} exchanges messages with the server.
    @ivar pinger: The L{Pinger} checks if the server has new messages for us.
    @ivar registration: The L{RegistrationHandler} performs the initial
        registration.

    @param config: A L{BrokerConfiguration}.
    """

    transport_factory = HTTPTransport
    pinger_factory = Pinger
    service_name = BrokerServer.name

    def __init__(self, config):
        self.persist_filename = os.path.join(
            config.data_path, "%s.bpickle" % (self.service_name,))
        super(BrokerService, self).__init__(config)

        self.transport = self.transport_factory(
            self.reactor, config.url, config.ssl_public_key)
        self.message_store = get_default_message_store(
            self.persist, config.message_store_path)
        self.identity = Identity(self.config, self.persist)
        exchange_store = ExchangeStore(self.config.exchange_store_path)
        self.exchanger = MessageExchange(
            self.reactor, self.message_store, self.transport, self.identity,
            exchange_store, config)
        self.pinger = self.pinger_factory(
            self.reactor, self.identity, self.exchanger, config)
        self.registration = RegistrationHandler(
            config, self.identity, self.reactor, self.exchanger, self.pinger,
            self.message_store)
        self.broker = BrokerServer(self.config, self.reactor, self.exchanger,
                                   self.registration, self.message_store,
                                   self.pinger)
        self.publisher = ComponentPublisher(self.broker, self.reactor,
                                            self.config)

    def startService(self):
        """Start the broker.

        Create a L{BrokerServer} listening on C{broker_socket_path} for clients
        connecting with the L{BrokerServerConnector}, and start the
        L{MessageExchange} and L{Pinger} services.
        """
        super(BrokerService, self).startService()
        self.publisher.start()
        self.exchanger.start()
        self.pinger.start()

    def stopService(self):
        """Stop the broker."""
        deferred = self.publisher.stop()
        self.exchanger.stop()
        self.pinger.stop()
        super(BrokerService, self).stopService()
        return deferred


def run(args):
    """Run the application, given some command line arguments."""
    run_landscape_service(BrokerConfiguration, BrokerService, args)
