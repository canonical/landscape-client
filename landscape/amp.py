import os
import logging

from landscape.lib.amp import (
    MethodCallProtocol, MethodCallFactory, RemoteObjectConnector)


class ComponentProtocol(MethodCallProtocol):
    """Communication protocol between the various Landscape components.

    It can be used both as server-side protocol for exposing the methods of a
    certain Landscape component, or as client-side protocol for connecting to
    another Landscape component we want to call the methods of.
    """
    methods = ["ping", "exit"]
    timeout = 60


class ComponentProtocolFactory(MethodCallFactory):

    protocol = ComponentProtocol


class RemoteComponentConnector(RemoteObjectConnector):
    """Utility superclass for creating connections with a Landscape component.

    @cvar component: The class of the component to connect to, it is expected
        to define a C{name} class attribute, which will be used to find out
        the socket to use. It must be defined by sub-classes.
    """

    factory = ComponentProtocolFactory

    def __init__(self, reactor, config, *args, **kwargs):
        """
        @param reactor: A L{TwistedReactor} object.
        @param config: A L{LandscapeConfiguration}.
        @param args: Positional arguments for protocol factory constructor.
        @param kwargs: Keyword arguments for protocol factory constructor.

        @see: L{MethodCallClientFactory}.
        """
        self._twisted_reactor = reactor
        socket = os.path.join(config.data_path, self.component.name + ".sock")
        super(RemoteComponentConnector, self).__init__(
            self._twisted_reactor._reactor, socket, *args, **kwargs)

    def connect(self, max_retries=None):
        """Connect to the remote Landscape component.

        If the connection is lost after having been established, and then
        it is established again by the reconnect mechanism, an event will
        be fired.

        @param max_retries: If given, the connector will keep trying to connect
            up to that number of times, if the first connection attempt fails.
        """

        def fire_reconnect(remote):
            self._twisted_reactor.fire("%s-reconnect" %
                                       self.component.name)

        def connected(remote):
            self._factory.add_notifier(fire_reconnect)
            return remote

        def log_error(failure):
            logging.error("Error while connecting to %s", self.component.name)
            return failure

        result = super(RemoteComponentConnector, self).connect(
            max_retries=max_retries)
        result.addErrback(log_error)
        result.addCallback(connected)
        return result


class RemoteComponentsRegistry(object):
    """
    A global registry for looking up Landscape components connectors by name.
    """

    _by_name = {}

    @classmethod
    def get(cls, name):
        """Get the connector class for the given Landscape component.

        @param name: Name of the Landscape component we want to connect to, for
           instance C{monitor} or C{manager}.
        """
        return cls._by_name[name]

    @classmethod
    def register(cls, connector_class):
        """Register a connector for a Landscape component.

        @param connector_class: A sub-class of L{RemoteComponentConnector}
            that can be used to connect to a certain component.
        """
        cls._by_name[connector_class.component.name] = connector_class
