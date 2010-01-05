from landscape.lib.amp import Method, MethodCallProtocol, RemoteObjectCreator


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


class RemoteBrokerCreator(RemoteObjectCreator):
    """A connected broker utilizing features provided by a L{BrokerServer}."""

    protocol = MethodCallProtocol
