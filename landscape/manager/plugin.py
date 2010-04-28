import sys

from logging import exception

from landscape.log import format_object
from landscape.broker.client import BrokerClientPlugin

# Protocol messages! Same constants are defined in the server.
FAILED = 5
SUCCEEDED = 6


class ManagerPlugin(BrokerClientPlugin):

    @property
    def manager(self):
        """An alias for the C{client} attribute}."""
        return self.client

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
        return self.manager.broker.send_message(operation_result, urgent=True)
