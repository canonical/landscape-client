import os

from twisted.internet.defer import succeed

from landscape.monitor.aptpinning import AptPinning
from landscape.tests.helpers import LandscapeIsolatedTest
from landscape.tests.helpers import MonitorHelper
from landscape.tests.mocker import ANY


class AptPinningTest(LandscapeIsolatedTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super(AptPinningTest, self).setUp()
        self.etc_apt_directory = self.makeDir()
        self.plugin = AptPinning(self.etc_apt_directory)
        self.monitor.add(self.plugin)
        self.mstore.set_accepted_types(["apt-pinning"])

    def test_get_data_without_apt_pinning_files(self):
        """
        L{AptPinning.get_data} returns an empty C{dict} if not APT pinning
        file is detected.
        """
        self.assertEquals(self.plugin.get_data(), {})

    def test_get_data_with_apt_preferences(self):
        """
        L{AptPinning.get_data} includes the contents of the main APT pinning
        preferences file.
        """
        preferences_filename = os.path.join(self.etc_apt_directory,
                                            "preferences")
        self.makeFile(path=preferences_filename, content="crap")
        self.assertEquals(self.plugin.get_data(),
                          {preferences_filename: "crap"})

    def test_get_data_with_empty_preferences_directory(self):
        """
        L{AptPinning.get_data} returns an empty C{dict} if the APT preference
        directory is present but empty.
        """
        preferences_directory = os.path.join(self.etc_apt_directory,
                                             "preferences.d")
        self.makeDir(path=preferences_directory)
        self.assertEquals(self.plugin.get_data(), {})

    def test_get_data_with_preferences_directory(self):
        """
        L{AptPinning.get_data} includes the contents of all the file in the APT
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
        The L{AptPinning.exchange} method sends messages of type "apt-pinning".
        """
        self.mstore.set_accepted_types(["apt-pinning"])
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(messages[0]["type"], "apt-pinning")
        self.assertEquals(messages[0]["files"], {})

    def test_run(self):
        """
        If the server can accept them, the plugin should send C{apt-pinning}
        urgent messages.
        """
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
