import os

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
    BrokerServerProtocolFactory, BrokerClientProtocolFactory,
    RemoteBrokerConnector)
from landscape.broker.client import BrokerClient


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
      - broker: A L{BrokerServer}.
    """

    def set_up(self, test_case):
        super(BrokerServerHelper, self).set_up(test_case)
        test_case.broker = BrokerServer(test_case.config, test_case.reactor,
                                        test_case.exchanger, test_case.handler,
                                        test_case.mstore)


class RemoteBrokerHelper(BrokerServerHelper):
    """
    This helper adds a connected L{RemoteBroker} to a L{BrokerServerHelper}.
    The following attributes will be set in your test case:
      - remote: A C{RemoteObject} connected to the broker server.
    """

    def set_up(self, test_case):
        super(RemoteBrokerHelper, self).set_up(test_case)

        factory = BrokerServerProtocolFactory(object=test_case.broker)
        socket = os.path.join(test_case.config.data_path,
                              BrokerServer.name + ".sock")
        self._port = test_case.reactor.listen_unix(socket, factory)
        self._connector = RemoteBrokerConnector(test_case.reactor,
                                                test_case.config)

        def set_remote(remote):
            test_case.remote = remote
            return remote

        connected = self._connector.connect()
        return connected.addCallback(set_remote)

    def tear_down(self, test_case):
        self._connector.disconnect()
        self._port.stopListening()
        super(RemoteBrokerHelper, self).tear_down(test_case)


class BrokerClientHelper(RemoteBrokerHelper):
    """
    This helper adds a L{BrokerClient} connected  to a L{BrokerServerHelper}.
    The following attributes will be set in your test case:
      - client: A connected L{BrokerClient}
      - client_reactor: The L{FakeReactor} used by the client
    """

    def set_up(self, test_case):

        def set_client(remote):
            # The client needs its own reactor to avoid infinite loops
            # when the broker broadcasts and event
            test_case.client_reactor = FakeReactor()
            test_case.client = BrokerClient(test_case.client_reactor)
            test_case.client.broker = remote

        connected = super(BrokerClientHelper, self).set_up(test_case)
        return connected.addCallback(set_client)


class RemoteClientHelper(BrokerClientHelper):
    """
    This helper adds a connected and registered L{RemoteClient} to a
    L{BrokerClientHelper}.
    The following attributes will be set in your test case:
      - remote_client: A C{RemoteClient} connected to a registered client.
    """

    def set_up(self, test_case):

        def set_remote_client(ignored):
            test_case.remote_client = test_case.broker.get_clients()[0]
            self._client_connector = test_case.broker.get_connectors()[0]

        def listen(ignored):

            factory = BrokerClientProtocolFactory(object=test_case.client)
            socket = os.path.join(test_case.config.data_path,
                                  test_case.client.name + ".sock")
            self._client_port = test_case.client_reactor.listen_unix(socket,
                                                                     factory)
            result = test_case.remote.register_client("client")
            return result.addCallback(set_remote_client)

        connected = super(RemoteClientHelper, self).set_up(test_case)
        return connected.addCallback(listen)

    def tear_down(self, test_case):
        self._client_connector.disconnect()
        self._client_port.stopListening()
        super(RemoteClientHelper, self).tear_down(test_case)
