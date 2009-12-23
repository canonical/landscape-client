from twisted.trial.unittest import TestCase
from twisted.internet import reactor
from twisted.internet.protocol import Factory, ClientCreator
from twisted.protocols.amp import AMP, String, Integer

from landscape.lib.amp import (
    StringOrNone, BPickle, ProtocolAttribute, MethodCall, MethodCallProtocol,
    get_nested_attr)


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


class Empty(MethodCall):

    arguments = []
    response = []


class Motd(MethodCall):

    arguments = []
    response = [("result", String())]


class Capitalize(MethodCall):

    arguments = [("word", String())]
    response = [("result", String())]


class Synonym(MethodCall):

    arguments = [("word", String())]
    response = [("result", StringOrNone())]


class Concatenate(MethodCall):

    arguments = [("word1", String()), ("word2", String())]
    response = [("result", String())]


class LowerCase(MethodCall):

    arguments = [("word", String()), ("index", Integer(optional=True))]
    response = [("result", String())]


class MultiplyAlphabetically(MethodCall):

    arguments = [("word_times", BPickle())]
    response = [("result", String())]


class Translate(MethodCall):

    arguments = [("word", String()), ("__protocol_attribute_language",
                                      ProtocolAttribute("factory.language"))]
    response = [("result", String())]


class WordsServerProtocol(MethodCallProtocol):

    @property
    def _object(self):
        return self.factory.words

    @Empty.responder
    def _empty(self):
        pass

    @Motd.responder
    def _motd(self):
        pass

    @Capitalize.responder
    def _capitalize(self, word):
        pass

    @Synonym.responder
    def _synonym(self, word):
        pass

    @Concatenate.responder
    def _concatenate(self, word1, word2):
        pass

    @LowerCase.responder
    def _lower_case(self, word, index):
        pass

    @MultiplyAlphabetically.responder
    def _multiply_alphabetically(self, word_times):
        pass

    @Translate.responder
    def _translate(self, word):
        pass


class RemoteWords(object):

    def __init__(self, protocol):
        self._protocol = protocol

    @Empty.sender
    def empty(self):
        pass

    @Motd.sender
    def motd(self):
        pass

    @Capitalize.sender
    def capitalize(self, word):
        pass

    @Synonym.sender
    def synonym(self, word):
        pass

    @Concatenate.sender
    def concatenate(self, word1, word2):
        pass

    @LowerCase.sender
    def lower_case(self, word, index=None):
        pass

    @MultiplyAlphabetically.sender
    def multiply_alphabetically(self, word_times):
        pass

    @Translate.sender
    def translate(self, word):
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


class MethodCallTest(TestCase):

    def test_get_method_name(self):
        """
        The L{get_method_name} function returns the target object method
        name associated the given C{MethodCall}.
        """
        self.assertEquals(Empty.get_method_name(), "empty")
        self.assertEquals(LowerCase.get_method_name(), "lower_case")


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
        A connected AMP client can issue a command without arguments and with
        an empty response.
        """
        performed = self.protocol.callRemote(Empty)
        return performed.addCallback(self.assertEquals, {})

    def test_motd(self):
        """
        A connected AMP client can issue a command targeted to an object
        method with a return value.
        """
        performed = self.protocol.callRemote(Motd)
        return performed.addCallback(self.assertEquals,
                                     {"result": "Words are cool"})

    def test_capitalize(self):
        """
        A connected AMP client can issue a command with one argument and
        a response value.
        """
        performed = self.protocol.callRemote(Capitalize, word="john")
        return performed.addCallback(self.assertEquals, {"result": "John"})

    def test_synonim(self):
        """
        The L{StringOrNone} argument normally behaves like a L{String}
        """
        performed = self.protocol.callRemote(Synonym, word="hi")
        return performed.addCallback(self.assertEquals, {"result": "hello"})

    def test_synonim_with_none(self):
        """
        The value of a L{StringOrNone} argument can be C{None}.
        """
        performed = self.protocol.callRemote(Synonym, word="foo")
        return performed.addCallback(self.assertEquals, {"result": None})

    def test_concatenate(self):
        """
        A connected AMP client can issue a command with many arguments.
        """
        performed = self.protocol.callRemote(Concatenate,
                                             word1="You ", word2="rock")
        return performed.addCallback(self.assertEquals, {"result": "You rock"})

    def test_lower_case(self):
        """
        A connected AMP client can issue a command with many arguments some
        of which have default values in the target object.
        """
        performed = self.protocol.callRemote(LowerCase, word="OHH")
        return performed.addCallback(self.assertEquals, {"result": "ohh"})

    def test_lower_case_with_index(self):
        """
        A connected AMP client can issue a command with many arguments some
        of which have default values in the target object.  If a value is
        specified by the caller it will be used in place of the default value
        """
        performed = self.protocol.callRemote(LowerCase, word="OHH", index=2)
        return performed.addCallback(self.assertEquals, {"result": "OHh"})

    def test_multiply_alphabetically(self):
        """
        The L{BPickle} argument type can be used to define L{MethodCall}s for
        methods requiring dictionary arguments.
        """
        performed = self.protocol.callRemote(MultiplyAlphabetically,
                                             word_times={"foo": 2, "bar": 3})
        return performed.addCallback(self.assertEquals,
                                     {"result": "barbarbarfoofoo"})

    def test_translate(self):
        """
        The L{Hidden} argument type can be used to define L{MethodCall}s for
        methods requiring additional arguments.
        """
        performed = self.protocol.callRemote(Translate, word="hi")
        return performed.addCallback(self.assertEquals, {"result": "ciao"})


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
        The L{amp_rpc_caller} decorator can send commands without arguments
        and with an empty response.
        """
        performed = self.words.empty()
        return performed.addCallback(self.assertEquals, None)

    def test_motd(self):
        """
        The L{amp_rpc_caller} decorator can send commands without arguments
        and get back the value of the commands's response.
        """
        performed = self.words.motd()
        return performed.addCallback(self.assertEquals, "Words are cool")

    def test_capitalize(self):
        """
        The L{amp_rpc_caller} decorator can send commands with one
        argument and get the response value.
        """
        performed = self.words.capitalize("john")
        return performed.addCallback(self.assertEquals, "John")

    def test_capitalize_with_kwarg(self):
        """
        The L{amp_rpc_caller} decorator can send commands with a named
        argument.
        """
        performed = self.words.capitalize(word="john")
        return performed.addCallback(self.assertEquals, "John")

    def test_concatenate(self):
        """
        The L{amp_rpc_caller} decorator can send commands with more
        than one argument.
        """
        performed = self.words.concatenate("You ", "rock")
        return performed.addCallback(self.assertEquals, "You rock")

    def test_concatenate_with_kwargs(self):
        """
        The L{amp_rpc_caller} decorator can send commands with several
        named arguments.
        """
        performed = self.words.concatenate(word2="rock", word1="You ")
        return performed.addCallback(self.assertEquals, "You rock")

    def test_lower_case(self):
        """
        The L{amp_rpc_caller} decorator can send a command having an
        argument with a default value.
        """
        performed = self.words.lower_case("OHH")
        return performed.addCallback(self.assertEquals, "ohh")

    def test_lower_case_with_index(self):
        """
        The L{amp_rpc_caller} decorator can send a command overriding
        the default value of an argument.
        """
        performed = self.words.lower_case("OHH", 2)
        return performed.addCallback(self.assertEquals, "OHh")

    def test_multiply_alphabetically(self):
        """
        The L{amp_rpc_caller} decorator can send a command requiring a
        {BPickle} argument, transparently handling the serialization.
        """
        performed = self.words.multiply_alphabetically({"foo": 2, "bar": 3})
        return performed.addCallback(self.assertEquals, "barbarbarfoofoo")

    def test_translate(self):
        """
        The L{amp_rpc_caller} decorator can send a command requiring L{Hidden}
        arguments, which won't be exposed to the caller.
        """
        performed = self.words.translate("hi")
        return performed.addCallback(self.assertEquals, "ciao")
