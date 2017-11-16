from twisted.internet.defer import maybeDeferred, execute, succeed
from twisted.python.compat import iteritems

from landscape.lib.amp import RemoteObject, MethodCallArgument
from landscape.client.amp import ComponentConnector, get_remote_methods
from landscape.client.broker.server import BrokerServer
from landscape.client.broker.client import BrokerClient
from landscape.client.monitor.monitor import Monitor
from landscape.client.manager.manager import Manager


class RemoteBroker(RemoteObject):

    def call_if_accepted(self, type, callable, *args):
        """Call C{callable} if C{type} is an accepted message type."""
        deferred_types = self.get_accepted_message_types()

        def got_accepted_types(result):
            if type in result:
                return callable(*args)
        deferred_types.addCallback(got_accepted_types)
        return deferred_types

    def call_on_event(self, handlers):
        """Call a given handler as soon as a certain event occurs.

        @param handlers: A dictionary mapping event types to callables, where
            an event type is string (the name of the event). When the first of
            the given event types occurs in the broker reactor, the associated
            callable will be fired.
        """
        result = self.listen_events(list(handlers.keys()))
        return result.addCallback(
            lambda args: handlers[args[0]](**args[1]))


class FakeRemoteBroker(object):
    """Looks like L{RemoteBroker}, but actually talks to local objects."""

    def __init__(self, exchanger, message_store, broker_server):
        self.exchanger = exchanger
        self.message_store = message_store
        self.broker_server = broker_server

    def __getattr__(self, name):
        """
        Pass attributes through to the real L{BrokerServer}, after checking
        that they're encodable with AMP.
        """
        original = getattr(self.broker_server, name, None)
        if (name in get_remote_methods(self.broker_server) and
            original is not None and
            callable(original)
            ):
            def method(*args, **kwargs):
                for arg in args:
                    assert MethodCallArgument.check(arg)
                for k, v in iteritems(kwargs):
                    assert MethodCallArgument.check(v)
                return execute(original, *args, **kwargs)
            return method
        else:
            raise AttributeError(name)

    def call_if_accepted(self, type, callable, *args):
        if type in self.message_store.get_accepted_types():
            return maybeDeferred(callable, *args)
        return succeed(None)

    def call_on_event(self, handlers):
        """Call a given handler as soon as a certain event occurs.

        @param handlers: A dictionary mapping event types to callables, where
            an event type is string (the name of the event). When the first of
            the given event types occurs in the broker reactor, the associated
            callable will be fired.
        """
        result = self.broker_server.listen_events(handlers.keys())
        return result.addCallback(
            lambda args: handlers[args[0]](**args[1]))

    def register(self):
        return succeed(None)


class RemoteBrokerConnector(ComponentConnector):
    """Helper to create connections with the L{BrokerServer}."""

    remote = RemoteBroker
    component = BrokerServer


class RemoteClientConnector(ComponentConnector):
    """Helper to create connections with the L{BrokerServer}."""

    component = BrokerClient


class RemoteMonitorConnector(RemoteClientConnector):
    """Helper to create connections with the L{Monitor}."""

    component = Monitor


class RemoteManagerConnector(RemoteClientConnector):
    """Helper for creating connections with the L{Monitor}."""

    component = Manager


def get_component_registry():
    """Get a mapping of component name to connectors, for all components."""
    all_connectors = [
        RemoteBrokerConnector,
        RemoteClientConnector,
        RemoteMonitorConnector,
        RemoteManagerConnector
    ]
    return dict(
        (connector.component.name, connector)
        for connector in all_connectors)
