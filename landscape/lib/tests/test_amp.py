from twisted.trial.unittest import TestCase
from twisted.internet import reactor
from twisted.internet.protocol import Factory, ClientCreator
from twisted.protocols.amp import AMP

from landscape.lib.amp import MethodCall, get_nested_attr


class Words(object):

    def empty(self):
        pass

    def motd(self):
        return "Words are cool"

    def capitalize(self, word):
        return word.capitalize()

    def synonym(self, word):
        if word == "hi":
            return "hello"
        else:
            return None

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

    def _check(self, word, seed, value=3):
        if seed == "cool" and value == 4:
            return "Guessed!"

    def guess(self, word, *args, **kwargs):
        return self._check(word, *args, **kwargs)


class WordsServerProtocol(AMP):

    @MethodCall.responder
    def _words(self):
        return self.factory.words


class RemoteWords(object):

    def __init__(self, protocol):
        self._protocol = protocol

    @MethodCall.sender
    def empty(self):
        pass

    @MethodCall.sender
    def motd(self):
        pass

    @MethodCall.sender
    def capitalize(self, word):
        pass

    @MethodCall.sender
    def synonym(self, word):
        pass

    @MethodCall.sender
    def is_short(self, word):
        pass

    @MethodCall.sender
    def concatenate(self, word1, word2):
        pass

    @MethodCall.sender
    def lower_case(self, word, index=None):
        pass

    @MethodCall.sender
    def multiply_alphabetically(self, word_times):
        pass

    @MethodCall.sender
    def translate(self, word, _language="factory.language"):
        pass

    @MethodCall.sender
    def guess(self, word, *args, **kwargs):
        pass


class GetNestedAttrTest(TestCase):

    def test_nested_attr(self):
        """
        The L{get_nested_attr} function returns nested attributes.
        """

        class Object(object):
            pass
        obj = Object()
        obj.foo = Object()
        obj.foo.bar = 1
        self.assertEquals(get_nested_attr(obj, "foo.bar"), 1)

    def test_nested_attr_with_empty_path(self):
        """
        The L{get_nested_attr} function returns the object itself if its
        passed an empty string.
        ."""
        obj = object()
        self.assertIdentical(get_nested_attr(obj, ""), obj)


class MethodCallResponderTest(TestCase):

    def setUp(self):
        super(MethodCallResponderTest, self).setUp()
        socket = self.mktemp()
        factory = Factory()
        factory.protocol = WordsServerProtocol
        factory.words = Words()
        factory.language = "italian"
        self.port = reactor.listenUNIX(socket, factory)

        def set_protocol(protocol):
            self.protocol = protocol

        connector = ClientCreator(reactor, AMP)
        connected = connector.connectUNIX(socket)
        return connected.addCallback(set_protocol)

    def tearDown(self):
        super(MethodCallResponderTest, self).setUp()
        self.port.loseConnection()
        self.protocol.transport.loseConnection()

    def test_empty(self):
        """
        A connected AMP client can issue a L{MethodCall} without arguments and
        with an empty response.
        """
        performed = self.protocol.callRemote(MethodCall, name="empty",
                                             args=[], kwargs={})
        return performed.addCallback(self.assertEquals, {"result": None})

    def test_motd(self):
        """
        A connected AMP client can issue a L{MethodCall} targeted to an
        object method with a return value.
        """
        performed = self.protocol.callRemote(MethodCall, name="motd",
                                             args=[], kwargs={})
        return performed.addCallback(self.assertEquals,
                                     {"result": "Words are cool"})

    def test_capitalize(self):
        """
        A connected AMP client can issue a L{MethodCall} with one argument and
        a response value.
        """
        performed = self.protocol.callRemote(MethodCall, name="capitalize",
                                             args=["john"], kwargs={})
        return performed.addCallback(self.assertEquals, {"result": "John"})

    def test_synonim(self):
        """
        The response of a L{MethodCall} command can be C{None}.
        """
        performed = self.protocol.callRemote(MethodCall, name="synonym",
                                             args=["foo"], kwargs={})
        return performed.addCallback(self.assertEquals, {"result": None})

    def test_is_short(self):
        """
        The return value of a L{MethodCall} argument can be a boolean.
        """
        performed = self.protocol.callRemote(MethodCall, name="is_short",
                                             args=["hi"], kwargs={})
        return performed.addCallback(self.assertEquals, {"result": True})

    def test_concatenate(self):
        """
        A connected AMP client can issue a L{MethodCall} with many arguments.
        """
        performed = self.protocol.callRemote(MethodCall, name="concatenate",
                                             args=["You ", "rock"], kwargs={})
        return performed.addCallback(self.assertEquals, {"result": "You rock"})

    def test_lower_case(self):
        """
        A connected AMP client can issue a L{MethodCall} for methods having
        default arguments.
        """
        performed = self.protocol.callRemote(MethodCall, name="lower_case",
                                             args=["OHH"], kwargs={})
        return performed.addCallback(self.assertEquals, {"result": "ohh"})

    def test_lower_case_with_index(self):
        """
        A connected AMP client can issue a L{MethodCall} with keyword arguments
        having default values in the target object.  If a value is specified by
        the caller it will be used in place of the default value
        """
        performed = self.protocol.callRemote(MethodCall, name="lower_case",
                                             args=["OHH"], kwargs={"index": 2})
        return performed.addCallback(self.assertEquals, {"result": "OHh"})

    def test_multiply_alphabetically(self):
        """
        Method arguments passed to a L{MethodCall} can be dictionaries.
        """
        performed = self.protocol.callRemote(MethodCall,
                                             name="multiply_alphabetically",
                                             args=[{"foo": 2, "bar": 3}], kwargs={})
        return performed.addCallback(self.assertEquals,
                                     {"result": "barbarbarfoofoo"})

    def test_translate(self):
        """
        A keyword argument prefixed by C{_} can be used to send a L{MethodCall}
        for a method requiring additional protocol-specific arguments.
        """
        performed = self.protocol.callRemote(MethodCall, name="translate",
                                             args=["hi"],
                                             kwargs={"_language": "factory.language"})
        return performed.addCallback(self.assertEquals, {"result": "ciao"})

    def test_guess(self):
        """
        The L{Hidden} argument type can be used to define L{MethodCall}s for
        methods requiring additional arguments.
        """
        performed = self.protocol.callRemote(MethodCall, name="guess",
                                             args=["word", "cool"],
                                             kwargs={"value": 4})
        return performed.addCallback(self.assertEquals, {"result": "Guessed!"})


class MethodCallSenderTest(TestCase):

    def setUp(self):
        super(MethodCallSenderTest, self).setUp()
        socket = self.mktemp()
        factory = Factory()
        factory.protocol = WordsServerProtocol
        factory.words = Words()
        factory.language = "italian"
        self.port = reactor.listenUNIX(socket, factory)

        def set_protocol(protocol):
            self.protocol = protocol
            self.words = RemoteWords(protocol)

        connector = ClientCreator(reactor, AMP)
        connected = connector.connectUNIX(socket)
        return connected.addCallback(set_protocol)

    def tearDown(self):
        super(MethodCallSenderTest, self).setUp()
        self.port.loseConnection()
        self.protocol.transport.loseConnection()

    def test_empty(self):
        """
        The L{sender} decorator can send L{MethodCall}s without arguments
        and with an empty response.
        """
        performed = self.words.empty()
        return performed.addCallback(self.assertEquals, None)

    def test_motd(self):
        """
        The L{sender} decorator can send L{MethodCall}s without arguments
        and get back the value of the commands's response.
        """
        performed = self.words.motd()
        return performed.addCallback(self.assertEquals, "Words are cool")

    def test_capitalize(self):
        """
        The L{sender} decorator can send L{MethodCall}s with one
        argument and get the response value.
        """
        performed = self.words.capitalize("john")
        return performed.addCallback(self.assertEquals, "John")

    def test_capitalize_with_kwarg(self):
        """
        The L{sender} decorator can send L{MethodCall}s with a named
        argument.
        """
        performed = self.words.capitalize(word="john")
        return performed.addCallback(self.assertEquals, "John")

    def test_is_short(self):
        """
        The return value of a L{MethodCall} argument can be a boolean.
        """
        performed = self.words.is_short("hi")
        return performed.addCallback(self.assertEquals, True)

    def test_concatenate(self):
        """
        The L{sender} decorator can send L{MethodCall}s with more
        than one argument.
        """
        performed = self.words.concatenate("You ", "rock")
        return performed.addCallback(self.assertEquals, "You rock")

    def test_concatenate_with_kwargs(self):
        """
        The L{sender} decorator can send L{MethodCall}s with several
        named arguments.
        """
        performed = self.words.concatenate(word2="rock", word1="You ")
        return performed.addCallback(self.assertEquals, "You rock")

    def test_lower_case(self):
        """
        The L{sender} decorator can send a L{MethodCall} having an argument
        with a default value.
        """
        performed = self.words.lower_case("OHH")
        return performed.addCallback(self.assertEquals, "ohh")

    def test_lower_case_with_index(self):
        """
        The L{sender} decorator can send L{MethodCall}s overriding the default
        value of an argument.
        """
        performed = self.words.lower_case("OHH", 2)
        return performed.addCallback(self.assertEquals, "OHh")

    def test_multiply_alphabetically(self):
        """
        The L{sender} decorator can send a L{MethodCall}s for methods requiring
        a dictionary arguments.
        """
        performed = self.words.multiply_alphabetically({"foo": 2, "bar": 3})
        return performed.addCallback(self.assertEquals, "barbarbarfoofoo")

    def test_translate(self):
        """
        The L{sender} decorator can send a L{MethodCall} requiring protocol
        arguments, which won't be exposed to the caller.
        """
        performed = self.words.translate("hi")
        return performed.addCallback(self.assertEquals, "ciao")

    def test_guess(self):
        """
        The L{sender} decorator behaves well with L{MethodCall}s for methods
        having generic C{*args} and C{**kwargs} arguments.
        """
        performed = self.words.guess("word", "cool", value=4)
        return performed.addCallback(self.assertEquals, "Guessed!")
