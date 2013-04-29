from twisted.internet import reactor
from twisted.internet.error import ConnectError, ConnectionDone
from twisted.internet.task import Clock
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase

from landscape.lib.amp import (
    MethodCallError, MethodCallServerProtocol, MethodCallClientProtocol,
    MethodCallServerFactory, MethodCallClientFactory, RemoteObject,
    MethodCallSender)
from landscape.tests.helpers import LandscapeTest


class FakeTransport(object):
    """Accumulate written data into a list."""

    def __init__(self, connection):
        self.stream = []
        self.connection = connection

    def write(self, data):
        self.stream.append(data)

    def loseConnection(self):
        raise NotImplemented()

    def getPeer(self):
        pass

    def getHost(self):
        pass


class FakeConnection(object):
    """Simulate a connection between a client and a server protocol."""

    def __init__(self, client, server):
        self.client = client
        self.server = server

    def make(self):
        self.server.makeConnection(FakeTransport(self))
        self.client.makeConnection(FakeTransport(self))

    def lose(self, connector, reason):
        self.server.connectionLost(reason)
        self.client.connectionLost(reason)
        self.client.factory.clientConnectionLost(connector, reason)

    def flush(self):
        """
        Notify the server of any data written by the client and viceversa.
        """
        while True:
            if self.client.transport and self.client.transport.stream:
                self.server.dataReceived(self.client.transport.stream.pop(0))
            elif self.server.transport and self.server.transport.stream:
                self.client.dataReceived(self.server.transport.stream.pop(0))
            else:
                break


class FakeConnector(object):
    """Make L{FakeConnection}s using the given server and client factories."""

    def __init__(self, client, server):
        self.client = client
        self.server = server
        self.connection = None

    @property
    def factory(self):
        return self.client

    def connect(self):
        self.connection = FakeConnection(self.client.buildProtocol(None),
                                         self.server.buildProtocol(None))

        # XXX Let the client factory be aware of this fake connection, so
        # it can flush it when needed. This is to workaround AMP not
        # supporting synchronous transports
        self.client.connection = self.connection

        self.connection.make()

    def disconnect(self):
        self.connection.lose(self, Failure(ConnectionDone()))


class WordsException(Exception):
    """Test exception."""


class Words(object):
    """
    Test class to be used as target object of a L{MethodCallServerFactory}.
    """

    def __init__(self, clock=None):
        self._clock = clock

    def secret(self):
        raise RuntimeError("I'm not supposed to be called!")

    def empty(self):
        pass

    def motd(self):
        return "Words are cool"

    def capitalize(self, word):
        return word.capitalize()

    def is_short(self, word):
        return len(word) < 4

    def concatenate(self, word1, word2):
        return word1 + word2

    def lower_case(self, word, index=None):
        if index is None:
            return word.lower()
        else:
            return word[:index] + word[index:].lower()

    def multiply_alphabetically(self, word_times):
        result = ""
        for word, times in sorted(word_times.iteritems()):
            result += word * times
        return result

    def meaning_of_life(self):

        class Complex(object):
            pass
        return Complex()

    def _check(self, word, seed, value=3):
        if seed == "cool" and value == 4:
            return "Guessed!"

    def guess(self, word, *args, **kwargs):
        return self._check(word, *args, **kwargs)

    def translate(self, word):
        raise WordsException("Unknown word")

    def google(self, word):
        deferred = Deferred()
        if word == "Landscape":
            self._clock.callLater(0.01, lambda: deferred.callback("Cool!"))
        elif word == "Easy query":
            deferred.callback("Done!")
        elif word == "Weird stuff":
            error = Exception("bad")
            self._clock.callLater(0.01, lambda: deferred.errback(error))
        elif word == "Censored":
            deferred.errback(Exception("very bad"))
        elif word == "Long query":
            # Do nothing, the deferred won't be fired at all
            pass
        elif word == "Slowish query":
            # Fire the result after a while.
            self._clock.callLater(120.0, lambda: deferred.callback("Done!"))
        return deferred


METHODS = ["empty",
           "motd",
           "capitalize",
           "is_short",
           "concatenate",
           "lower_case",
           "multiply_alphabetically",
           "translate",
           "meaning_of_life",
           "guess",
           "google"]


class MethodCallTest(LandscapeTest):

    def setUp(self):
        super(MethodCallTest, self).setUp()
        server = MethodCallServerProtocol(Words(), METHODS)
        client = MethodCallClientProtocol()
        self.connection = FakeConnection(client, server)
        self.connection.make()
        self.clock = Clock()
        self.sender = MethodCallSender(client, self.clock)

    def test_with_forbidden_method(self):
        """
        If a method is not included in L{MethodCallServerFactory.methods} it
        can't be called.
        """
        deferred = self.sender.send_method_call(method="secret",
                                                args=[],
                                                kwargs={})
        self.connection.flush()
        self.failureResultOf(deferred).trap(MethodCallError)

    def test_with_no_arguments(self):
        """
        A connected client can issue a L{MethodCall} without arguments and
        with an empty response.
        """
        deferred = self.sender.send_method_call(method="empty",
                                                args=[],
                                                kwargs={})
        self.connection.flush()
        self.assertIs(None, self.successResultOf(deferred))

    def test_with_return_value(self):
        """
        A connected client can issue a L{MethodCall} targeted to an
        object method with a return value.
        """
        deferred = self.sender.send_method_call(method="motd",
                                                args=[],
                                                kwargs={})
        self.connection.flush()
        self.assertEqual("Words are cool", self.successResultOf(deferred))

    def test_with_one_argument(self):
        """
        A connected AMP client can issue a L{MethodCall} with one argument and
        a response value.
        """
        deferred = self.sender.send_method_call(method="capitalize",
                                                args=["john"],
                                                kwargs={})
        self.connection.flush()
        self.assertEqual("John", self.successResultOf(deferred))

    def test_with_boolean_return_value(self):
        """
        The return value of a L{MethodCall} argument can be a boolean.
        """
        deferred = self.sender.send_method_call(method="is_short",
                                                args=["hi"],
                                                kwargs={})
        self.connection.flush()
        self.assertTrue(self.successResultOf(deferred))

    def test_with_many_arguments(self):
        """
        A connected client can issue a L{MethodCall} with many arguments.
        """
        deferred = self.sender.send_method_call(method="concatenate",
                                                args=["We ", "rock"],
                                                kwargs={})
        self.connection.flush()
        self.assertEqual("We rock", self.successResultOf(deferred))

    def test_with_default_arguments(self):
        """
        A connected client can issue a L{MethodCall} for methods having
        default arguments.
        """
        deferred = self.sender.send_method_call(method="lower_case",
                                                args=["OHH"],
                                                kwargs={})
        self.connection.flush()
        self.assertEqual("ohh", self.successResultOf(deferred))

    def test_with_overriden_default_arguments(self):
        """
        A connected client can issue a L{MethodCall} with keyword arguments
        having default values in the target object.  If a value is specified by
        the caller it will be used in place of the default value
        """
        deferred = self.sender.send_method_call(method="lower_case",
                                                args=["OHH"],
                                                kwargs={"index": 2})
        self.connection.flush()
        self.assertEqual("OHh", self.successResultOf(deferred))

    def test_with_dictionary_arguments(self):
        """
        Method arguments passed to a L{MethodCall} can be dictionaries.
        """
        deferred = self.sender.send_method_call(method="multiply_"
                                                       "alphabetically",
                                                args=[{"foo": 2, "bar": 3}],
                                                kwargs={})
        self.connection.flush()
        self.assertEqual("barbarbarfoofoo", self.successResultOf(deferred))

    def test_with_non_serializable_return_value(self):
        """
        If the target object method returns an object that can't be serialized,
        the L{MethodCall} result is C{None}.
        """
        deferred = self.sender.send_method_call(method="meaning_of_life",
                                                args=[],
                                                kwargs={})
        self.connection.flush()
        self.failureResultOf(deferred).trap(MethodCallError)

    def test_with_long_argument(self):
        """
        The L{MethodCall} protocol supports sending method calls with arguments
        bigger than the maximum AMP parameter value size.
        """
        deferred = self.sender.send_method_call(method="is_short",
                                                args=["!" * 65535],
                                                kwargs={})
        self.connection.flush()
        self.assertFalse(self.successResultOf(deferred))

    def test_with_long_argument_multiple_calls(self):
        """
        The L{MethodCall} protocol supports concurrently sending multiple
        method calls with arguments bigger than the maximum AMP value size.
        """
        deferred1 = self.sender.send_method_call(method="is_short",
                                                 args=["!" * 80000],
                                                 kwargs={})
        deferred2 = self.sender.send_method_call(method="is_short",
                                                 args=["*" * 90000],
                                                 kwargs={})

        self.connection.flush()
        self.assertFalse(self.successResultOf(deferred1))
        self.assertFalse(self.successResultOf(deferred2))

    def test_translate(self):
        """
        If the target object method raises an exception, the remote call fails
        with a L{MethodCallError}.
        """
        deferred = self.sender.send_method_call(method="translate",
                                                args=["hi"],
                                                kwargs={})
        self.connection.flush()
        self.failureResultOf(deferred).trap(MethodCallError)


class RemoteObjectTest(LandscapeTest):

    def setUp(self):
        super(RemoteObjectTest, self).setUp()
        self.clock = Clock()
        self.factory = MethodCallClientFactory(self.clock)
        server_factory = MethodCallServerFactory(Words(self.clock), METHODS)
        self.connector = FakeConnector(self.factory, server_factory)
        self.connector.connect()
        self.remote = self.successResultOf(self.factory.getRemoteObject())

    def test_method_call_sender_with_forbidden_method(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and withj
        an empty response.
        """
        deferred = self.remote.secret()
        self.failureResultOf(deferred).trap(MethodCallError)

    def test_with_no_arguments(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and withj
        an empty response.
        """
        deferred = self.remote.empty()
        self.assertIs(None, self.successResultOf(deferred))

    def test_with_return_value(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and get
        back the value of the commands's response.
        """
        deferred = self.remote.motd()
        self.assertEqual("Words are cool", self.successResultOf(deferred))

    def test_with_one_argument(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with one argument and get
        the response value.
        """
        deferred = self.remote.capitalize("john")
        self.assertEqual("John", self.successResultOf(deferred))

    def test_with_one_keyword_argument(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with a named argument.
        """
        deferred = self.remote.capitalize(word="john")
        self.assertEqual("John", self.successResultOf(deferred))

    def test_with_boolean_return_value(self):
        """
        The return value of a L{MethodCall} argument can be a boolean.
        """
        return self.assertSuccess(self.remote.is_short("hi"), True)

    def test_with_many_arguments(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with more than one argument.
        """
        deferred = self.remote.concatenate("You ", "rock")
        self.assertEqual("You rock", self.successResultOf(deferred))

    def test_with_many_keyword_arguments(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with several
        named arguments.
        """
        deferred = self.remote.concatenate(word2="rock", word1="You ")
        self.assertEqual("You rock", self.successResultOf(deferred))

    def test_with_default_arguments(self):
        """
        A L{RemoteObject} can send a L{MethodCall} having an argument with
        a default value.
        """
        deferred = self.remote.lower_case("OHH")
        self.assertEqual("ohh", self.successResultOf(deferred))

    def test_with_overriden_default_arguments(self):
        """
        A L{RemoteObject} can send L{MethodCall}s overriding the default
        value of an argument.
        """
        deferred = self.remote.lower_case("OHH", 2)
        self.assertEqual("OHh", self.successResultOf(deferred))

    def test_with_dictionary_arguments(self):
        """
        A L{RemoteObject} can send a L{MethodCall}s for methods requiring
        a dictionary arguments.
        """
        deferred = self.remote.multiply_alphabetically({"foo": 2, "bar": 3})
        self.assertEqual("barbarbarfoofoo", self.successResultOf(deferred))

    def test_with_generic_args_and_kwargs(self):
        """
        A L{RemoteObject} behaves well with L{MethodCall}s for methods
        having generic C{*args} and C{**kwargs} arguments.
        """
        deferred = self.remote.guess("word", "cool", value=4)
        self.assertEqual("Guessed!", self.successResultOf(deferred))

    def test_with_successful_deferred(self):
        """
        If the target object method returns a L{Deferred}, it is handled
        transparently.
        """
        result = []
        deferred = self.remote.google("Landscape")
        deferred.addCallback(result.append)

        # At this point the receiver is waiting for method to complete, so
        # the deferred has not fired yet
        self.assertEqual([], result)

        # Simulate time advancing and the receiver responding
        self.clock.advance(0.5)
        self.connector.connection.flush()

        self.assertEqual(["Cool!"], result)

    def test_with_failing_deferred(self):
        """
        If the target object method returns a failing L{Deferred}, a
        L{MethodCallError} is raised.
        """
        result = []
        deferred = self.remote.google("Weird stuff")
        deferred.addErrback(result.append)

        # At this point the receiver is waiting for method to complete, so
        # the deferred has not fired yet
        self.assertEqual([], result)

        # Simulate time advancing and the receiver responding
        self.clock.advance(0.5)
        self.connector.connection.flush()

        [failure] = result
        failure.trap(MethodCallError)

    def test_with_already_callback_deferred(self):
        """
        The target object method can return an already fired L{Deferred}.
        """
        deferred = self.remote.google("Easy query")
        self.assertEqual("Done!", self.successResultOf(deferred))

    def test_with_already_errback_deferred(self):
        """
        If the target object method can return an already failed L{Deferred}.
        """
        deferred = self.remote.google("Censored")
        self.failureResultOf(deferred).trap(MethodCallError)

    def test_with_deferred_timeout(self):
        """
        If the peer protocol doesn't send a response for a deferred within
        the given timeout, the method call fails.
        """
        result = []
        deferred = self.remote.google("Long query")
        deferred.addErrback(result.append)

        self.clock.advance(60.0)

        [failure] = result
        failure.trap(MethodCallError)

    def test_with_late_response(self):
        """
        If the peer protocol sends a late response for a request that has
        already timeout, that response is ignored.
        """
        result = []
        deferred = self.remote.google("Slowish query")
        deferred.addErrback(result.append)

        self.clock.advance(120.0)

        [failure] = result
        failure.trap(MethodCallError)

    def test_method_call_error(self):
        """
        If a L{MethodCall} fails due to a L{MethodCallError},
        the L{RemoteObject} won't try to perform it again, even if the
        C{retryOnReconnect} error is set, as a L{MethodCallError} is a
        permanent failure that is not likely to ever succeed.
        """
        self.factory.retryOnReconnect = True
        deferred = self.remote.secret()
        self.failureResultOf(deferred).trap(MethodCallError)

    def test_retry(self):
        """
        If the connection is lost and C{retryOnReconnect} is C{True} on the
        factory, the L{RemoteObject} will transparently retry to perform
        the L{MethodCall} requests that failed due to the broken connections.
        """
        self.factory.factor = 0.19
        self.factory.retryOnReconnect = True
        self.connector.disconnect()
        deferred = self.remote.capitalize("john")

        # The deferred has not fired yet, because it's been put in the pending
        # queue, till the call gets a chance to be retried upon reconnection
        self.assertFalse(deferred.called)

        # Time passes and the factory successfully reconnects
        self.clock.advance(1)

        # We finally get the result
        self.assertEqual("John", self.successResultOf(deferred))

    def test_retry_with_method_call_error(self):
        """
        If a retried L{MethodCall} request fails due to a L{MethodCallError},
        the L{RemoteObject} will properly propagate the error to the original
        caller.
        """
        self.factory.factor = 0.19
        self.factory.retryOnReconnect = True
        self.connector.disconnect()
        deferred = self.remote.secret()

        # The deferred has not fired yet, because it's been put in the pending
        # queue, till the call gets a chance to be retried upon reconnection
        self.assertFalse(deferred.called)

        # Time passes and the factory successfully reconnects
        self.clock.advance(1)

        failure = self.failureResultOf(deferred)
        self.assertEqual("Forbidden method 'secret'", str(failure.value))


class MethodCallClientFactoryTest(LandscapeTest):

    def setUp(self):
        super(MethodCallClientFactoryTest, self).setUp()
        self.clock = Clock()
        self.factory = MethodCallClientFactory(self.clock)

    def test_max_delay(self):
        """
        The L{MethodCallClientFactory} class has a default value of 30 seconds
        for the maximum reconnection delay.
        """
        self.assertEqual(self.factory.maxDelay, 30)

    def test_connect_notifier(self):
        """
        The C{notifyOnConnect} method supports specifying a callback that
        will be invoked when a the connection has been established.
        """
        protocols = []
        self.factory.notifyOnConnect(protocols.append)
        protocol = self.factory.buildProtocol(None)
        protocol.connectionMade()
        self.assertEqual([protocol], protocols)

    def test_connect_notifier_with_reconnect(self):
        """
        The C{notifyOnConnect} fires the callbacks also then a connection is
        re-established after it was lost.
        """
        protocols = []
        self.factory.notifyOnConnect(protocols.append)
        protocol1 = self.factory.buildProtocol(None)
        protocol1.connectionMade()
        protocol2 = self.factory.buildProtocol(None)
        protocol2.connectionMade()
        self.assertEqual([protocol1, protocol2], protocols)

    def test_get_remote_object(self):
        """
        The C{getRemoteObject} method returns a deferred firing with a
        connected L{RemoteBroker}.
        """
        deferred = self.factory.getRemoteObject()
        protocol = self.factory.buildProtocol(None)
        protocol.connectionMade()
        self.assertIsInstance(self.successResultOf(deferred), RemoteObject)

    def test_get_remote_object_failure(self):
        """
        If the factory fails to establish a connection the deferreds returned
        by C{getRemoteObject} will fail.
        """
        deferred = self.factory.getRemoteObject()
        self.factory.continueTrying = False  # Don't retry
        self.factory.clientConnectionFailed(None, Failure(ConnectError()))
        self.failureResultOf(deferred).trap(ConnectError)

    def test_client_connection_failed(self):
        """
        The L{MethodCallClientFactory} keeps trying to connect if maxRetries
        is not reached.
        """
        class FakeConnector(object):
            called = False

            def connect(self):
                self.called = True

        connector = FakeConnector()
        self.assertEqual(self.factory.retries, 0)
        self.factory.clientConnectionFailed(connector, None)
        self.assertEqual(self.factory.retries, 1)
        self.clock.advance(5)
        self.assertTrue(connector.called)

    def test_reconnect(self):
        """
        If the connection is lost, the L{RemoteObject} created by the creator
        will transparently handle the reconnection.
        """
        server_factory = MethodCallServerFactory(Words(self.clock), METHODS)
        connector = FakeConnector(self.factory, server_factory)
        connector.connect()
        remote = self.successResultOf(self.factory.getRemoteObject())

        connector.disconnect()
        self.clock.advance(5)
        deferred = remote.empty()
        self.assertIsNone(self.successResultOf(deferred))


class MethodCallFunctionalTest(TestCase):

    def setUp(self):
        super(MethodCallFunctionalTest, self).setUp()
        self.socket = self.mktemp()
        self.server = MethodCallServerFactory(Words(reactor), METHODS)
        self.client = MethodCallClientFactory(reactor)
        self.port = reactor.listenUNIX(self.socket, self.server)
        #self.client.maxRetries = 0  # By default, don't try to reconnect

    def tearDown(self):
        super(MethodCallFunctionalTest, self).tearDown()
        self.port.stopListening()

    @inlineCallbacks
    def test_connect(self):
        """
        The L{RemoteObject} resulting form the deferred returned by
        L{MethodCallClientFactory.getRemoteObject} is properly connected
        to the remote peer.
        """
        connector = reactor.connectUNIX(self.socket, self.client)
        remote = yield self.client.getRemoteObject()
        result = yield remote.capitalize("john")
        self.assertEqual(result, "John")
        self.client.stopTrying()
        connector.disconnect()

    @inlineCallbacks
    def test_connect_with_max_retries(self):
        """
        If L{MethodCallClientFactory.maxRetries} is set, then the factory
        will give up trying to connect after that amout of times.
        """
        self.port.stopListening()
        self.client.maxRetries = 0
        reactor.connectUNIX(self.socket, self.client)
        yield self.assertFailure(self.client.getRemoteObject(), ConnectError)

    @inlineCallbacks
    def test_reconnect(self):
        """
        If the connection is lost, the L{RemoteObject} created by the factory
        will transparently handle the reconnection.
        """
        self.client.factor = 0.01  # Try reconnecting very quickly
        connector = reactor.connectUNIX(self.socket, self.client)
        remote = yield self.client.getRemoteObject()

        # Disconnect and wait till we connect again
        deferred = Deferred()
        self.client.notifyOnConnect(deferred.callback)
        connector.disconnect()
        yield deferred

        # The remote object is still working
        result = yield remote.capitalize("john")
        self.assertEqual(result, "John")
        self.client.stopTrying()
        connector.disconnect()

    @inlineCallbacks
    def test_retry(self):
        """
        If the connection is lost, the L{RemoteObject} created by the creator
        will transparently retry to perform the L{MethodCall} requests that
        failed due to the broken connection.
        """
        self.client.factor = 0.01  # Try reconnecting very quickly
        self.client.retryOnReconnect = True
        connector = reactor.connectUNIX(self.socket, self.client)
        remote = yield self.client.getRemoteObject()

        # Disconnect
        connector.disconnect()

        # This call will fail but it's transparently retried
        result = yield remote.capitalize("john")
        self.assertEqual(result, "John")
        self.client.stopTrying()
        connector.disconnect()

    @inlineCallbacks
    def test_retry_with_method_call_error(self):
        """
        If a retried L{MethodCall} request fails due to a L{MethodCallError},
        the L{RemoteObject} will properly propagate the error to the original
        caller.
        """
        self.client.factor = 0.01  # Try reconnecting very quickly
        self.client.retryOnReconnect = True
        connector = reactor.connectUNIX(self.socket, self.client)
        remote = yield self.client.getRemoteObject()

        # Disconnect
        connector.disconnect()

        # A method call error is not retried
        yield self.assertFailure(remote.secret(), MethodCallError)
        self.client.stopTrying()
        connector.disconnect()

    @inlineCallbacks
    def test_wb_retry_with_while_still_disconnected(self):
        """
        The L{RemoteObject._retry} method gets called as soon as a new
        connection is ready. If for whatever reason the connection drops
        again very quickly, the C{_retry} method will behave as expected.
        """
        self.client.factor = 0.01  # Try reconnecting very quickly
        self.client.retryOnReconnect = True
        connector = reactor.connectUNIX(self.socket, self.client)
        remote = yield self.client.getRemoteObject()

        # Disconnect
        connector.disconnect()

        def handle_reconnect(protocol):
            # In this precise moment we have a newly connected protocol
            remote._sender.protocol = protocol

            # Pretend that the connection is lost again very quickly
            protocol.transport.loseConnection()

            # Force RemoteObject._retry to run using a disconnected protocol
            reactor.callLater(0, remote._retry)

            # Restore the real handler and start listening again very soon
            self.client.dontNotifyOnConnect(handle_reconnect)
            self.client.notifyOnConnect(remote._handle_connect)

        def assert_failure(error):
            self.assertEqual(str(error), "Forbidden method 'secret'")

        # Use our own reconnect handler
        self.client.dontNotifyOnConnect(remote._handle_connect)
        self.client.notifyOnConnect(handle_reconnect)

        error = yield self.assertFailure(remote.secret(), MethodCallError)
        self.assertEqual(str(error), "Forbidden method 'secret'")

        self.client.stopTrying()
        connector.disconnect()

    @inlineCallbacks
    def test_retry_with_many_method_calls(self):
        """
        If several L{MethodCall} requests were issued while disconnected, they
        will be all eventually completed when the connection gets established
        again.
        """
        self.client.factor = 0.01  # Try reconnecting very quickly
        self.client.retryOnReconnect = True
        connector = reactor.connectUNIX(self.socket, self.client)
        remote = yield self.client.getRemoteObject()

        # Disconnect
        connector.disconnect()

        result1 = yield remote.guess("word", "cool", value=4)
        result2 = yield remote.motd()

        self.assertEqual(result1, "Guessed!")
        self.assertEqual(result2, "Words are cool")
        self.client.stopTrying()
        connector.disconnect()

    @inlineCallbacks
    def test_retry_without_retry_on_reconnect(self):
        """
        If C{retryOnReconnect} is C{False}, the L{RemoteObject} object won't
        retry to perform requests which failed because the connection was
        lost, however requests made after a reconnection will still succeed.
        """
        self.client.factor = 0.01  # Try reconnecting very quickly
        connector = reactor.connectUNIX(self.socket, self.client)
        remote = yield self.client.getRemoteObject()

        # Disconnect
        deferred = Deferred()
        self.client.notifyOnConnect(deferred.callback)
        connector.disconnect()

        yield self.assertFailure(remote.modt(), ConnectionDone)

        # Wait for reconnection and peform another call
        yield deferred
        result = yield remote.motd()
        self.assertEqual(result, "Words are cool")

        self.client.stopTrying()
        connector.disconnect()

    @inlineCallbacks
    def test_retry_with_timeout(self):
        """
        If a C{retryTimeout} is set, the L{RemoteObject} object will errback
        failed L{MethodCall}s after that amount of seconds, without retrying
        them when the connection established again.
        """
        self.client.retryOnReconnect = True
        self.client.retryTimeout = 0.1
        self.client.factor = 1  # Reconnect slower than timeout
        connector = reactor.connectUNIX(self.socket, self.client)
        remote = yield self.client.getRemoteObject()

        # Disconnect
        connector.disconnect()

        error = yield self.assertFailure(remote.modt(), MethodCallError)
        self.assertEqual("timeout", str(error))

        self.client.stopTrying()
        connector.disconnect()
