from twisted.internet.defer import maybeDeferred

from landscape.lib.format import format_object
from landscape.lib.log import log_failure
from landscape.client.broker.client import BrokerClientPlugin

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

        The function can also return a C{Deferred}, and the behavior above
        still applies.

        @param message: The original message.
        @param callable: The function to call to handle the message.
            C{args} and C{kwargs} are passed to it.
        """
        deferred = maybeDeferred(callable, *args, **kwargs)

        def success(text):
            return SUCCEEDED, text

        def failure(failure):
            text = "%s: %s" % (failure.type.__name__, failure.value)
            msg = ("Error occured running message handler %s with "
                   "args %r %r.", format_object(callable), args, kwargs)
            log_failure(failure, msg=msg)
            return FAILED, text

        def send(args):
            status, text = args
            result = {"type": "operation-result",
                      "status": status,
                      "operation-id": message["operation-id"]}
            if text:
                result["result-text"] = text
            return self.manager.broker.send_message(
                result, self._session_id, urgent=True)

        deferred.addCallback(success)
        deferred.addErrback(failure)
        deferred.addCallback(send)

        return deferred
