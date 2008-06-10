import sys

from logging import exception

from landscape.log import format_object
from landscape.plugin import Plugin, PluginRegistry, BrokerPlugin
from landscape.lib.dbus_util import method

# Protocol messages! Same constants are defined in the server.
FAILED = 5
SUCCEEDED = 6

SERVICE = "com.canonical.landscape.manager"


BUS_NAME = "com.canonical.landscape.Manager"
OBJECT_PATH = "/com/canonical/landscape/Manager"
IFACE_NAME = BUS_NAME


class ManagerDBusObject(BrokerPlugin):
    """A DBUS object which provides an interface to the Landscape Manager."""

    bus_name = BUS_NAME
    object_path = OBJECT_PATH

    ping = method(IFACE_NAME)(BrokerPlugin.ping)
    exit = method(IFACE_NAME)(BrokerPlugin.exit)
    message = method(IFACE_NAME)(BrokerPlugin.message)


class ManagerPluginRegistry(PluginRegistry):
    """Central point of integration for the Landscape Manager."""

    def __init__(self, reactor, broker, config, bus=None):
        super(ManagerPluginRegistry, self).__init__()
        self.reactor = reactor
        self.broker = broker
        self.config = config
        self.bus = bus


class ManagerPlugin(Plugin):

    def call_with_operation_result(self, message, callable, *args, **kwargs):
        """Send an operation-result message after calling C{callable}.

        If the function returns normally, an operation-result
        indicating success will be sent.  If the function raises an
        exception, an operation-result indicating failure will be
        sent.

        @param message: The original message.
        @param callable: The function to call to handle the message.
            C{args} and C{kwargs} are passed to it.
        """
        try:
            text = callable(*args, **kwargs)
        except:
            status = FAILED
            cls, obj = sys.exc_info()[:2]
            text = "%s: %s" % (cls.__name__, obj)
            exception("Error occured running message handler %s "
                      "with args %r %r.",
                      format_object(callable), args, kwargs)
        else:
            status = SUCCEEDED
        operation_result = {"type": "operation-result", "status": status,
                            "operation-id": message["operation-id"]}
        if text:
            operation_result["result-text"] = text
        return self.registry.broker.send_message(operation_result, urgent=True)
