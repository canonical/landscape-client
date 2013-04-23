from twisted.internet import reactor
from twisted.internet.protocol import Factory
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.error import ConnectionDone, ConnectError
from twisted.internet.task import Clock
from twisted.protocols.amp import AMP
from twisted.python.failure import Failure

from landscape.lib.amp import (
    MethodCallError, MethodCallProtocol, MethodCallClientFactory, RemoteObject,
    RemoteObjectConnector, MethodCallReceiver, MethodCallSender)
from landscape.tests.helpers import LandscapeTest


class FakeTransport(object):
    """Accumulate written data into a list."""

    def __init__(self):
        self.stream = []

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
        self.server.makeConnection(FakeTransport())
        self.client.makeConnection(FakeTransport())

    def flush(self):
        """
        Notify the server of any data written by the client and viceversa.
        """
        while True:
            if self.client.transport.stream:
                self.server.dataReceived(self.client.transport.stream.pop(0))
            elif self.server.transport.stream:
                self.client.dataReceived(self.server.transport.stream.pop(0))
            else:
                break


class WordsException(Exception):
    """Test exception."""


class Words(object):
    """Test class to be used as target object of a L{MethodCallProtocol}."""

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


class WordsProtocol(MethodCallProtocol):

    methods = ["empty",
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

    timeout = 0.2


METHODS = WordsProtocol.methods


class WordsFactory(MethodCallClientFactory):

    protocol = WordsProtocol
    factor = 0.19

    retryOnReconnect = True
    retryTimeout = 0.7


class RemoteWordsConnector(RemoteObjectConnector):

    factory = WordsFactory


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
        server = AMP(locator=MethodCallReceiver(Words(), METHODS))
        client = AMP()
        self.connection = FakeConnection(client, server)
        self.clock = Clock()
        self.sender = MethodCallSender(client, self.clock)

    def test_with_forbidden_method(self):
        """
        If a method is not included in L{MethodCallProtocol.methods} it
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
        server = AMP(locator=MethodCallReceiver(Words(self.clock), METHODS))
        client = AMP()
        self.connection = FakeConnection(client, server)
        factory = WordsFactory(self.clock)
        self.remote = RemoteObject(factory)
        factory.clientConnectionMade(client)

        send_method_call = self.remote._sender.send_method_call

        def synchronous_send_method_call(method, args=[], kwargs={}):
            # Transparently flush the connection after a send_method_call
            # invocation
            deferred = send_method_call(method, args=args, kwargs=kwargs)
            self.connection.flush()
            return deferred

        self.remote._sender.send_method_call = synchronous_send_method_call

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
        self.connection.flush()

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
        self.connection.flush()

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


class MethodCallClientFactoryTest(LandscapeTest):

    def setUp(self):
        super(MethodCallClientFactoryTest, self).setUp()
        self.clock = Clock()
        self.factory = MethodCallClientFactory(reactor=self.clock)

    def test_max_delay(self):
        """
        The L{MethodCallClientFactory} class has a default value of 30 seconds
        for the maximum reconnection delay.
        """
        self.assertEqual(self.factory.maxDelay, 30)

    def test_connect_notifier(self):
        """
        The C{notifyOnConnect} method supports specifying a callback that
        will be invoked when a connection has been established.
        """
        protocols = []
        self.factory.notifyOnConnect(protocols.append)
        protocol = self.factory.buildProtocol(None)
        protocol.connectionMade()
        self.assertEqual([protocol], protocols)

    def test_connect_notifier_with_reconnect(self):
        """
        The C{notifyOnConnect} method will also callback when a connection is
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


class RemoteObjectConnectorTest(LandscapeTest):

    def setUp(self):
        super(RemoteObjectConnectorTest, self).setUp()
        self.socket = self.mktemp()
        self.server_factory = Factory()
        self.server_factory.protocol = lambda: (
            AMP(locator=MethodCallReceiver(Words(reactor), METHODS)))
        self.port = reactor.listenUNIX(self.socket, self.server_factory)
        self.connector = RemoteWordsConnector(reactor, self.socket)

        def set_remote(words):
            self.words = words

        connected = self.connector.connect()
        return connected.addCallback(set_remote)

    def tearDown(self):
        self.connector.disconnect()
        self.port.stopListening()
        super(RemoteObjectConnectorTest, self).tearDown()

    def test_connect(self):
        """
        The L{RemoteObject} resulting form the deferred returned by
        L{RemoteObjectConnector.connect} is properly connected to the
        remote peer.
        """
        return self.assertSuccess(self.words.empty())

    def test_connect_with_max_retries(self):
        """
        If C{max_retries} is passed to L{RemoteObjectConnector.connet},
        then it will give up trying to connect after that amout of times.
        """
        self.connector.disconnect()
        self.port.stopListening()

        def reconnect(ignored):
            self.port = reactor.listenUNIX(self.socket, self.server_factory)
            return self.connector.connect()

        result = self.connector.connect(max_retries=0)
        self.assertFailure(result, ConnectError)
        return result.addCallback(reconnect)

    def test_connect_with_factor(self):
        """
        If C{factor} is passed to L{RemoteObjectConnector.connect} method,
        then the associated protocol factory will be set to that value.
        """
        self.connector.disconnect()

        def assert_factor(ignored):
            self.assertEqual(self.connector._factory.factor, 1.0)

        result = self.connector.connect(factor=1.0)
        return result.addCallback(assert_factor)

    def test_disconnect(self):
        """
        It is possible to call L{RemoteObjectConnector.disconnect} multiple
        times, even if the connection has been already closed.
        """
        self.connector.disconnect()
        self.connector.disconnect()

    def test_disconnect_without_connect(self):
        """
        It is possible to call L{RemoteObjectConnector.disconnect} even
        if the connection was never established. In that case the method
        is effectively a no-op.
        """
        connector = RemoteWordsConnector(None, None)
        connector.disconnect()

    def test_reconnect(self):
        """
        If the connection is lost, the L{RemoteObject} created by the creator
        will transparently handle the reconnection.
        """
        self.words._sender.protocol.transport.loseConnection()
        self.port.stopListening()

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)
            reactor.callLater(0.3, assert_remote)

        def assert_remote():
            result = self.words.empty()
            result.addCallback(lambda x: reconnected.callback(None))
            return result

        reactor.callLater(0.01, restart_listening)
        reconnected = Deferred()
        return reconnected

    def test_method_call_error(self):
        """
        If a L{MethodCall} fails due to a L{MethodCallError}, the
        L{RemoteObject} won't try to perform it again.
        """
        return self.assertFailure(self.words.secret(), MethodCallError)

    def test_retry(self):
        """
        If the connection is lost, the L{RemoteObject} created by the creator
        will transparently retry to perform the L{MethodCall} requests that
        failed due to the broken connection.
        """
        self.words._sender.protocol.transport.loseConnection()
        self.port.stopListening()

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)

        reactor.callLater(0.1, restart_listening)
        return self.words.empty()

    def test_retry_with_method_call_error(self):
        """
        If a retried L{MethodCall} request fails due to a L{MethodCallError},
        the L{RemoteObject} will properly propagate the error to the original
        caller.
        """
        self.words._sender.protocol.transport.loseConnection()
        self.port.stopListening()

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)

        def assert_failure(error):
            self.assertEqual(str(error), "Forbidden method 'secret'")

        reactor.callLater(0.5, restart_listening)
        result = self.words.secret()
        self.assertFailure(result, MethodCallError)
        return result.addCallback(assert_failure)

    def test_wb_retry_with_while_still_disconnected(self):
        """
        The L{RemoteObject._retry} method gets called as soon as a new
        connection is ready. If for whatever reason the connection drops
        again very quickly, the C{_retry} method will behave as expected.
        """
        self.words._sender.protocol.transport.loseConnection()
        self.port.stopListening()
        real_handle_connect = self.words._handle_connect

        def handle_connect(protocol):
            # In this precise moment we have a newly connected protocol
            self.words._sender.protocol = protocol

            # Pretend that the connection is lost again very quickly
            protocol.transport.loseConnection()
            self.port.stopListening()

            # Force RemoteObject._retry to run using a disconnected protocol
            reactor.callLater(0, self.words._retry)

            # Restore the real handler and start listening again very soon
            self.connector._factory.dontNotifyOnConnect(handle_connect)
            self.connector._factory.notifyOnConnect(real_handle_connect)
            reactor.callLater(0.2, restart_listening)

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)

        def assert_failure(error):
            self.assertEqual(str(error), "Forbidden method 'secret'")

        # Use our own reconnect handler
        self.connector._factory.dontNotifyOnConnect(real_handle_connect)
        self.connector._factory.notifyOnConnect(handle_connect)

        reactor.callLater(0.2, restart_listening)
        result = self.words.secret()
        self.assertFailure(result, MethodCallError)
        return result.addCallback(assert_failure)

    def test_retry_with_many_method_calls(self):
        """
        If several L{MethodCall} requests were issued while disconnected, they
        will be all eventually completed when the connection gets established
        again.
        """
        self.words._sender.protocol.transport.loseConnection()
        self.port.stopListening()

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)

        def assert_guess(response):
            self.assertEqual(response, "Guessed!")

        def assert_secret(failure):
            self.assertEqual(str(failure.value), "Forbidden method 'secret'")

        def assert_motd(response):
            self.assertEqual(response, "Words are cool")

        reactor.callLater(0.1, restart_listening)

        results = [self.words.guess("word", "cool", value=4),
                   self.words.secret(),
                   self.words.motd()]
        results[0].addCallback(assert_guess)
        results[1].addErrback(assert_secret)
        results[2].addCallback(assert_motd)
        return DeferredList(results)

    def test_retry_without_retry_on_reconnect(self):
        """
        If C{retry_on_reconnect} is C{False}, the L{RemoteObject} object won't
        retry to perform requests which failed because the connection was
        lost, however requests made after a reconnection will still succeed.
        """
        self.words._sender.protocol.transport.loseConnection()
        self.port.stopListening()

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)
            reactor.callLater(0.3, assert_reconnected)

        def assert_reconnected():
            result = self.words.empty()
            result.addCallback(lambda x: reconnected.callback(None))
            return result

        reactor.callLater(0.1, restart_listening)
        self.words._factory.retryOnReconnect = False
        result = self.words.empty()
        self.assertFailure(result, ConnectionDone)
        reconnected = Deferred()
        return result.addCallback(lambda x: reconnected)

    def test_retry_with_timeout(self):
        """
        If a C{timeout} is set, the L{RemoteObject} object will errback failed
        L{MethodCall}s after that amount of seconds, without retrying them when
        the connection established again.
        """
        self.words._sender.protocol.transport.loseConnection()
        self.port.stopListening()

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)
            reactor.callLater(0.1, reconnected.callback, None)

        def assert_failure(error):
            self.assertEqual(str(error), "timeout")
            return reconnected

        reactor.callLater(0.9, restart_listening)
        result = self.words.empty()
        self.assertFailure(result, MethodCallError)
        reconnected = Deferred()
        return result.addCallback(assert_failure)
