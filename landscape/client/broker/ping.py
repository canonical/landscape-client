"""
Implementation of a lightweight exchange-triggering mechanism via
small HTTP requests asking if we should do a full exchange.

Ping Sequence
=============

Diagram::

  1. BrokerService --> Pinger              :  Start

  2. [Loop forever]
  |
  |  2.1 Pinger     --> PingClient         :  Schedule Ping
  |
  |  2.2 PingClient --> {Server} WebPing   :  Ping
  |
  |  2.3 PingClient <-- {Server} WebPing   :  return(messages waiting?
  |                                        :    [Boolean])
  |
  |  2.4 Pinger     <-- PingClient         :  return(messages waiting?
  |                                             [Boolean])
  |
  |  2.5 [If: messages waiting == True ]
  |    |
  |    |  2.5.1 Pinger --> MessageExchange  :  Schedule urgent exchange
  |    |
  |    --[End If]
  |
  |  2.6 [Wait: for ping interval to expire]
  |
  --[End Loop]

"""

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

from logging import info

from twisted.python.failure import Failure
from twisted.internet import defer

from landscape.lib import bpickle
from landscape.lib.fetch import fetch
from landscape.lib.log import log_failure


class PingClient(object):
    """An HTTP client which knows how to talk to the ping server."""

    def __init__(self, reactor, get_page=None):
        if get_page is None:
            get_page = fetch
        self._reactor = reactor
        self.get_page = get_page

    def ping(self, url, insecure_id):
        """Ask the question: are there messages for this computer ID?

        @param url: The URL of the ping server to hit.
        @param insecure_id: This client's insecure ID, if C{None} no HTTP
            request will be performed and the result will be C{False}.

        @return: A deferred resulting in True if there are messages
            and False otherwise.
        """
        if insecure_id is not None:
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            data = urlencode({"insecure_id": insecure_id})
            page_deferred = defer.Deferred()

            def errback(type, value, tb):
                page_deferred.errback(Failure(value, type, tb))
            self._reactor.call_in_thread(page_deferred.callback, errback,
                                         self.get_page, url,
                                         post=True, data=data,
                                         headers=headers)
            page_deferred.addCallback(self._got_result)
            return page_deferred
        return defer.succeed(False)

    def _got_result(self, webtext):
        """
        Given a response that came from a ping server, return True if
        the response indicates that their are messages waiting for
        this computer, False otherwise.
        """
        if bpickle.loads(webtext) == {"messages": True}:
            return True


class Pinger(object):
    """
    A plugin which pings the Landscape server with HTTP requests to
    see if a full exchange should be initiated.

    @param reactor: The reactor to schedule calls with.
    @param identity: The L{Identity} holding the insecure ID used when pinging.
    @param exchanger: The L{MessageExchange} to trigger exchanges with.
    @param config: The L{BrokerConfiguration} to get the 'ping_url' and
        'ping_interval' parameters from. The 'ping_url' specifies what URL
        to hit when pinging, and 'ping_interval' how frequently to ping.
        Changes in the configuration object will take effect from the next
        scheduled ping.
    """

    def __init__(self, reactor, identity, exchanger, config,
                 ping_client_factory=PingClient):
        self._config = config
        self._identity = identity
        self._reactor = reactor
        self._exchanger = exchanger
        self._call_id = None
        self._ping_client = None
        self.ping_client_factory = ping_client_factory
        reactor.call_on("message", self._handle_set_intervals)

    def get_url(self):
        return self._config.ping_url

    def get_interval(self):
        return self._config.ping_interval

    def start(self):
        """Start pinging."""
        self._ping_client = self.ping_client_factory(self._reactor)
        self._schedule()

    def ping(self):
        """Perform a ping; if there are messages, fire an exchange."""
        deferred = self._ping_client.ping(
            self._config.ping_url, self._identity.insecure_id)
        deferred.addCallback(self._got_result)
        deferred.addErrback(self._got_error)
        deferred.addBoth(lambda _: self._schedule())

    def _got_result(self, exchange):
        if exchange:
            info("Ping indicates message available. "
                 "Scheduling an urgent exchange.")
            self._exchanger.schedule_exchange(urgent=True)

    def _got_error(self, failure):
        log_failure(failure,
                    "Error contacting ping server at %s" %
                    (self._ping_client.url,))

    def _schedule(self):
        """Schedule a new ping using the current ping interval."""
        self._call_id = self._reactor.call_later(self._config.ping_interval,
                                                 self.ping)

    def _handle_set_intervals(self, message):
        if message["type"] == "set-intervals" and "ping" in message:
            self._config.ping_interval = message["ping"]
            self._config.write()
            info("Ping interval set to %d seconds." %
                 self._config.ping_interval)
        if self._call_id is not None:
            self._reactor.cancel_call(self._call_id)
            self._schedule()

    def stop(self):
        """Stop pinging the message server."""
        if self._call_id is not None:
            self._reactor.cancel_call(self._call_id)
            self._call_id = None


class FakePinger(object):

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass
