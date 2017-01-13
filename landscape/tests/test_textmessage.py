from landscape.textmessage import (
    AcceptedTypeError, EmptyMessageError, got_accepted_types, get_message,
    send_message)
from landscape.tests.helpers import (
    LandscapeTest, FakeBrokerServiceHelper, StandardIOHelper)
from twisted.python.compat import _PY3


def get_message_text(unicode_str):
    """
    A helper to differentiate between Python 2 and 3 encoding for StringIO.
    """
    if _PY3:
        message_text = unicode_str
    else:
        message_text = unicode_str.encode("UTF-8")
    return message_text


class SendMessageTest(LandscapeTest):

    helpers = [StandardIOHelper, FakeBrokerServiceHelper]

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
            self.assertEqual(len(messages), 1)
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

        message_text = get_message_text(u"Foobl\N{HIRAGANA LETTER A}")
        self.stdin.write(message_text)
        self.stdin.seek(0, 0)

        def got_result(result):
            messages = service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 1)
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
        message_text = get_message_text(u"\N{HIRAGANA LETTER A}")
        message = get_message(
            ["landscape-message",
             message_text, "a!"])
        self.assertEqual(message, u"\N{HIRAGANA LETTER A} a!")

    def test_get_message_stdin(self):
        """
        If no arguments are specified then the message should be read
        from stdin.
        """
        message_text = get_message_text(u"Foobl\N{HIRAGANA LETTER A}")
        self.stdin.write(message_text)
        self.stdin.seek(0, 0)
        message = get_message(["landscape-message"])
        self.assertEqual(self.stdout.getvalue(),
                         "Please enter your message, and send EOF "
                         "(Control + D after newline) when done.\n")
        self.assertEqual(message, u"Foobl\N{HIRAGANA LETTER A}")

    def test_get_empty_message_stdin(self):
        """
        If no arguments are specified then the message should be read
        from stdin.
        """
        self.assertRaises(EmptyMessageError,
                          get_message, ["landscape-message"])

    def test_get_message_without_encoding(self):
        """
        If sys.stdin.encoding is None, it's likely a pipe, so try to
        decode it as UTF-8 by default.
        """
        message_text = get_message_text(u"\N{HIRAGANA LETTER A}")
        message = get_message(
            ["landscape-message",
             message_text, "a!"])
        self.assertEqual(message, u"\N{HIRAGANA LETTER A} a!")
