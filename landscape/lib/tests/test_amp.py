from twisted.trial.unittest import TestCase
from twisted.internet import reactor
from twisted.internet.protocol import Factory, ClientCreator
from twisted.protocols.amp import AMP, Command, String, Integer

from landscape.lib.amp import amp_rpc_responder, BPickle, Hidden


class Words(object):

    def empty(self):
        pass

    def motd(self):
        return "Words are cool"

    def capitalize(self, word):
        return word.capitalize()

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


class WordsProtocol(AMP):

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


class AmpRcpResponderTest(TestCase):

    def setUp(self):
        super(AmpRcpResponderTest, self).setUp()
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
        super(AmpRcpResponderTest, self).setUp()
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
