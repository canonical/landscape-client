"""Deployment code for the broker."""

import os

from landscape.deployment import (LandscapeService, Configuration,
                                  run_landscape_service)
from landscape.broker.store import get_default_message_store
from landscape.broker.transport import HTTPTransport
from landscape.broker.exchange import MessageExchange
from landscape.broker.registration import RegistrationHandler, Identity
from landscape.broker.broker import BrokerDBusObject
from landscape.broker.ping import Pinger


class BrokerConfiguration(Configuration):
    """Specialized configuration for the Landscape Broker."""

    required_options = ["url"]

    def __init__(self):
        super(BrokerConfiguration, self).__init__()
        self._original_http_proxy = os.environ.get("http_proxy")
        self._original_https_proxy = os.environ.get("https_proxy")

    def make_parser(self):
        """
        Specialize L{Configuration.make_parser}, adding many
        broker-specific options.
        """
        parser = super(BrokerConfiguration, self).make_parser()

        parser.add_option("-a", "--account-name", metavar="NAME",
                          help="The account this computer belongs to.")
        parser.add_option("-p", "--registration-password", metavar="PASSWORD",
                          help="The account-wide password used for registering "
                               "clients.")
        parser.add_option("-t", "--computer-title", metavar="TITLE",
                          help="The title of this computer")
        parser.add_option("-u", "--url", help="The server URL to connect to.")
        parser.add_option("-k", "--ssl-public-key",
                          help="The public SSL key to verify the server. "
                               "Only used if the given URL is https.")
        parser.add_option("--exchange-interval", default=15*60, type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between server "
                               "exchanges.")
        parser.add_option("--urgent-exchange-interval", default=1*60,
                          type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between urgent server "
                               "exchanges.")
        parser.add_option("--ping-url",
                          help="The URL to perform lightweight exchange "
                               "initiation with.")
        parser.add_option("--http-proxy", metavar="URL",
                          help="The URL of the HTTP proxy, if one is needed.")
        parser.add_option("--https-proxy", metavar="URL",
                          help="The URL of the HTTPS proxy, if one is needed.")
        parser.add_option("-n", "--no-start", action="store_true")
        return parser

    @property
    def message_store_path(self):
        return os.path.join(self.data_path, "messages")

    def load(self, args, accept_unexistent_config=False):
        """
        Load the configuration with L{Configuration.load}, and then set
        http_proxy and https_proxy environment variables based on that config
        data.
        """
        super(BrokerConfiguration, self).load(
            args, accept_unexistent_config=accept_unexistent_config)
        if self.http_proxy:
            os.environ["http_proxy"] = self.http_proxy
        elif self._original_http_proxy:
            os.environ["http_proxy"] = self._original_http_proxy

        if self.https_proxy:
            os.environ["https_proxy"] = self.https_proxy
        elif self._original_https_proxy:
            os.environ["https_proxy"] = self._original_https_proxy


class BrokerService(LandscapeService):
    """
    The core Twisted Service which creates and runs all necessary
    components when started.
    """

    transport_factory = HTTPTransport

    service_name = "broker"

    def __init__(self, config):
        self.persist_filename = os.path.join(
            config.data_path, "%s.bpickle" % (self.service_name,))
        super(BrokerService, self).__init__(config)
        self.transport = self.transport_factory(config.url,
                                                config.ssl_public_key)

        self.message_store = get_default_message_store(
            self.persist, config.message_store_path)
        self.identity = Identity(self.config, self.persist)
        self.exchanger = MessageExchange(self.reactor, self.message_store,
                                         self.transport, self.identity,
                                         config.exchange_interval,
                                         config.urgent_exchange_interval)

        self.registration = RegistrationHandler(self.identity, self.reactor,
                                                self.exchanger,
                                                self.message_store)
        self.pinger = Pinger(self.reactor, config.ping_url, self.identity,
                             self.exchanger)

        self.reactor.call_on("post-exit", self._exit)

    def _exit(self):
        # Our reactor calls the Twisted reactor's crash() method rather
        # than the real stop.  As a consequence, if we use it here, normal
        # termination doesn't happen, and stopService() would never get
        # called.
        from twisted.internet import reactor
        reactor.stop()

    def startService(self):
        """
        Set up the persist, message store, transport, reactor, and
        dbus message exchange service.

        If the configuration specifies the bus as 'session', the DBUS
        message exchange service will use the DBUS Session Bus.
        """
        super(BrokerService, self).startService()
        self.dbus_object = BrokerDBusObject(self.config, self.reactor,
                                            self.exchanger, self.registration,
                                            self.message_store, self.bus)

        self.exchanger.start()
        self.pinger.start()

    def stopService(self):
        """Stop the broker."""
        self.exchanger.stop()
        super(BrokerService, self).stopService()


def run(args):
    """Run the application, given some command line arguments."""
    run_landscape_service(BrokerConfiguration, BrokerService, args,
                          BrokerDBusObject.bus_name)
