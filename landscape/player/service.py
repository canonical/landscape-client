"""Deployment code for the player."""

import os
from landscape.lib.fetch import fetch_async
from landscape.service import LandscapeService, run_landscape_service
from landscape.broker.registration import RegistrationHandler, Identity
from landscape.broker.transport import HTTPTransport
from landscape.broker.exchangestore import ExchangeStore
from landscape.broker.ping import Pinger
from landscape.broker.store import get_default_message_store
from landscape.broker.server import BrokerServer
from landscape.broker.amp import BrokerServerProtocolFactory
from landscape.player.exchange import PayloadExchanger
from landscape.player.player import PayloadPlayer
from landscape.player.reader import PayloadReader
from landscape.player.config import PlaybackConfiguration


class PlaybackService(LandscapeService):
    transport_factory = HTTPTransport
    pinger_factory = Pinger
    service_name = "player"

    def __init__(self, config):
        """
        @param config: A L{BrokerConfiguration}.
        """
        self.persist_filename = os.path.join(
            config.data_path, "%s.bpickle" % (self.service_name,))
        super(PlaybackService, self).__init__(config)

        self.payload_reader = PayloadReader(config.record_directory)

        self.transport = self.transport_factory(
            config.url, config.ssl_public_key, None)
        self.message_store = get_default_message_store(
            self.persist, config.message_store_path)
        self.identity = Identity(self.config, self.persist)
        exchange_store = ExchangeStore(self.config.exchange_store_path)
        self.exchanger = PayloadExchanger(
            self.reactor, self.message_store, self.transport, self.identity,
            exchange_store, config)
        self.pinger = self.pinger_factory(self.reactor, config.ping_url,
                                          self.identity, self.exchanger)
        self.registration = RegistrationHandler(
            config, self.identity, self.reactor, self.exchanger, self.pinger,
            self.message_store, fetch_async)
        self.reactor.call_on("post-exit", self._exit)

        self.player = PayloadPlayer(self.payload_reader, self.exchanger, 10)

        self.broker = BrokerServer(self.config, self.reactor, self.exchanger,
                                   self.registration, self.message_store)
        self.factory = BrokerServerProtocolFactory(object=self.broker)

    def _exit(self):
        # Our reactor calls the Twisted reactor's crash() method rather
        # than the real stop.  As a consequence, if we use it here, normal
        # termination doesn't happen, and stopService() would never get
        # called.
        from twisted.internet import reactor
        reactor.stop()

    def startService(self):
        """Start the broker.

        Start the L{MessageExchange}, L{Pinger} and L{Player} services.
        """
        super(PlaybackService, self).startService()
        self.exchanger.start()
        self.pinger.start()
        self.player.load()
        self.player.play()

    def stopService(self):
        """Stop the broker."""
        self.exchanger.stop()
        super(PlaybackService, self).stopService()


def run(args):
    """Run the application, given some command line arguments."""
    run_landscape_service(PlaybackConfiguration, PlaybackService, args)
