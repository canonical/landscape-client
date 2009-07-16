import sys

from landscape.broker.remote import RemoteBroker
from landscape.textmessage import (
    AcceptedTypeError, EmptyMessageError, got_accepted_types, get_message,
    send_message)
from landscape.tests.helpers import (
    LandscapeTest, FakeRemoteBrokerHelper, StandardIOHelper)


class SendMessageTest(LandscapeTest):

    helpers = [StandardIOHelper, FakeRemoteBrokerHelper]

    def test_send_message(self):
        """
        L{send_message} should send a message of type
        C{text-message} to the landscape dbus messaging service.
        """
        service = self.broker_service
        service.message_store.set_accepted_types(["text-message"])

        result = send_message(u"Hi there!", self.remote)
        def got_result(result):
            messages = service.message_store.get_pending_messages()
            self.assertEquals(len(messages), 1)
            self.assertMessage(messages[0], {"type": "text-message",
                                             "message": u"Hi there!"})
            self.assertTrue(service.exchanger.is_urgent())
        return result.addCallback(got_result)

    def test_got_accepted_types_without_text_message_type(self):
        """
        If 'text-message' isn't in the list of accepted types an
        L{AcceptedTypeError} is raised.
        """
        self.assertRaises(AcceptedTypeError, got_accepted_types, (),
                          self.remote, ())

    def test_got_accepted_types(self):
        """
        If 'text-message' is an accepted type a message should be
        retrieved from the user and sent to the broker.
        """
        service = self.broker_service
        service.message_store.set_accepted_types(["text-message"])

        input = u"Foobl\N{HIRAGANA LETTER A}"
        self.stdin.write(input.encode("UTF-8"))
        self.stdin.seek(0, 0)

        def got_result(result):
            messages = service.message_store.get_pending_messages()
            self.assertEquals(len(messages), 1)
            self.assertMessage(messages[0],
                               {"type": "text-message",
                                "message": u"Foobl\N{HIRAGANA LETTER A}"})

        d = got_accepted_types(["text-message"], self.remote, ())
        d.addCallback(got_result)
        return d


class ScriptTest(LandscapeTest):

    helpers = [StandardIOHelper]

    def test_get_message(self):
        """
        A message should be properly decoded from the command line arguments.
        """
        message = get_message(
            ["landscape-message",
             u"\N{HIRAGANA LETTER A}".encode(sys.stdin.encoding), "a!"])
        self.assertEquals(message, u"\N{HIRAGANA LETTER A} a!")

    def test_get_message_stdin(self):
        """
        If no arguments are specified then the message should be read
        from stdin.
        """
        input = u"Foobl\N{HIRAGANA LETTER A}"
        self.stdin.write(input.encode("UTF-8"))
        self.stdin.seek(0, 0)
        message = get_message(["landscape-message"])
        self.assertEquals(self.stdout.getvalue(),
                          "Please enter your message, and send EOF "
                          "(Control + D after newline) when done.\n")
        self.assertEquals(message, input)

    def test_get_empty_message_stdin(self):
        """
        If no arguments are specified then the message should be read
        from stdin.
        """
        self.assertRaises(EmptyMessageError, get_message, ["landscape-message"])

    def test_get_message_without_encoding(self):
        """
        If sys.stdin.encoding is None, it's likely a pipe, so try to
        decode it as UTF-8 by default.
        """
        encoding = sys.stdin.encoding
        sys.stdin.encoding = None
        try:
            message = get_message(
                ["landscape-message",
                 u"\N{HIRAGANA LETTER A}".encode("UTF-8"), "a!"])
        finally:
            sys.stdin.encoding = encoding
        self.assertEquals(message, u"\N{HIRAGANA LETTER A} a!")
