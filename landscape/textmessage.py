"""
Support code for the C{landscape-message} utility, which sends a text
message to the Landscape web UI via the landscape-client's dbus
messaging service (see L{landscape.plugins.dbus_message}).
"""

import sys
from optparse import OptionParser

from twisted.python import log
from twisted.python.failure import Failure
from twisted.internet.defer import fail

from landscape.lib.dbus_util import (
    get_bus, SecurityError, ServiceUnknownError, NoReplyError)

from landscape import VERSION
from landscape.broker.broker import BUS_NAME
from landscape.broker.remote import RemoteBroker


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

    @param broker: The L{landscape.broker.remote.RemoteBroker}
        object to use to send the message.
    @return: A L{Deferred} which will fire with the result of the send.
    @raise ServiceUnknownError: (Deferred) if an
        org.freedesktop.DBus.Error.ServiceUnknown is raised from DBUS.
    @raise SecurityError: (Deferred) if a security policy prevents
        sending the message.
    """
    message = {"type": "text-message", "message": text}
    response = broker.send_message(message, True)
    return response


def got_result(result):
    print u"Message sent."


def got_error(failure):
    """
    An error occurred. Attempt to write a meaningful message if it's
    an error we know about, otherwise just print the exception value.
    """
    print u"Failure sending message."
    if failure.check(ServiceUnknownError):
        print "Couldn't find the %s service." % BUS_NAME
        print "Is the Landscape Client running?"
    elif failure.check(SecurityError, NoReplyError):
        print "Couldn't access the %s service." % BUS_NAME
        print "You may need to run landscape-message as root."
    elif failure.check(AcceptedTypeError):
        print ("Server not accepting text messages.  "
               "Is Landscape Client registered with the server?")
    else:
        print "Unknown error:", failure.type, failure.getErrorMessage()


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
    from twisted.internet import reactor

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
    import dbus.glib
    from twisted.internet.glib2reactor import install
    install()
    from twisted.internet import reactor

    parser = OptionParser(version=VERSION)
    parser.add_option("-b", "--bus", default="system",
                      help="The DBUS bus to use to send the message.")
    options, args = parser.parse_args(args)

    try:
        broker = RemoteBroker(get_bus(options.bus))
    except:
        got_error(Failure())
        return

    result = broker.get_accepted_message_types()
    result.addCallback(got_accepted_types, broker, args)
    result.addErrback(got_error)
    result.addBoth(lambda x: reactor.callWhenRunning(reactor.stop))
    reactor.run()
