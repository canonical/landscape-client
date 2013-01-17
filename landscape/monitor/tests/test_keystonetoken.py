import os
from landscape.tests.helpers import LandscapeTest

from landscape.monitor.keystonetoken import KeystoneToken


class KeystoneTokenTest(LandscapeTest):

    def setUp(self):
        super(KeystoneTokenTest, self).setUp()
        self.keystone_file = os.path.join(self.makeDir(), "keystone.conf")
        self.plugin = KeystoneToken(self.keystone_file)

    def test_get_keystone_token_nonexistent(self):
        """
        The plugin provides no data when the keystone configuration file
        doesn't exist.
        """
        self.log_helper.ignore_errors("KeystoneToken: No admin_token found .*")
        self.assertIs(None, self.plugin.get_data())

    def test_get_keystone_token_empty(self):
        """
        The plugin provides no data when the keystone configuration file is
        empty.
        """
        self.log_helper.ignore_errors("KeystoneToken: No admin_token found .*")
        self.makeFile(path=self.keystone_file, content="")
        self.assertIs(None, self.plugin.get_data())

    def test_get_keystone_token_no_admin_token(self):
        """
        The plugin provides no data when the keystone configuration doesn't
        have an admin_token field.
        """
        self.log_helper.ignore_errors("KeystoneToken: No admin_token found .*")
        self.makeFile(path=self.keystone_file, content="[DEFAULT]")
        self.assertIs(None, self.plugin.get_data())

    def test_get_keystone_token(self):
        """
        Finally! Some data is actually there!
        """
        self.makeFile(
            path=self.keystone_file,
            content="[DEFAULT]\nadmin_token = foobar")
        self.assertEqual("foobar", self.plugin.get_data())

    def test_get_keystone_token_non_utf8(self):
        """
        The data can be arbitrary bytes.
        """
        content = "[DEFAULT]\nadmin_token = \xff"
        self.makeFile(
            path=self.keystone_file,
            content=content)
        self.assertEqual("\xff", self.plugin.get_data())
