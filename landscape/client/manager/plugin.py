import logging
from pathlib import Path
from typing import Optional

from twisted.internet.defer import maybeDeferred

from landscape.client import GROUP
from landscape.client import USER
from landscape.client.broker.client import BrokerClientPlugin
from landscape.lib.format import format_object
from landscape.lib.log import log_failure
from landscape.lib.persist import Persist

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
            text = f"{failure.type.__name__}: {failure.value}"
            msg = (
                "Error occured running message handler %s with " "args %r %r.",
                format_object(callable),
                args,
                kwargs,
            )
            log_failure(failure, msg=msg)
            return FAILED, text

        def send(args):
            status, text = args
            result = {
                "type": "operation-result",
                "status": status,
                "operation-id": message["operation-id"],
            }
            if text:
                result["result-text"] = text
            return self.manager.broker.send_message(
                result,
                self._session_id,
                urgent=True,
            )

        deferred.addCallback(success)
        deferred.addErrback(failure)
        deferred.addCallback(send)

        return deferred


class DataWatcherManager(ManagerPlugin):
    """
    A utility for plugins which send data to the Landscape server
    which does not constantly change. New messages will only be sent
    when the result of get_data() has changed since the last time it
    was called. Note this is the same as the DataWatcher plugin but
    for Manager plugins instead of Monitor.Subclasses should provide
    a get_data method
    """

    message_type: Optional[str] = None

    def __init__(self):
        super().__init__()
        self._persist = None

    def register(self, registry):
        super().register(registry)
        self._persist_filename = Path(
            self.registry.config.data_path,
            self.message_type + '.manager.bpkl',
        )
        self._persist = Persist(
            filename=self._persist_filename,
            user=USER,
            group=GROUP
        )
        self.call_on_accepted(self.message_type, self.send_message)

    def run(self):
        return self.registry.broker.call_if_accepted(
            self.message_type,
            self.send_message,
        )

    def send_message(self):
        """Send a message to the broker if the data has changed since the last
        call"""
        result = self.get_new_data()
        if not result:
            logging.debug("{} unchanged so not sending".format(
                          self.message_type))
            return
        logging.debug("Sending new {} data!".format(self.message_type))
        message = {"type": self.message_type, self.message_type: result}
        return self.registry.broker.send_message(message, self._session_id)

    def get_new_data(self):
        """Returns the data only if it has changed"""
        data = self.get_data()
        if self._persist is None:  # Persist not initialized yet
            return data
        elif self._persist.get("data") != data:
            self._persist.set("data", data)
            return data
        else:  # Data not changed
            return None

    def get_data(self):
        """
        The result of this will be cached and subclasses must implement this
        and return the correct return type defined in the server bound message
        schema
        """
        raise NotImplementedError("Subclasses must implement get_data()")

    def _reset(self):
        """Reset the persist."""
        if self._persist:
            self._persist.remove("data")
