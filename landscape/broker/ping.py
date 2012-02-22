"""
Implementation of a lightweight exchange-triggering mechanism via
small HTTP requests asking if we should do a full exchange.
"""

import urllib
import logging
from logging import info

from twisted.python.failure import Failure
from twisted.internet import defer

from landscape.lib.bpickle import loads
from landscape.lib.fetch import fetch
from landscape.lib.log import log_failure


class PingClient(object):
    """An HTTP client which asks: Are there messages for computer X?

    @param url: The URL to ask the question to.
    @type identity: L{landscape.broker.registration.Identity}
    @param identity: This client's identity.
    @param get_page: The method to use to retrieve content.  If not specified,
        landscape.lib.fetch.fetch is used.
    """

    def __init__(self, reactor, url, identity, get_page=None):
        if get_page is None:
            get_page = fetch
        self._reactor = reactor
        self._identity = identity
        self.get_page = get_page
        self.url = url

    def ping(self):
        """Ask the question.

        Hits the URL previously specified with the insecure_id gotten
        from the identity.

        @return: A deferred resulting in True if there are messages
            and False otherwise.
        """
        insecure_id = self._identity.insecure_id
        if insecure_id is not None:
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            data = urllib.urlencode({"insecure_id": insecure_id})
            page_deferred = defer.Deferred()

            def errback(type, value, tb):
                page_deferred.errback(Failure(value, type, tb))
            self._reactor.call_in_thread(page_deferred.callback, errback,
                                         self.get_page, self.url,
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
        if loads(webtext) == {"messages": True}:
            return True


class Pinger(object):
    """
    A plugin which pings the Landscape server with HTTP requests to
    see if a full exchange should be initiated.

    @param reactor: The reactor to schedule calls with
    @param url: The URL to ping
    @param interval: How often to send the pings
    @param exchanger: The L{landscape.broker.exchange.MessageExchange} to
        trigger exchanges with.
    """

    def __init__(self, reactor, url, identity, exchanger,
                 interval=30, ping_client_factory=PingClient):
        self._url = url
        self._interval = interval
        self._identity = identity
        self._reactor = reactor
        self._exchanger = exchanger
        self._call_id = None
        self._ping_client = None
        self.ping_client_factory = ping_client_factory
        reactor.call_on("message", self._handle_set_intervals)

    def get_url(self):
        return self._url

    def set_url(self, url):
        self._url = url
        if self._ping_client is not None:
            self._ping_client.url = url

    def get_interval(self):
        return self._interval

    def start(self):
        """Start pinging."""
        self._ping_client = self.ping_client_factory(
            self._reactor, self._url, self._identity)
        self._call_id = self._reactor.call_every(self._interval, self.ping)

    def ping(self):
        """Perform a ping; if there are messages, fire an exchange."""
        ping_deferred = self._ping_client.ping()
        ping_deferred.addCallback(self._got_result)
        ping_deferred.addErrback(self._got_error)

    def _got_result(self, exchange):
        if exchange:
            info("Ping indicates message available. "
                 "Scheduling an urgent exchange.")
            self._exchanger.schedule_exchange(urgent=True)

    def _got_error(self, failure):
        log_failure(failure,
                    "Error contacting ping server at %s" %
                    (self._ping_client.url,))

    def _handle_set_intervals(self, message):
        if message["type"] == "set-intervals" and "ping" in message:
            self._interval = message["ping"]
            info("Ping interval set to %d seconds." % self._interval)
        if self._call_id is not None:
            self._reactor.cancel_call(self._call_id)
            self._call_id = self._reactor.call_every(self._interval, self.ping)


class FakePinger(object):

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass
