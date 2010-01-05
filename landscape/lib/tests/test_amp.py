from twisted.trial.unittest import TestCase
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.protocol import ServerFactory, ClientCreator

from landscape.lib.amp import (
    MethodCallError, MethodCall, get_nested_attr, Method, MethodCallProtocol,
    MethodCallFactory)
from landscape.tests.helpers import LandscapeTest


class Words(object):

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

    def translate(self, word, language):
        if word == "hi" and language == "italian":
            return "ciao"
        else:
            raise RuntimeError("'%s' doesn't exit in %s" % (word, language))

    def meaning_of_life(self):

        class Complex(object):
            pass
        return Complex()

    def _check(self, word, seed, value=3):
        if seed == "cool" and value == 4:
            return "Guessed!"

    def guess(self, word, *args, **kwargs):
        return self._check(word, *args, **kwargs)


class WordsProtocol(MethodCallProtocol):

    methods = [Method("empty"),
               Method("motd"),
               Method("capitalize"),
               Method("is_short"),
               Method("concatenate"),
               Method("lower_case"),
               Method("multiply_alphabetically"),
               Method("translate", language="factory.language"),
               Method("meaning_of_life"),
               Method("guess")]


class MethodCallProtocolTest(LandscapeTest):

    def setUp(self):
        super(MethodCallProtocolTest, self).setUp()
        socket = self.mktemp()
        factory = MethodCallFactory(Words())
        factory.protocol = WordsProtocol
        factory.language = "italian"
        self.port = reactor.listenUNIX(socket, factory)

        def set_protocol(protocol):
            self.protocol = protocol

        connector = ClientCreator(reactor, MethodCallProtocol)
        connected = connector.connectUNIX(socket)
        return connected.addCallback(set_protocol)

    def tearDown(self):
        self.protocol.transport.loseConnection()
        self.port.loseConnection()
        super(MethodCallProtocolTest, self).tearDown()

    def test_secret(self):
        """
        If a method is not included in L{MethodCallProtocol.methods} it
        can't be called.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="secret")
        return self.assertFailure(result, MethodCallError)

    def test_empty(self):
        """
        A connected client can issue a L{MethodCall} without arguments and
        with an empty response.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="empty")
        return self.assertSuccess(result, {"result": None})

    def test_motd(self):
        """
        A connected client can issue a L{MethodCall} targeted to an
        object method with a return value.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="motd")
        return self.assertSuccess(result, {"result": "Words are cool"})

    def test_capitalize(self):
        """
        A connected AMP client can issue a L{MethodCall} with one argument and
        a response value.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="capitalize",
                                          args=["john"])
        return self.assertSuccess(result, {"result": "John"})

    def test_is_short(self):
        """
        The return value of a L{MethodCall} argument can be a boolean.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="is_short",
                                          args=["hi"])
        return self.assertSuccess(result, {"result": True})

    def test_concatenate(self):
        """
        A connected client can issue a L{MethodCall} with many arguments.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="concatenate",
                                          args=["You ", "rock"])
        return self.assertSuccess(result, {"result": "You rock"})

    def test_lower_case(self):
        """
        A connected client can issue a L{MethodCall} for methods having
        default arguments.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="lower_case",
                                          args=["OHH"])
        return self.assertSuccess(result, {"result": "ohh"})

    def test_lower_case_with_index(self):
        """
        A connected client can issue a L{MethodCall} with keyword arguments
        having default values in the target object.  If a value is specified by
        the caller it will be used in place of the default value
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="lower_case",
                                          args=["OHH"],
                                          kwargs={"index": 2})
        return self.assertSuccess(result, {"result": "OHh"})

    def test_multiply_alphabetically(self):
        """
        Method arguments passed to a L{MethodCall} can be dictionaries.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="multiply_alphabetically",
                                          args=[{"foo": 2, "bar": 3}],
                                          kwargs={})
        return self.assertSuccess(result, {"result": "barbarbarfoofoo"})

    def test_translate(self):
        """
        A L{Method} can specify additional protocol-specific arguments
        that will be added to the ones provided by the L{MethodCall}.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="translate",
                                          args=["hi"])
        return self.assertSuccess(result, {"result": "ciao"})

    def test_meaning_of_life(self):
        """
        If the target object method returns an object that can't be serialized,
        the L{MethodCall} result is C{None}.
        """
        result = self.protocol.callRemote(MethodCall,
                                          name="meaning_of_life")
        return self.assertFailure(result, MethodCallError)


class RemoteObjectTest(LandscapeTest):

    def setUp(self):
        super(RemoteObjectTest, self).setUp()
        socket = self.mktemp()
        factory = MethodCallFactory(Words())
        factory.protocol = WordsProtocol
        factory.language = "italian"
        self.port = reactor.listenUNIX(socket, factory)

        def set_protocol(protocol):
            self.protocol = protocol
            self.words = protocol.remote

        connector = ClientCreator(reactor, MethodCallProtocol)
        connected = connector.connectUNIX(socket)
        return connected.addCallback(set_protocol)

    def tearDown(self):
        self.protocol.transport.loseConnection()
        self.port.loseConnection()
        super(RemoteObjectTest, self).tearDown()

    def test_empty(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and withj
        an empty response.
        """
        return self.assertSuccess(self.words.empty())

    def test_motd(self):
        """
        A L{RemoteObject} can send L{MethodCall}s without arguments and get
        back the value of the commands's response.
        """
        result = self.words.motd()
        return self.assertSuccess(result, "Words are cool")

    def test_capitalize(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with one argument and get
        the response value.
        """
        result = self.words.capitalize("john")
        return self.assertSuccess(result, "John")

    def test_capitalize_with_kwarg(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with a named argument.
        """
        result = self.words.capitalize(word="john")
        return self.assertSuccess(result, "John")

    def test_is_short(self):
        """
        The return value of a L{MethodCall} argument can be a boolean.
        """
        return self.assertSuccess(self.words.is_short("hi"), True)

    def test_concatenate(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with more than one argument.
        """
        result = self.words.concatenate("You ", "rock")
        return self.assertSuccess(result, "You rock")

    def test_concatenate_with_kwargs(self):
        """
        A L{RemoteObject} can send L{MethodCall}s with several
        named arguments.
        """
        result = self.words.concatenate(word2="rock", word1="You ")
        return self.assertSuccess(result, "You rock")

    def test_lower_case(self):
        """
        A L{RemoteObject} can send a L{MethodCall} having an argument with
        a default value.
        """
        result = self.words.lower_case("OHH")
        return self.assertSuccess(result, "ohh")

    def test_lower_case_with_index(self):
        """
        A L{RemoteObject} can send L{MethodCall}s overriding the default
        value of an argument.
        """
        result = self.words.lower_case("OHH", 2)
        return self.assertSuccess(result, "OHh")

    def test_multiply_alphabetically(self):
        """
        A L{RemoteObject} can send a L{MethodCall}s for methods requiring
        a dictionary arguments.
        """
        result = self.words.multiply_alphabetically({"foo": 2, "bar": 3})
        return self.assertSuccess(result, "barbarbarfoofoo")

    def test_translate(self):
        """
        A L{RemoteObject} can send a L{MethodCall} requiring protocol
        arguments, which won't be exposed to the caller.
        """
        result = self.assertSuccess(self.words.translate("hi"), "ciao")
        return self.assertSuccess(result, "ciao")

    def test_guess(self):
        """
        A L{RemoteObject} behaves well with L{MethodCall}s for methods
        having generic C{*args} and C{**kwargs} arguments.
        """
        result = self.words.guess("word", "cool", value=4)
        return self.assertSuccess(result, "Guessed!")


class GetNestedAttrTest(TestCase):

    def test_get_nested_attr(self):
        """
        The L{get_nested_attr} function returns nested attributes.
        """

        class Object(object):
            pass
        obj = Object()
        obj.foo = Object()
        obj.foo.bar = 1
        self.assertEquals(get_nested_attr(obj, "foo.bar"), 1)

    def test_get_nested_attr_with_empty_path(self):
        """
        The L{get_nested_attr} function returns the object itself if its
        passed an empty string.
        ."""
        obj = object()
        self.assertIdentical(get_nested_attr(obj, ""), obj)
