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

    def test_get_data(self):
        """
        L{AptPinning.get_data} should return C{True} if the an APT preferences
        file is present.
        """
        self.assertFalse(self.plugin.get_data())
        preferences_filename = os.path.join(self.etc_apt_directory,
                                            "preferences")
        self.makeFile(path=preferences_filename, content="crap")
        self.assertTrue(self.plugin.get_data())

    def test_get_data_with_preferences_directory(self):
        """
        L{AptPinning.get_data} should return C{True} if the a file the APT
        preferences directory is present.
        """
        preferences_directory = os.path.join(self.etc_apt_directory,
                                             "preferences.d")
        self.makeDir(path=preferences_directory)
        self.assertFalse(self.plugin.get_data())
        self.makeFile(dirname=preferences_directory, content="crap")
        self.assertTrue(self.plugin.get_data())

    def test_exchange(self):
        """
        The L{AptPinning.exchange} method sends messages of type "apt-pinning".
        """
        self.mstore.set_accepted_types(["apt-pinning"])
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(messages[0]["type"], "apt-pinning")
        self.assertEquals(messages[0]["status"], False)

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
