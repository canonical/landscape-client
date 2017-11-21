import os
import mock

from twisted.python.compat import unicode

from landscape.client.monitor.aptpreferences import AptPreferences
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import MonitorHelper


class AptPreferencesTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super(AptPreferencesTest, self).setUp()
        self.etc_apt_directory = self.makeDir()
        self.plugin = AptPreferences(self.etc_apt_directory)
        self.monitor.add(self.plugin)

    def test_get_data_without_apt_preferences_files(self):
        """
        L{AptPreferences.get_data} returns C{None} if no APT preferences file
        is detected.
        """
        self.assertIdentical(self.plugin.get_data(), None)

    def test_get_data_with_apt_preferences(self):
        """
        L{AptPreferences.get_data} includes the contents of the main APT
        preferences file.
        """
        preferences_filename = os.path.join(self.etc_apt_directory,
                                            "preferences")
        self.makeFile(path=preferences_filename, content="crap")
        self.assertEqual(self.plugin.get_data(),
                         {preferences_filename: "crap"})

    def test_get_data_with_empty_preferences_directory(self):
        """
        L{AptPreferences.get_data} returns C{None} if the APT preference
        directory is present but empty.
        """
        preferences_directory = os.path.join(self.etc_apt_directory,
                                             "preferences.d")
        self.makeDir(path=preferences_directory)
        self.assertIdentical(self.plugin.get_data(), None)

    def test_get_data_with_preferences_directory(self):
        """
        L{AptPreferences.get_data} includes the contents of all the file in the
        APT preferences directory.
        """
        preferences_directory = os.path.join(self.etc_apt_directory,
                                             "preferences.d")
        self.makeDir(path=preferences_directory)
        filename1 = self.makeFile(dirname=preferences_directory, content="foo")
        filename2 = self.makeFile(dirname=preferences_directory, content="bar")
        self.assertEqual(self.plugin.get_data(), {filename1: "foo",
                                                  filename2: "bar"})

    def test_get_data_with_one_big_file(self):
        """
        L{AptPreferences.get_data} truncates the contents of an APT preferences
        files bigger than the size limit.
        """
        preferences_filename = os.path.join(self.etc_apt_directory,
                                            "preferences")
        limit = self.plugin.size_limit
        self.makeFile(path=preferences_filename, content="a" * (limit + 1))
        self.assertEqual(self.plugin.get_data(), {
            preferences_filename: "a" * (limit - len(preferences_filename))})

    def test_get_data_with_many_big_files(self):
        """
        L{AptPreferences.get_data} truncates the contents of individual APT
        preferences files in the total size is bigger than the size limit.
        """
        preferences_directory = os.path.join(self.etc_apt_directory,
                                             "preferences.d")
        self.makeDir(path=preferences_directory)
        limit = self.plugin.size_limit
        filename1 = self.makeFile(dirname=preferences_directory,
                                  content="a" * (limit // 2))
        filename2 = self.makeFile(dirname=preferences_directory,
                                  content="b" * (limit // 2))
        self.assertEqual(self.plugin.get_data(),
                         {filename1: "a" * (limit // 2 - len(filename1)),
                          filename2: "b" * (limit // 2 - len(filename2))})

    def test_exchange_without_apt_preferences_data(self):
        """
        If the system has no APT preferences data, no message is sent.
        """
        self.mstore.set_accepted_types(["apt-preferences"])
        self.plugin.exchange()
        self.assertEqual(self.mstore.get_pending_messages(), [])

    def test_exchange(self):
        """
        If the system has some APT preferences data, a message of type
        C{apt-preferences} is sent. If the data then gets removed, a
        further message with the C{data} field set to C{None} is sent.
        """
        self.mstore.set_accepted_types(["apt-preferences"])
        main_preferences_filename = os.path.join(self.etc_apt_directory,
                                                 "preferences")
        self.makeFile(path=main_preferences_filename, content="crap")
        preferences_directory = os.path.join(self.etc_apt_directory,
                                             "preferences.d")
        self.makeDir(path=preferences_directory)
        sub_preferences_filename = self.makeFile(dirname=preferences_directory,
                                                 content="foo")
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(messages[0]["type"], "apt-preferences")
        self.assertEqual(messages[0]["data"],
                         {main_preferences_filename: u"crap",
                          sub_preferences_filename: u"foo"})
        for filename in messages[0]["data"]:
            self.assertTrue(isinstance(filename, unicode))

        # Remove all APT preferences data from the system
        os.remove(main_preferences_filename)
        os.remove(sub_preferences_filename)
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(messages[1]["type"], "apt-preferences")
        self.assertIdentical(messages[1]["data"], None)

    def test_exchange_only_once(self):
        """
        If the system has some APT preferences data, a message of type
        C{apt-preferences} is sent. If the data then gets removed, a
        further message with the C{data} field set to C{None} is sent.
        """
        self.mstore.set_accepted_types(["apt-preferences"])
        preferences_filename = os.path.join(self.etc_apt_directory,
                                            "preferences")
        self.makeFile(path=preferences_filename, content="crap")
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)

    def test_run(self):
        """
        If the server can accept them, the plugin should send
        C{apt-preferences} urgent messages.
        """
        self.mstore.set_accepted_types(["apt-preferences"])

        preferences_filename = os.path.join(self.etc_apt_directory,
                                            "preferences")
        self.makeFile(path=preferences_filename, content="crap")

        with mock.patch.object(self.remote, "send_message"):
            self.plugin.run()
            self.mstore.set_accepted_types([])
            self.plugin.run()
            self.remote.send_message.assert_called_once_with(
                mock.ANY, mock.ANY, urgent=True)

    def test_resynchronize(self):
        """
        The "resynchronize" reactor message cause the plugin to send fresh
        data.
        """
        preferences_filename = os.path.join(self.etc_apt_directory,
                                            "preferences")
        self.makeFile(path=preferences_filename, content="crap")
        self.mstore.set_accepted_types(["apt-preferences"])
        self.plugin.run()
        self.reactor.fire("resynchronize", scopes=["package"])
        self.plugin.run()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)
