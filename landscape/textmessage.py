"""
Support code for the C{landscape-message} utility, which sends a text
message to the Landscape web UI via the landscape-client's dbus
messaging service (see L{landscape.plugins.dbus_message}).
"""

import sys

from landscape.lib.log import log_failure
from landscape.reactor import LandscapeReactor
from landscape.broker.amp import RemoteBrokerConnector
from landscape.deployment import Configuration


class AcceptedTypeError(Exception):
    """
    Raised when a message is sent without 'text-message' being an
    accepted type.
    """


class EmptyMessageError(Exception):
    """Raised when an empty message is provied."""


def send_message(text, broker):
    """Add a message to the queue via a remote broker.

    The message is of type C{text-message}.

    @param broker: A connected L{RemoteBroker} object to use to send
        the message.
    @return: A L{Deferred} which will fire with the result of the send.
    """
    def got_session_id(session_id):
        response = broker.send_message(message, session_id, True)
        return response

    message = {"type": "text-message", "message": text}
    result = broker.get_session_id()
    result.addCallback(got_session_id)
    return result


def got_result(result):
    print u"Message sent."


def get_message(args):
    encoding = sys.stdin.encoding or "UTF-8"
    if len(args) < 2:
        print ("Please enter your message, and send EOF (Control + D after "
               "newline) when done.")
        message = sys.stdin.read().decode(encoding)
    else:
        message = u" ".join([x.decode(encoding) for x in args[1:]])
    if not message:
        raise EmptyMessageError("Text messages may not be empty.")
    return message


def got_accepted_types(accepted_types, broker, args):
    if not "text-message" in accepted_types:
        raise AcceptedTypeError("Text messages may not be created.  Is "
                                "Landscape Client registered with the server?")
    message = get_message(args)
    d = send_message(message, broker)
    d.addCallback(got_result)
    return d


def run(args=sys.argv):
    """Send a message to Landscape.

    This function runs a Twisted reactor, prints various status
    messages, and exits the process.
    """
    reactor = LandscapeReactor()
    config = Configuration()
    config.load(args)

    def got_connection(broker):
        result = broker.get_accepted_message_types()
        return result.addCallback(got_accepted_types, broker, args)

    def got_error(failure):
        log_failure(failure)

    connector = RemoteBrokerConnector(reactor, config)
    result = connector.connect()
    result.addCallback(got_connection)
    result.addErrback(got_error)
    result.addBoth(lambda x: connector.disconnect())

    # For some obscure reason our LandscapeReactor.stop method calls
    # reactor.crash() instead of reactor.stop(), which doesn't work
    # here. Maybe LandscapeReactor.stop should simply use reactor.stop().
    result.addBoth(lambda ignored: reactor.call_later(
        0, reactor._reactor.stop))

    reactor.run()

    return result
