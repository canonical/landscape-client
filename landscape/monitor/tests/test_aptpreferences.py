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
        self.assertEquals(self.plugin.get_data(), {})

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
        L{AptPreferences.get_data} returns an empty C{dict} if the APT preference
        directory is present but empty.
        """
        preferences_directory = os.path.join(self.etc_apt_directory,
                                             "preferences.d")
        self.makeDir(path=preferences_directory)
        self.assertEquals(self.plugin.get_data(), {})

    def test_get_data_with_preferences_directory(self):
        """
        L{AptPreferences.get_data} includes the contents of all the file in the APT
        preferences directory.
        """
        preferences_directory = os.path.join(self.etc_apt_directory,
                                             "preferences.d")
        self.makeDir(path=preferences_directory)
        filename1 = self.makeFile(dirname=preferences_directory, content="foo")
        filename2 = self.makeFile(dirname=preferences_directory, content="bar")
        self.assertEquals(self.plugin.get_data(), {filename1: "foo",
                                                   filename2: "bar"})

    def test_exchange(self):
        """
        The L{AptPreferences.exchange} method sends messages of
        type "apt-preferences".
        """
        self.mstore.set_accepted_types(["apt-preferences"])
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(messages[0]["type"], "apt-preferences")
        self.assertEquals(messages[0]["contents"], {})

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
