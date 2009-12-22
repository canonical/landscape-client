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


class WordsProtocol(MethodCallProtocol):

    @property
    def _object(self):
        return self.factory.words

    @Empty.responder
    def empty(self):
        pass

    @Motd.responder
    def motd(self):
        pass

    @Capitalize.responder
    def capitalize(self, word):
        pass

    @Synonym.responder
    def synonym(self, word):
        pass

    @Concatenate.responder
    def concatenate(self, word1, word2):
        pass

    @LowerCase.responder
    def lower_case(self, word, index):
        pass

    @MultiplyAlphabetically.responder
    def multiply_alphabetically(self, word_times):
        pass

    @Translate.responder
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


class MethodCallResponderTest(TestCase):

    def setUp(self):
        super(MethodCallResponderTest, self).setUp()
        socket = self.mktemp()
        factory = Factory()
        factory.protocol = WordsProtocol
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
