from twisted.internet.protocol import ClientCreator

from landscape.lib.amp import Method, MethodCallProtocol


class BrokerServerProtocol(MethodCallProtocol):
    """
    Communication protocol between the broker server and its clients.
    """
    methods = [Method("ping"),
               Method("register_client", protocol=""),
               Method("send_message"),
               Method("is_message_pending"),
               Method("stop_clients"),
               Method("reload_configuration"),
               Method("register"),
               Method("get_accepted_message_types"),
               Method("get_server_uuid"),
               Method("register_client_accepted_message_type"),
               Method("exit")]


class RemoteBrokerCreator(object):
    """A connected broker utilizing features provided by a L{BrokerServer}."""

    def __init__(self, config, reactor):
        """
        @param protocol: A L{BrokerServerProtocol} connection with a remote
            broker server.
        """
        self._config = config
        self._reactor = reactor

    def connect(self):
        """Connect to the remote L{BrokerServer}."""

        def set_protocol(protocol):
            self._protocol = protocol
            return protocol.remote

        connector = ClientCreator(self._reactor._reactor,
                                  BrokerClientProtocol,
                                  self._reactor._reactor)
        socket = self._config.broker_socket_filename
        connected = connector.connectUNIX(socket)
        return connected.addCallback(set_protocol)

    def disconnect(self):
        """Disconnect from the remote L{BrokerServer}."""
        self._protocol.transport.loseConnection()


class BrokerClientProtocol(MethodCallProtocol):
    """
    Communication protocol between the broker server and its clients.
    """

    methods = [Method("ping"),
               Method("dispatch_message"),
               Method("fire_event"),
               Method("exit")]
