import unittest

from twisted.internet import reactor
from twisted.internet.error import ConnectError, ConnectionDone
from twisted.internet.task import Clock
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure

from landscape.lib import testing
from landscape.lib.amp import (
    MethodCallError, MethodCallServerProtocol, MethodCallClientProtocol,
    MethodCallServerFactory, MethodCallClientFactory, RemoteObject,
    MethodCallSender)


class FakeTransport(object):
    """Accumulate written data into a list."""

    def __init__(self, connection):
        self.stream = []
        self.connection = connection

    def write(self, data):
        self.stream.append(data)

    def loseConnection(self):
        raise NotImplementedError()

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
        self.client.fake_connection = self.connection

        self.connection.make()

    def disconnect(self):
        self.connection.lose(self, Failure(ConnectionDone()))


class DummyObject(object):

    method = None


class BaseTestCase(testing.TwistedTestCase, unittest.TestCase):
    pass


class MethodCallTest(BaseTestCase):

    def setUp(self):
        super(MethodCallTest, self).setUp()
        self.methods = ["method"]
        self.object = DummyObject()
        server = MethodCallServerProtocol(self.object, self.methods)
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
        self.methods.remove("method")
        deferred = self.sender.send_method_call(method="method",
                                                args=[],
                                                kwargs={})
        self.connection.flush()
        self.failureResultOf(deferred).trap(MethodCallError)

    def test_with_no_arguments(self):
        """
        A connected client can issue a L{MethodCall} without arguments and
        with an empty response.
        """
        self.object.method = lambda: None
        deferred = self.sender.send_method_call(method="method",
                                                args=[],
                                                kwargs={})
        self.connection.flush()
        self.assertIs(None, self.successResultOf(deferred))

    def test_with_return_value(self):
        """
        A connected client can issue a L{MethodCall} targeted to an
        object method with a return value.
        """
        self.object.method = lambda: "Cool result"
        deferred = self.sender.send_method_call(method="method",
                                                args=[],
                                                kwargs={})
        self.connection.flush()
        self.assertEqual("Cool result", self.successResultOf(deferred))

    def test_with_one_argument(self):
        """
        A connected AMP client can issue a L{MethodCall} with one argument and
        a response value.
        """
        self.object.method = lambda word: word.capitalize()
        deferred = self.sender.send_method_call(method="method",
                                                args=["john"],
                                                kwargs={})
        self.connection.flush()
        self.assertEqual("John", self.successResultOf(deferred))

    def test_with_boolean_return_value(self):
        """
        The return value of a L{MethodCall} argument can be a boolean.
        """
        self.object.method = lambda word: len(word) < 3
        deferred = self.sender.send_method_call(method="method",
                                                args=["hi"],
                                                kwargs={})
        self.connection.flush()
        self.assertTrue(self.successResultOf(deferred))

    def test_with_many_arguments(self):
        """
        A connected client can issue a L{MethodCall} with many arguments.
        """
        self.object.method = lambda word1, word2: word1 + word2
        deferred = self.sender.send_method_call(method="method",
                                                args=["We ", "rock"],
                                                kwargs={})
        self.connection.flush()
        self.assertEqual("We rock", self.successResultOf(deferred))

    def test_with_default_arguments(self):
        """
        A connected client can issue a L{MethodCall} for methods having
        default arguments.
        """
        self.object.method = lambda word, index=0: word[index:].lower()
        deferred = self.sender.send_method_call(method="method",
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
        self.object.method = lambda word, index=0: word[index:].lower()
        deferred = self.sender.send_method_call(method="method",
                                                args=["ABC"],
                                                kwargs={"index": 2})
        self.connection.flush()
        self.assertEqual("c", self.successResultOf(deferred))

    def test_with_dictionary_arguments(self):
        """
        Method arguments passed to a L{MethodCall} can be dictionaries.
        """
        # Sort the keys to ensure stable test outcome.
        self.object.method = lambda d: "".join(
            sorted(d.keys()) * sum(d.values()))
        deferred = self.sender.send_method_call(method="method",
                                                args=[{"foo": 1, "bar": 2}],
                                                kwargs={})
        self.connection.flush()
        self.assertEqual("barfoobarfoobarfoo", self.successResultOf(deferred))

    def test_with_bytes_dictionary_arguments(self):
        """
        Method arguments passed to a MethodCall can be a dict of bytes.
        """
        arg = {b"byte_key": 1}
        self.object.method = lambda d: ",".join([
            type(x).__name__ for x in d.keys()])
        deferred = self.sender.send_method_call(
            method="method",
            args=[arg],
            kwargs={})
        self.connection.flush()
        # str under python2, bytes under python3
        self.assertEqual(type(b"").__name__, self.successResultOf(deferred))

    def test_with_non_serializable_return_value(self):
        """
        If the target object method returns an object that can't be serialized,
        the L{MethodCall} raises an error.
        """
        class Complex(object):
            pass

        self.object.method = lambda: Complex()
        deferred = self.sender.send_method_call(method="method",
                                                args=[],
                                                kwargs={})
        self.connection.flush()
        self.failureResultOf(deferred).trap(MethodCallError)

    def test_with_long_argument(self):
        """
        The L{MethodCall} protocol supports sending method calls with arguments
        bigger than the maximum AMP parameter value size.
        """
        self.object.method = lambda word: len(word) == 65535
        deferred = self.sender.send_method_call(method="method",
                                                args=["!" * 65535],
                                                kwargs={})
        self.connection.flush()
        self.assertTrue(self.successResultOf(deferred))

    def test_with_long_argument_multiple_calls(self):
        """
        The L{MethodCall} protocol supports concurrently sending multiple
        method calls with arguments bigger than the maximum AMP value size.
        """
        self.object.method = lambda word: len(word)
        deferred1 = self.sender.send_method_call(method="method",
                                                 args=["!" * 80000],
                                                 kwargs={})
        deferred2 = self.sender.send_method_call(method="method",
                                                 args=["*" * 90000],
                                                 kwargs={})

        self.connection.flush()
        self.assertEqual(80000, self.successResultOf(deferred1))
        self.assertEqual(90000, self.successResultOf(deferred2))

    def test_with_exception(self):
        """
        If the target object method raises an exception, the remote call fails
        with a L{MethodCallError}.
        """
        self.object.method = lambda a, b: a / b
        deferred = self.sender.send_method_call(method="method",
                                                args=[1, 0],
                                                kwargs={})
        self.connection.flush()
        self.failureResultOf(deferred).trap(MethodCallError)

    def test_with_successful_deferred(self):
        """
        If the target object method returns a L{Deferred}, it is handled
        transparently.
        """
        self.object.deferred = Deferred()
        self.object.method = lambda: self.object.deferred
        result = []
        deferred = self.sender.send_method_call(method="method",
                                                args=[],
                                                kwargs={})
        deferred.addCallback(result.append)

        self.connection.flush()

        # At this point the receiver is waiting for method to complete, so
        # the deferred has not fired yet
        self.assertEqual([], result)

        # Fire the deferred and let the receiver respond
        self.object.deferred.callback("Hey!")
        self.connection.flush()

        self.assertEqual(["Hey!"], result)

    def test_with_failing_deferred(self):
        """
        If the target object method returns a failing L{Deferred}, a
        L{MethodCallError} is raised.
        """
        self.object.deferred = Deferred()
        self.object.method = lambda: self.object.deferred
        result = []
        deferred = self.sender.send_method_call(method="method",
                                                args=[],
                                                kwargs={})
        deferred.addErrback(result.append)

        self.connection.flush()

        # At this point the receiver is waiting for method to complete, so
        # the deferred has not fired yet
        self.assertEqual([], result)

        # Simulate time advancing and the receiver responding
        self.object.deferred.errback(Exception())
        self.connection.flush()

        [failure] = result
        failure.trap(MethodCallError)

    def test_with_deferred_timeout(self):
        """
        If the peer protocol doesn't send a response for a deferred within
        the given timeout, the method call fails.
        """
        self.object.method = lambda: Deferred()
        result = []
        deferred = self.sender.send_method_call(method="method",
                                                args=[],
                                                kwargs={})
        deferred.addErrback(result.append)

        self.clock.advance(60)

        [failure] = result
        failure.trap(MethodCallError)

    def test_with_late_response(self):
        """
        If the peer protocol sends a late response for a request that has
        already timeout, that response is ignored.
        """
        self.object.deferred = Deferred()
        self.object.method = lambda: self.object.deferred
        result = []
        deferred = self.sender.send_method_call(method="method",
                                                args=[],
                                                kwargs={})
        deferred.addErrback(result.append)

        self.clock.advance(60)
        self.object.deferred.callback("late")

        [failure] = result
        failure.trap(MethodCallError)


class RemoteObjectTest(BaseTestCase):

    def setUp(self):
        super(RemoteObjectTest, self).setUp()
        self.methods = ["method"]
        self.object = DummyObject()
        self.clock = Clock()
        self.factory = MethodCallClientFactory(self.clock)
        server_factory = MethodCallServerFactory(self.object, self.methods)
        self.connector = FakeConnector(self.factory, server_factory)
        self.connector.connect()
        self.remote = self.successResultOf(self.factory.getRemoteObject())

    def test_with_forbidden_method(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and withj
        an empty response.
        """
        self.methods.remove("method")
        deferred = self.remote.method()
        failure = self.failureResultOf(deferred)
        self.assertEqual("Forbidden method 'method'", str(failure.value))

    def test_with_no_arguments(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and with
        an empty response.
        """
        self.object.method = lambda: None
        deferred = self.remote.method()
        self.assertIs(None, self.successResultOf(deferred))

    def test_with_return_value(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and get
        back the value of the commands's response.
        """
        self.object.method = lambda: "Cool"
        deferred = self.remote.method()
        self.assertEqual("Cool", self.successResultOf(deferred))

    def test_with_arguments(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with one argument and get
        the response value.
        """
        self.object.method = lambda word, times=2: word * times
        deferred = self.remote.method("hi", times=3)
        self.assertEqual("hihihi", self.successResultOf(deferred))

    def test_method_call_error(self):
        """
        If a L{MethodCall} fails due to a L{MethodCallError},
        the L{RemoteObject} won't try to perform it again, even if the
        C{retryOnReconnect} error is set, as a L{MethodCallError} is a
        permanent failure that is not likely to ever succeed.
        """
        self.methods.remove("method")
        self.factory.retryOnReconnect = True
        deferred = self.remote.method()
        self.failureResultOf(deferred).trap(MethodCallError)

    def test_retry(self):
        """
        If the connection is lost and C{retryOnReconnect} is C{True} on the
        factory, the L{RemoteObject} will transparently retry to perform
        the L{MethodCall} requests that failed due to the broken connections.
        """
        self.object.method = lambda word: word.capitalize()
        self.factory.factor = 0.19
        self.factory.retryOnReconnect = True
        self.connector.disconnect()
        deferred = self.remote.method("john")

        # The deferred has not fired yet, because it's been put in the pending
        # queue, until the call gets a chance to be retried upon reconnection
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
        self.methods.remove("method")
        self.factory.factor = 0.19
        self.factory.retryOnReconnect = True
        self.connector.disconnect()
        deferred = self.remote.method()

        # The deferred has not fired yet, because it's been put in the pending
        # queue, until the call gets a chance to be retried upon reconnection
        self.assertFalse(deferred.called)

        # Time passes and the factory successfully reconnects
        self.clock.advance(1)

        failure = self.failureResultOf(deferred)
        self.assertEqual("Forbidden method 'method'", str(failure.value))


class MethodCallClientFactoryTest(BaseTestCase):

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

    def test_reconnect(self):
        """
        If the connection is lost, the L{RemoteObject} created by the creator
        will transparently handle the reconnection.
        """
        dummy_object = DummyObject()
        dummy_object.method = lambda: None
        server_factory = MethodCallServerFactory(dummy_object, ["method"])
        connector = FakeConnector(self.factory, server_factory)
        connector.connect()
        remote = self.successResultOf(self.factory.getRemoteObject())

        connector.disconnect()
        self.clock.advance(5)
        deferred = remote.method()
        self.assertIs(None, self.successResultOf(deferred))


class MethodCallFunctionalTest(BaseTestCase):

    def setUp(self):
        super(MethodCallFunctionalTest, self).setUp()
        self.methods = ["method"]
        self.object = DummyObject()
        self.object.method = lambda word: word.capitalize()
        self.socket = self.mktemp()
        self.server = MethodCallServerFactory(self.object, self.methods)
        self.client = MethodCallClientFactory(reactor)
        self.port = reactor.listenUNIX(self.socket, self.server)

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
        result = yield remote.method("john")
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
        result = yield remote.method("john")
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
        result = yield remote.method("john")
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
        self.methods.remove("method")
        self.client.factor = 0.01  # Try reconnecting very quickly
        self.client.retryOnReconnect = True
        connector = reactor.connectUNIX(self.socket, self.client)
        remote = yield self.client.getRemoteObject()

        # Disconnect
        connector.disconnect()

        # A method call error is not retried
        yield self.assertFailure(remote.method(), MethodCallError)
        self.client.stopTrying()
        connector.disconnect()

    @inlineCallbacks
    def test_wb_retry_with_while_still_disconnected(self):
        """
        The L{RemoteObject._retry} method gets called as soon as a new
        connection is ready. If for whatever reason the connection drops
        again very quickly, the C{_retry} method will behave as expected.
        """
        self.methods.remove("method")
        self.client.factor = 0.01  # Try reconnecting very quickly
        self.client.retryOnReconnect = True
        connector = reactor.connectUNIX(self.socket, self.client)
        remote = yield self.client.getRemoteObject()

        # Disconnect
        connector.disconnect()

        def handle_reconnect(protocol):
            # In this precise moment we have a newly connected protocol
            remote._sender._protocol = protocol

            # Pretend that the connection is lost again very quickly
            protocol.transport.loseConnection()

            # Force RemoteObject._retry to run using a disconnected protocol
            reactor.callLater(0, remote._retry)

            # Restore the real handler and start listening again very soon
            self.client.dontNotifyOnConnect(handle_reconnect)
            self.client.notifyOnConnect(remote._handle_connect)

        def assert_failure(error):
            self.assertEqual(str(error), "Forbidden method 'method'")

        # Use our own reconnect handler
        self.client.dontNotifyOnConnect(remote._handle_connect)
        self.client.notifyOnConnect(handle_reconnect)

        error = yield self.assertFailure(remote.method(), MethodCallError)
        self.assertEqual(str(error), "Forbidden method 'method'")

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

        result1 = yield remote.method("john")
        result2 = yield remote.method("bill")

        self.assertEqual(result1, "John")
        self.assertEqual(result2, "Bill")
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
        result = yield remote.method("john")
        self.assertEqual(result, "John")

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

        error = yield self.assertFailure(remote.method("foo"), MethodCallError)
        self.assertEqual("timeout", str(error))

        self.client.stopTrying()
        connector.disconnect()
