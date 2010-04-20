from twisted.internet import reactor
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.protocol import ClientCreator
from twisted.internet.error import ConnectionDone, ConnectError
from twisted.internet.task import Clock

from landscape.lib.twisted_util import gather_results
from landscape.lib.amp import (
    MethodCallError, MethodCallProtocol, MethodCallFactory, RemoteObject,
    RemoteObjectConnector)
from landscape.tests.helpers import LandscapeTest
from landscape.tests.mocker import KWARGS


class WordsException(Exception):
    """Test exception."""


class Words(object):
    """Test class to be used as target object of a L{MethodCallProtocol}."""

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
            reactor.callLater(0.01, lambda: deferred.callback("Cool!"))
        elif word == "Easy query":
            deferred.callback("Done!")
        elif word == "Weird stuff":
            reactor.callLater(0.01, lambda: deferred.errback(Exception("bad")))
        elif word == "Censored":
            deferred.errback(Exception("very bad"))
        elif word == "Long query":
            # Do nothing, the deferred won't be fired at all
            pass
        elif word == "Slowish query":
            # Fire the result after a while.
            reactor.callLater(0.05, lambda: deferred.callback("Done!"))
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

    timeout = 0.1


class WordsFactory(MethodCallFactory):

    protocol = WordsProtocol
    factor = 0.19


class RemoteWordsConnector(RemoteObjectConnector):

    factory = WordsFactory


class MethodCallProtocolTest(LandscapeTest):

    def setUp(self):
        super(MethodCallProtocolTest, self).setUp()
        socket = self.mktemp()
        factory = WordsFactory(object=Words())
        self.port = reactor.listenUNIX(socket, factory)

        def set_protocol(protocol):
            self.protocol = protocol

        connector = ClientCreator(reactor, WordsProtocol)
        connected = connector.connectUNIX(socket)
        return connected.addCallback(set_protocol)

    def tearDown(self):
        self.protocol.transport.loseConnection()
        self.port.stopListening()
        super(MethodCallProtocolTest, self).tearDown()

    def test_with_forbidden_method(self):
        """
        If a method is not included in L{MethodCallProtocol.methods} it
        can't be called.
        """
        result = self.protocol.send_method_call(method="secret",
                                                args=[],
                                                kwargs={})
        return self.assertFailure(result, MethodCallError)

    def test_with_no_arguments(self):
        """
        A connected client can issue a L{MethodCall} without arguments and
        with an empty response.
        """
        result = self.protocol.send_method_call(method="empty",
                                                args=[],
                                                kwargs={})
        return self.assertSuccess(result, {"result": None,
                                           "deferred": None})

    def test_with_return_value(self):
        """
        A connected client can issue a L{MethodCall} targeted to an
        object method with a return value.
        """
        result = self.protocol.send_method_call(method="motd",
                                                args=[],
                                                kwargs={})
        return self.assertSuccess(result, {"result": "Words are cool",
                                           "deferred": None})

    def test_with_one_argument(self):
        """
        A connected AMP client can issue a L{MethodCall} with one argument and
        a response value.
        """
        result = self.protocol.send_method_call(method="capitalize",
                                                args=["john"],
                                                kwargs={})
        return self.assertSuccess(result, {"result": "John",
                                           "deferred": None})

    def test_with_boolean_return_value(self):
        """
        The return value of a L{MethodCall} argument can be a boolean.
        """
        result = self.protocol.send_method_call(method="is_short",
                                                args=["hi"],
                                                kwargs={})
        return self.assertSuccess(result, {"result": True,
                                           "deferred": None})

    def test_with_many_arguments(self):
        """
        A connected client can issue a L{MethodCall} with many arguments.
        """
        result = self.protocol.send_method_call(method="concatenate",
                                                args=["You ", "rock"],
                                                kwargs={})
        return self.assertSuccess(result, {"result": "You rock",
                                           "deferred": None})

    def test_with_default_arguments(self):
        """
        A connected client can issue a L{MethodCall} for methods having
        default arguments.
        """
        result = self.protocol.send_method_call(method="lower_case",
                                                args=["OHH"],
                                                kwargs={})
        return self.assertSuccess(result, {"result": "ohh",
                                           "deferred": None})

    def test_with_overriden_default_arguments(self):
        """
        A connected client can issue a L{MethodCall} with keyword arguments
        having default values in the target object.  If a value is specified by
        the caller it will be used in place of the default value
        """
        result = self.protocol.send_method_call(method="lower_case",
                                                args=["OHH"],
                                                kwargs={"index": 2})
        return self.assertSuccess(result, {"result": "OHh",
                                           "deferred": None})

    def test_with_dictionary_arguments(self):
        """
        Method arguments passed to a L{MethodCall} can be dictionaries.
        """
        result = self.protocol.send_method_call(method="multiply_"
                                                       "alphabetically",
                                                args=[{"foo": 2, "bar": 3}],
                                                kwargs={})
        return self.assertSuccess(result, {"result": "barbarbarfoofoo",
                                           "deferred": None})

    def test_with_non_serializable_return_value(self):
        """
        If the target object method returns an object that can't be serialized,
        the L{MethodCall} result is C{None}.
        """
        result = self.protocol.send_method_call(method="meaning_of_life",
                                                args=[],
                                                kwargs={})
        return self.assertFailure(result, MethodCallError)

    def test_with_long_argument(self):
        """
        The L{MethodCall} protocol supports sending method calls with arguments
        bigger than the maximum AMP parameter value size.
        """
        result = self.protocol.send_method_call(method="is_short",
                                                args=["!" * 65535],
                                                kwargs={})
        return self.assertSuccess(result, {"result": False,
                                           "deferred": None})

    def test_with_long_argument_multiple_calls(self):
        """
        The L{MethodCall} protocol supports sending method calls with arguments
        bigger than the
        """
        result1 = self.protocol.send_method_call(method="is_short",
                                                 args=["!" * 80000],
                                                 kwargs={})
        result2 = self.protocol.send_method_call(method="is_short",
                                                 args=["*" * 90000],
                                                 kwargs={})

        return gather_results(
            [self.assertSuccess(result1, {"result": False, "deferred": None}),
             self.assertSuccess(result2, {"result": False, "deferred": None})])

    def test_translate(self):
        """
        If the target object method raises an exception, the remote call fails
        with a L{MethodCallError}.
        """
        result = self.protocol.send_method_call(method="translate",
                                                args=["hi"],
                                                kwargs={})
        return self.assertFailure(result, MethodCallError)


class RemoteObjectTest(LandscapeTest):

    def setUp(self):
        super(RemoteObjectTest, self).setUp()
        socket = self.mktemp()
        server_factory = WordsFactory(object=Words())
        self.port = reactor.listenUNIX(socket, server_factory)

        def set_remote(protocol):
            self.protocol = protocol
            self.words = RemoteObject(protocol)
            client_factory.stopTrying()

        connected = Deferred()
        connected.addCallback(set_remote)
        client_factory = WordsFactory(reactor=reactor)
        client_factory.add_notifier(connected.callback)
        reactor.connectUNIX(socket, client_factory)
        return connected

    def tearDown(self):
        self.protocol.transport.loseConnection()
        self.port.stopListening()
        super(RemoteObjectTest, self).tearDown()

    def test_method_call_sender_with_forbidden_method(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and withj
        an empty response.
        """
        result = self.words.secret()
        return self.assertFailure(result, MethodCallError)

    def test_with_no_arguments(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and withj
        an empty response.
        """
        return self.assertSuccess(self.words.empty())

    def test_with_return_value(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and get
        back the value of the commands's response.
        """
        result = self.words.motd()
        return self.assertSuccess(result, "Words are cool")

    def test_with_one_argument(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with one argument and get
        the response value.
        """
        result = self.words.capitalize("john")
        return self.assertSuccess(result, "John")

    def test_with_one_keyword_argument(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with a named argument.
        """
        result = self.words.capitalize(word="john")
        return self.assertSuccess(result, "John")

    def test_with_boolean_return_value(self):
        """
        The return value of a L{MethodCall} argument can be a boolean.
        """
        return self.assertSuccess(self.words.is_short("hi"), True)

    def test_with_many_arguments(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with more than one argument.
        """
        result = self.words.concatenate("You ", "rock")
        return self.assertSuccess(result, "You rock")

    def test_with_many_keyword_arguments(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with several
        named arguments.
        """
        result = self.words.concatenate(word2="rock", word1="You ")
        return self.assertSuccess(result, "You rock")

    def test_with_default_arguments(self):
        """
        A L{RemoteObject} can send a L{MethodCall} having an argument with
        a default value.
        """
        result = self.words.lower_case("OHH")
        return self.assertSuccess(result, "ohh")

    def test_with_overriden_default_arguments(self):
        """
        A L{RemoteObject} can send L{MethodCall}s overriding the default
        value of an argument.
        """
        result = self.words.lower_case("OHH", 2)
        return self.assertSuccess(result, "OHh")

    def test_with_dictionary_arguments(self):
        """
        A L{RemoteObject} can send a L{MethodCall}s for methods requiring
        a dictionary arguments.
        """
        result = self.words.multiply_alphabetically({"foo": 2, "bar": 3})
        return self.assertSuccess(result, "barbarbarfoofoo")

    def test_with_generic_args_and_kwargs(self):
        """
        A L{RemoteObject} behaves well with L{MethodCall}s for methods
        having generic C{*args} and C{**kwargs} arguments.
        """
        result = self.words.guess("word", "cool", value=4)
        return self.assertSuccess(result, "Guessed!")

    def test_with_success_full_deferred(self):
        """
        If the target object method returns a L{Deferred}, it is handled
        transparently.
        """
        result = self.words.google("Landscape")
        return self.assertSuccess(result, "Cool!")

    def test_with_failing_deferred(self):
        """
        If the target object method returns a failing L{Deferred}, a
        L{MethodCallError} is raised.
        """
        result = self.words.google("Weird stuff")
        return self.assertFailure(result, MethodCallError)

    def test_with_already_callback_deferred(self):
        """
        The target object method can return an already fired L{Deferred}.
        """
        result = self.words.google("Easy query")
        return self.assertSuccess(result, "Done!")

    def test_with_already_errback_deferred(self):
        """
        If the target object method can return an already failed L{Deferred}.
        """
        result = self.words.google("Censored")
        return self.assertFailure(result, MethodCallError)

    def test_with_deferred_timeout(self):
        """
        If the peer protocol doesn't send a response for a deferred within
        the given timeout, the method call fails.
        """
        result = self.words.google("Long query")
        return self.assertFailure(result, MethodCallError)

    def test_with_late_response(self):
        """
        If the peer protocol sends a late response for a request that has
        already timeout, that response is ignored.
        """
        self.protocol.timeout = 0.01
        result = self.words.google("Slowish query")
        self.assertFailure(result, MethodCallError)

        def assert_late_response_is_handled(ignored):
            deferred = Deferred()
            # We wait a bit to be sure that the late response gets delivered
            reactor.callLater(0.1, lambda: deferred.callback(None))
            return deferred

        return result.addCallback(assert_late_response_is_handled)


class MethodCallFactoryTest(LandscapeTest):

    def setUp(self):
        super(MethodCallFactoryTest, self).setUp()
        self.clock = Clock()
        self.factory = WordsFactory(reactor=self.clock)

    def test_add_notifier(self):
        """
        The L{MethodCallClientFactory.add_notifier} method can be used to
        add a callback function to be called when a connection is made and
        a new protocol instance built.
        """
        protocol = self.factory.protocol()
        self.factory.protocol = lambda: protocol
        callback = self.mocker.mock()
        callback(protocol)
        self.mocker.replay()
        self.factory.add_notifier(callback)
        self.factory.buildProtocol(None)
        self.clock.advance(0)

    def test_remove_notifier(self):
        """
        The L{MethodCallClientFactory.remove_notifier} method can be used to
        remove a previously added notifier callback.
        """
        callback = lambda protocol: 1 / 0
        self.factory.add_notifier(callback)
        self.factory.remove_notifier(callback)
        self.factory.buildProtocol(None)
        self.clock.advance(0)

    def test_client_connection_failed(self):
        """
        The L{MethodCallClientFactory} keeps trying to connect if maxRetries
        is not reached.
        """
        # This is sub-optimal but the ReconnectingFactory in Hardy's Twisted
        # doesn't support task.Clock
        self.factory.retry = self.mocker.mock()
        self.factory.retry(KWARGS)
        self.mocker.replay()
        self.assertEquals(self.factory.retries, 0)
        self.factory.clientConnectionFailed(None, None)

    def test_client_connection_failed_with_max_retries_reached(self):
        """
        The L{MethodCallClientFactory} stops trying to connect if maxRetries
        is reached.
        """
        callback = lambda protocol: 1 / 0
        errback = self.mocker.mock()
        errback("failure")
        self.mocker.replay()

        self.factory.add_notifier(callback, errback)
        self.factory.maxRetries = 1
        self.factory.retries = self.factory.maxRetries
        self.factory.clientConnectionFailed(object(), "failure")
        self.clock.advance(0)


class RemoteObjectConnectorTest(LandscapeTest):

    def setUp(self):
        super(RemoteObjectConnectorTest, self).setUp()
        self.socket = self.mktemp()
        self.server_factory = WordsFactory(object=Words())
        self.port = reactor.listenUNIX(self.socket, self.server_factory)
        self.connector = RemoteWordsConnector(reactor, self.socket,
                                              retry_on_reconnect=True,
                                              timeout=0.7)

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
            self.assertEquals(self.connector._factory.factor, 1.0)

        result = self.connector.connect(factor=1.0)
        return result.addCallback(assert_factor)

    def test_disconnect(self):
        """
        It is possible to call L{RemoteObjectConnector.disconnect} multiple
        times, even if the connection has been already closed.
        """
        self.connector.disconnect()
        self.connector.disconnect()
        self.assertIs(self.connector._remote, None)

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
        self.words._protocol.transport.loseConnection()
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
        self.words._protocol.transport.loseConnection()
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
        self.words._protocol.transport.loseConnection()
        self.port.stopListening()

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)

        def assert_failure(error):
            self.assertEquals(str(error), "Forbidden method 'secret'")

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
        self.words._protocol.transport.loseConnection()
        self.port.stopListening()

        def handle_reconnect(protocol):
            # In this precise moment we have a newly connected protocol
            self.words._protocol = protocol

            # Pretend that the connection is lost again very quickly
            protocol.transport.loseConnection()
            self.port.stopListening()

            # Force RemoteObject._retry to run using a disconnected protocol
            reactor.callLater(0, self.words._retry)

            # Restore the real handler and start listening again very soon
            self.connector._factory.remove_notifier(handle_reconnect)
            self.connector._factory.add_notifier(self.words._handle_reconnect)
            reactor.callLater(0.2, restart_listening)

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)

        def assert_failure(error):
            self.assertEquals(str(error), "Forbidden method 'secret'")

        # Use our own reconnect handler
        self.connector._factory.remove_notifier(self.words._handle_reconnect)
        self.connector._factory.add_notifier(handle_reconnect)

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
        self.words._protocol.transport.loseConnection()
        self.port.stopListening()

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)

        def assert_guess(response):
            self.assertEquals(response, "Guessed!")

        def assert_secret(failure):
            self.assertEquals(str(failure.value), "Forbidden method 'secret'")

        def assert_motd(response):
            self.assertEquals(response, "Words are cool")

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
        self.words._protocol.transport.loseConnection()
        self.port.stopListening()

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)
            reactor.callLater(0.3, assert_reconnected)

        def assert_reconnected():
            result = self.words.empty()
            result.addCallback(lambda x: reconnected.callback(None))
            return result

        reactor.callLater(0.1, restart_listening)
        self.words._retry_on_reconnect = False
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
        self.words._protocol.transport.loseConnection()
        self.port.stopListening()

        def restart_listening():
            self.port = reactor.listenUNIX(self.socket, self.server_factory)
            reactor.callLater(0.1, reconnected.callback, None)

        def assert_failure(error):
            self.assertEquals(str(error), "timeout")
            return reconnected

        reactor.callLater(0.9, restart_listening)
        result = self.words.empty()
        self.assertFailure(result, MethodCallError)
        reconnected = Deferred()
        return result.addCallback(assert_failure)
