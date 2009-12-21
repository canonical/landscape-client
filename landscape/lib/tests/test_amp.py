from twisted.trial.unittest import TestCase
from twisted.internet import reactor
from twisted.internet.protocol import Factory, ClientCreator
from twisted.protocols.amp import AMP, Command, String, Integer

from landscape.lib.amp import (
    amp_rpc_responder, amp_rpc_caller, StringOrNone, BPickle, Hidden)


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


class Empty(Command):

    arguments = []
    response = []


class Motd(Command):

    arguments = []
    response = [("result", String())]


class Capitalize(Command):

    arguments = [("word", String())]
    response = [("result", String())]


class Synonym(Command):

    arguments = [("word", String())]
    response = [("result", StringOrNone())]


class Concatenate(Command):

    arguments = [("word1", String()), ("word2", String())]
    response = [("result", String())]


class LowerCase(Command):

    arguments = [("word", String()), ("index", Integer(optional=True))]
    response = [("result", String())]


class MultiplyAlphabetically(Command):

    arguments = [("word_times", BPickle())]
    response = [("result", String())]


class Translate(Command):

    arguments = [("word", String()),
                 ("__amp_rpc_language", Hidden(".factory.language"))]
    response = [("result", String())]


class WordsServerProtocol(AMP):

    __amp_rpc_model__ = ".factory.words"

    @amp_rpc_responder
    def empty(self):
        pass

    @amp_rpc_responder
    def motd(self):
        pass

    @amp_rpc_responder
    def capitalize(self, word):
        pass

    @amp_rpc_responder
    def synonym(self, word):
        pass

    @amp_rpc_responder
    def concatenate(self, word1, word2):
        pass

    @amp_rpc_responder
    def lower_case(self, word, index):
        pass

    @amp_rpc_responder
    def multiply_alphabetically(self, word_times):
        pass

    @amp_rpc_responder
    def translate(self, word):
        pass


class WordsClientProtocol(AMP):

    @amp_rpc_caller
    def empty(self):
        pass

    @amp_rpc_caller
    def motd(self):
        pass

    @amp_rpc_caller
    def capitalize(self, word):
        pass

    @amp_rpc_caller
    def synonym(self, word):
        pass

    @amp_rpc_caller
    def concatenate(self, word1, word2):
        pass

    @amp_rpc_caller
    def lower_case(self, word, index=None):
        pass

    @amp_rpc_caller
    def multiply_alphabetically(self, word_times):
        pass

    @amp_rpc_caller
    def translate(self, word):
        pass


class AmpRpcResponderTest(TestCase):

    def setUp(self):
        super(AmpRpcResponderTest, self).setUp()
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
        super(AmpRpcResponderTest, self).setUp()
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
        A connected AMP client can issue a command targeted to a model
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
        of which have default values in the model.
        """
        performed = self.protocol.callRemote(LowerCase, word="OHH")
        return performed.addCallback(self.assertEquals, {"result": "ohh"})

    def test_lower_case_with_index(self):
        """
        A connected AMP client can issue a command with many arguments some
        of which have default values in the model.  If a value is specified
        by the caller it will be used in place of the default value
        """
        performed = self.protocol.callRemote(LowerCase, word="OHH", index=2)
        return performed.addCallback(self.assertEquals, {"result": "OHh"})

    def test_multiply_alphabetically(self):
        """
        The L{BPickle} argument type can be used for model commands requiring
        dictionary arguments.
        """
        performed = self.protocol.callRemote(MultiplyAlphabetically,
                                             word_times={"foo": 2, "bar": 3})
        return performed.addCallback(self.assertEquals,
                                     {"result": "barbarbarfoofoo"})

    def test_translate(self):
        """
        The L{Hidden} argument type can be used for model commands requiring
        dictionary arguments.
        """
        performed = self.protocol.callRemote(Translate, word="hi")
        return performed.addCallback(self.assertEquals, {"result": "ciao"})


class AmpRpcCallerTest(TestCase):

    def setUp(self):
        super(AmpRpcCallerTest, self).setUp()
        socket = self.mktemp()
        factory = Factory()
        factory.protocol = WordsServerProtocol
        factory.words = Words()
        factory.language = "italian"
        self.port = reactor.listenUNIX(socket, factory)

        def set_protocol(protocol):
            self.protocol = protocol

        connector = ClientCreator(reactor, WordsClientProtocol)
        connected = connector.connectUNIX(socket)
        return connected.addCallback(set_protocol)

    def tearDown(self):
        super(AmpRpcCallerTest, self).setUp()
        self.port.loseConnection()
        self.protocol.transport.loseConnection()

    def test_empty(self):
        """
        The L{amp_rpc_caller} decorator can send commands without arguments
        and with an empty response.
        """
        performed = self.protocol.empty()
        return performed.addCallback(self.assertEquals, None)

    def test_motd(self):
        """
        The L{amp_rpc_caller} decorator can send commands without arguments
        and get back the value of the commands's response.
        """
        performed = self.protocol.motd()
        return performed.addCallback(self.assertEquals, "Words are cool")

    def test_capitalize(self):
        """
        The L{amp_rpc_caller} decorator can send commands with one
        argument and get the response value.
        """
        performed = self.protocol.capitalize("john")
        return performed.addCallback(self.assertEquals, "John")

    def test_capitalize_with_kwarg(self):
        """
        The L{amp_rpc_caller} decorator can send commands with a named
        argument.
        """
        performed = self.protocol.capitalize(word="john")
        return performed.addCallback(self.assertEquals, "John")

    def test_concatenate(self):
        """
        The L{amp_rpc_caller} decorator can send commands with more
        than one argument.
        """
        performed = self.protocol.concatenate("You ", "rock")
        return performed.addCallback(self.assertEquals, "You rock")

    def test_concatenate_with_kwargs(self):
        """
        The L{amp_rpc_caller} decorator can send commands with several
        named arguments.
        """
        performed = self.protocol.concatenate(word2="rock", word1="You ")
        return performed.addCallback(self.assertEquals, "You rock")

    def test_lower_case(self):
        """
        The L{amp_rpc_caller} decorator can send a command having an
        argument with a default value.
        """
        performed = self.protocol.lower_case("OHH")
        return performed.addCallback(self.assertEquals, "ohh")

    def test_lower_case_with_index(self):
        """
        The L{amp_rpc_caller} decorator can send a command overriding
        the default value of an argument.
        """
        performed = self.protocol.lower_case("OHH", 2)
        return performed.addCallback(self.assertEquals, "OHh")

    def test_multiply_alphabetically(self):
        """
        The L{amp_rpc_caller} decorator can send a command requiring a
        {BPickle} argument, transparently handling the serialization.
        """
        performed = self.protocol.multiply_alphabetically({"foo": 2, "bar": 3})
        return performed.addCallback(self.assertEquals, "barbarbarfoofoo")

    def test_translate(self):
        """
        The L{amp_rpc_caller} decorator can send a command requiring L{Hidden}
        arguments, which won't be exposed to the caller.
        """
        performed = self.protocol.translate("hi")
        return performed.addCallback(self.assertEquals, "ciao")
