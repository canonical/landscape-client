import os

from twisted.internet.defer import succeed

from landscape.monitor.aptpreferences import AptPreferences
from landscape.tests.helpers import LandscapeIsolatedTest
from landscape.tests.helpers import MonitorHelper
from landscape.tests.mocker import ANY


class AptPreferencesTest(LandscapeIsolatedTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super(AptPreferencesTest, self).setUp()
        self.etc_apt_directory = self.makeDir()
        self.plugin = AptPreferences(self.etc_apt_directory)
        self.monitor.add(self.plugin)

    def test_get_data_without_apt_preferences_files(self):
        """
        L{AptPreferences.get_data} returns an empty C{dict} if no APT
        preferences file is detected.
        """
        self.assertEquals(self.plugin.get_data(), None)

    def test_get_data_with_apt_preferences(self):
        """
        L{AptPreferences.get_data} includes the contents of the main APT
        preferences file.
        """
        preferences_filename = os.path.join(self.etc_apt_directory,
                                            "preferences")
        self.makeFile(path=preferences_filename, content="crap")
        self.assertEquals(self.plugin.get_data(),
                          {preferences_filename: "crap"})

    def test_get_data_with_empty_preferences_directory(self):
        """
        L{AptPreferences.get_data} returns an empty C{dict} if the APT
        preference directory is present but empty.
        """
        preferences_directory = os.path.join(self.etc_apt_directory,
                                             "preferences.d")
        self.makeDir(path=preferences_directory)
        self.assertEquals(self.plugin.get_data(), None)

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
        self.assertEquals(self.plugin.get_data(), {filename1: "foo",
                                                   filename2: "bar"})

    def test_exchange_without_apt_preferences_data(self):
        """
        If the system has no APT preferences data, no message is sent.
        """
        self.mstore.set_accepted_types(["apt-preferences"])
        self.plugin.exchange()
        self.assertEquals(self.mstore.get_pending_messages(), [])

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
        self.assertEquals(messages[0]["type"], "apt-preferences")
        self.assertEquals(messages[0]["data"],
                          {main_preferences_filename: u"crap",
                           sub_preferences_filename: u"foo"})
        for filename in messages[0]["data"]:
            self.assertTrue(isinstance(filename, unicode))

        # Remove all APT preferences data from the system
        os.remove(main_preferences_filename)
        os.remove(sub_preferences_filename)
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(messages[1]["type"], "apt-preferences")
        self.assertEquals(messages[1]["data"], None)

    def test_run(self):
        """
        If the server can accept them, the plugin should send C{apt-preferences}
        urgent messages.
        """
        self.mstore.set_accepted_types(["apt-preferences"])
        broker_mock = self.mocker.replace(self.remote)
        broker_mock.send_message(ANY, urgent=True)
        self.mocker.result(succeed(None))
        self.mocker.replay()
        preferences_filename = os.path.join(self.etc_apt_directory,
                                            "preferences")
        self.makeFile(path=preferences_filename, content="crap")
        self.plugin.run()
        self.mstore.set_accepted_types([])
        self.plugin.run()
