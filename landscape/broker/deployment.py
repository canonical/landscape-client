"""Deployment code for the broker."""

import os

from landscape.deployment import (LandscapeService, Configuration,
                                  run_landscape_service)
from landscape.broker.store import get_default_message_store
from landscape.broker.transport import HTTPTransport
from landscape.broker.exchange import MessageExchange
from landscape.broker.registration import RegistrationHandler, Identity
from landscape.broker.broker import BrokerDBusObject
from landscape.lib.fetch import fetch_async
from landscape.broker.ping import Pinger


class BrokerConfiguration(Configuration):
    """Specialized configuration for the Landscape Broker.

    @cvar required_options: C{["url"]}
    """

    required_options = ["url"]

    def __init__(self):
        super(BrokerConfiguration, self).__init__()
        self._original_http_proxy = os.environ.get("http_proxy")
        self._original_https_proxy = os.environ.get("https_proxy")

    def make_parser(self):
        """Parser factory for broker-specific options.

        @return: An L{OptionParser} preset for all the options
            from L{Configuration.make_parser} plus:
              - C{account_name}
              - C{registration_password}
              - C{computer_title}
              - C{url}
              - C{ssl_public_key}
              - C{exchange_interval} (C{15*60})
              - C{urgent_exchange_interval} (C{1*60})
              - C{ping_url}
              - C{http_proxy}
              - C{https_proxy}
              - C{cloud}
        """
        parser = super(BrokerConfiguration, self).make_parser()

        parser.add_option("-a", "--account-name", metavar="NAME",
                          help="The account this computer belongs to.")
        parser.add_option("-p", "--registration-password", metavar="PASSWORD",
                          help="The account-wide password used for registering "
                               "clients.")
        parser.add_option("-t", "--computer-title", metavar="TITLE",
                          help="The title of this computer")
        parser.add_option("-u", "--url",
                          help="The server URL to connect to (default: "
                               "https://landscape.canonical.com/"
                               "message-system).")
        parser.add_option("-k", "--ssl-public-key",
                          help="The SSL CA certificate to verify the server "
                               "with. Only used if the server URL to which "
                               "we connect is https.")
        parser.add_option("--exchange-interval", default=15*60, type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between server "
                               "exchanges (default: 900s).")
        parser.add_option("--urgent-exchange-interval", default=1*60,
                          type="int", metavar="INTERVAL",
                          help="The number of seconds between urgent server "
                               "exchanges (default: 60s).")
        parser.add_option("--ping-url",
                          help="The URL to perform lightweight exchange "
                               "initiation with (default: "
                               "http://landscape.canonical.com/ping).")
        parser.add_option("--http-proxy", metavar="URL",
                          help="The URL of the HTTP proxy, if one is needed.")
        parser.add_option("--https-proxy", metavar="URL",
                          help="The URL of the HTTPS proxy, if one is needed.")
        parser.add_option("--cloud", action="store_true",
                          help="Set this if your computer is a cloud instance "
                               "(EC2 or UEC) and you want it to be managed by "
                               "Landscape's cloud features. See the manpage "
                               "for details.")
        parser.add_option("--tags",
                          help="Comma separated list of tag names to be sent "
                               "to the server.")
        return parser

    @property
    def message_store_path(self):
        """Get the path to the message store."""
        return os.path.join(self.data_path, "messages")

    def load(self, args, accept_nonexistent_config=False):
        """
        Load options from command line arguments and a config file.

        Load the configuration with L{Configuration.load}, and then set
        C{http_proxy} and C{https_proxy} environment variables based on
        that config data.
        """
        super(BrokerConfiguration, self).load(
            args, accept_nonexistent_config=accept_nonexistent_config)
        if self.http_proxy:
            os.environ["http_proxy"] = self.http_proxy
        elif self._original_http_proxy:
            os.environ["http_proxy"] = self._original_http_proxy

        if self.https_proxy:
            os.environ["https_proxy"] = self.https_proxy
        elif self._original_https_proxy:
            os.environ["https_proxy"] = self._original_https_proxy


class BrokerService(LandscapeService):
    """The core C{Service} of the Landscape Broker C{Application}.

    The Landscape broker service handles all the communication between the
    client and server. When started it creates and runs all necessary components
    to exchange messages with the Landscape server.

    @ivar persist_filename: Path to broker-specific persisted data.
    @ivar persist: A L{Persist} object saving and loading from
        C{self.persist_filename}.
    @ivar message_store: A L{MessageStore} used by the C{exchanger} to
        queue outgoing messages.
    @ivar transport: A L{HTTPTransport} used by the C{exchanger} to deliver messages.
    @ivar identity: The L{Identity} of the Landscape client the broker runs on.
    @ivar exchanger: The L{MessageExchange} exchanges messages with the server.
    @ivar pinger: The L{Pinger} checks if the server has new messages for us.
    @ivar registration: The L{RegistrationHandler} performs the initial
        registration.

    @cvar service_name: C{"broker"}
    """

    transport_factory = HTTPTransport
    service_name = "broker"

    def __init__(self, config):
        """
        @param config: a L{BrokerConfiguration}.
        """
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

        self.pinger = Pinger(self.reactor, config.ping_url, self.identity,
                             self.exchanger)
        self.registration = RegistrationHandler(config,
                                                self.identity, self.reactor,
                                                self.exchanger,
                                                self.pinger,
                                                self.message_store,
                                                config.cloud, fetch_async)

        self.reactor.call_on("post-exit", self._exit)

    def _exit(self):
        # Our reactor calls the Twisted reactor's crash() method rather
        # than the real stop.  As a consequence, if we use it here, normal
        # termination doesn't happen, and stopService() would never get
        # called.
        from twisted.internet import reactor
        reactor.stop()

    def startService(self):
        """Start the broker.

        Create the DBus-published L{BrokerDBusObject}, and start
        the L{MessageExchange} and L{Pinger} services.

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
