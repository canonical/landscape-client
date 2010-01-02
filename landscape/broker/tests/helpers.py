from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator

from landscape.lib.fetch import fetch_async
from landscape.lib.persist import Persist
from landscape.watchdog import bootstrap_list
from landscape.reactor import FakeReactor
from landscape.broker.transport import FakeTransport
from landscape.broker.exchange import MessageExchange
from landscape.broker.store import get_default_message_store
from landscape.broker.registration import Identity, RegistrationHandler
from landscape.broker.ping import Pinger
from landscape.broker.deployment import BrokerConfiguration
from landscape.broker.server import BrokerServer
from landscape.broker.amp import (
    BrokerServerProtocolFactory, RemoteBroker, BrokerClientProtocol)
from landscape.broker.client import BrokerClient
from landscape.broker.service import BrokerService


class BrokerConfigurationHelper(object):
    """
    The following attributes will be set on your test case:
      - config: A sample L{BrokerConfiguration}.
      - config_filename: The name of the configuration file that was used to
        generate the above C{config}.
    """

    def set_up(self, test_case):
        data_path = test_case.makeDir()
        log_dir = test_case.makeDir()
        test_case.config_filename = test_case.makeFile(
            "[client]\n"
            "url = http://localhost:91919\n"
            "computer_title = Some Computer\n"
            "account_name = some_account\n"
            "ping_url = http://localhost:91910\n"
            "data_path = %s\n"
            "log_dir = %s\n" % (data_path, log_dir))

        bootstrap_list.bootstrap(data_path=data_path, log_dir=log_dir)

        test_case.config = BrokerConfiguration()
        test_case.config.load(["-c", test_case.config_filename])

    def tear_down(self, test_case):
        pass


class ExchangeHelper(BrokerConfigurationHelper):
    """
    This helper uses the sample broker configuration provided by the
    L{BrokerConfigurationHelper} to create all the components needed by
    a L{MessageExchange}.  The following attributes will be set on your
    test case:
      - exchanger: A L{MessageExchange} using a L{FakeReactor} and a
        L{FakeTransport}.
      - reactor: The L{FakeReactor} used by the C{exchager}.
      - transport: The L{FakeTransport} used by the C{exchanger}.
      - identity: The L{Identity} used by the C{exchanger} and based
        on the sample configuration.
      - mstore: The L{MessageStore} used by the C{exchanger} and based
        on the sample configuration.
      - persist: The L{Persist} object used by C{mstore} and C{identity}.
      - persit_filename: Path to the file holding the C{persist} data.
    """

    def set_up(self, test_case):
        super(ExchangeHelper, self).set_up(test_case)
        test_case.persist_filename = test_case.makePersistFile()
        test_case.persist = Persist(filename=test_case.persist_filename)
        test_case.mstore = get_default_message_store(
            test_case.persist, test_case.config.message_store_path)
        test_case.identity = Identity(test_case.config, test_case.persist)
        test_case.transport = FakeTransport(test_case.config.url,
                                            test_case.config.ssl_public_key)
        test_case.reactor = FakeReactor()
        test_case.exchanger = MessageExchange(
            test_case.reactor, test_case.mstore, test_case.transport,
            test_case.identity, test_case.config.exchange_interval,
            test_case.config.urgent_exchange_interval)


class RegistrationHelper(ExchangeHelper):
    """
    This helper adds a registration handler to the L{ExchangeHelper}.  If the
    test case has C{cloud} class attribute, the C{handler} will be configured
    for a cloud registration.  The following attributes will be set in your
    test case:
      - handler: A L{RegistrationHandler}
      - fetch_func: The C{fetch_async} function used by the C{handler}, it
        can be customised by test cases.
    """

    def set_up(self, test_case):
        super(RegistrationHelper, self).set_up(test_case)
        test_case.pinger = Pinger(test_case.reactor, test_case.config.ping_url,
                                  test_case.identity, test_case.exchanger)

        def fetch_func(*args, **kwargs):
            return test_case.fetch_func(*args, **kwargs)

        test_case.fetch_func = fetch_async
        test_case.config.cloud = getattr(test_case, "cloud", False)
        test_case.handler = RegistrationHandler(
            test_case.config, test_case.identity, test_case.reactor,
            test_case.exchanger, test_case.pinger, test_case.mstore,
            fetch_async=fetch_func)


class BrokerServerHelper(RegistrationHelper):
    """
    This helper adds a broker server to the L{RegistrationHelper}.  The
    following attributes will be set in your test case:
      - server: A L{BrokerServer}.
    """

    def set_up(self, test_case):
        super(BrokerServerHelper, self).set_up(test_case)
        test_case.broker = BrokerServer(test_case.config, test_case.reactor,
                                        test_case.exchanger, test_case.handler,
                                        test_case.mstore)


class BrokerProtocolHelper(BrokerServerHelper):
    """
    This helper adds a connected broker protocol to the L{BrokerServerHelper}.
    The following attributes will be set in your test case:
      - port: The C{Port} object connected to the Unix socket the server
          is listening to.
      - protocol: An L{AMP} protocol instance connected to the server's port.
    """

    def set_up(self, test_case):
        super(BrokerProtocolHelper, self).set_up(test_case)
        socket = test_case.makeFile()
        factory = BrokerServerProtocolFactory(test_case.broker)
        test_case.port = reactor.listenUNIX(socket, factory)

        def set_protocol(protocol):
            test_case.protocol = protocol

        connector = ClientCreator(reactor, BrokerClientProtocol)
        connected = connector.connectUNIX(socket)
        return connected.addCallback(set_protocol)

    def tear_down(self, test_case):
        super(BrokerProtocolHelper, self).tear_down(test_case)
        test_case.port.loseConnection()
        test_case.protocol.transport.loseConnection()


class RemoteBrokerHelper(BrokerProtocolHelper):
    """
    This helper adds a connected L{RemoteBroker} to a L{BrokerProtocolHelper}.
    The following attributes will be set in your test case:
      - remote: A C{RemoteBroker} object connected to the broker server.
    """

    def set_up(self, test_case):
        connected = super(RemoteBrokerHelper, self).set_up(test_case)
        connected.addCallback(lambda x: setattr(
            test_case, "remote", RemoteBroker(test_case.protocol)))
        return connected


class BrokerClientHelper(RemoteBrokerHelper):
    """
    This helper adds a L{BrokerClient} to a L{RemoteBrokerHelper}.
    The following attributes will be set in your test case:
      - client: A C{BrokerClient} object connected to a remote broker.
    """

    def set_up(self, test_case):

        def set_broker_client(ignored):
            test_case.client = BrokerClient(test_case.remote,
                                            test_case.reactor)

        connected = super(BrokerClientHelper, self).set_up(test_case)
        return connected.addCallback(set_broker_client)


class BrokerServiceHelper(object):
    """
    The following attributes will be set in your test case:
      - broker_service: A started C{BrokerService}.
      - remote: A C{RemoteBroker} object connected to the broker server.
    """

    def set_up(self, test_case):
        data_path = test_case.makeDir()
        log_dir = test_case.makeDir()
        test_case.config_filename = test_case.makeFile(
            "[client]\n"
            "url = http://localhost:91919\n"
            "computer_title = Some Computer\n"
            "account_name = some_account\n"
            "ping_url = http://localhost:91910\n"
            "data_path = %s\n"
            "log_dir = %s\n" % (data_path, log_dir))

        bootstrap_list.bootstrap(data_path=data_path, log_dir=log_dir)

        config = BrokerConfiguration()
        config.load(["-c", test_case.config_filename])

        class FakeBrokerService(BrokerService):
            reactor_factory = FakeReactor
            transport_factory = FakeTransport

        test_case.broker_service = FakeBrokerService(config)
        test_case.broker_service.startService()

        connector = ClientCreator(reactor, BrokerClientProtocol)
        connected = connector.connectUNIX(config.broker_socket_filename)
        return connected.addCallback(lambda protocol: setattr(
            test_case, "remote", RemoteBroker(protocol)))

    def tear_down(self, test_case):
        test_case.broker_service.stopService()
        test_case.remote.disconnect()
