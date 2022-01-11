import sys

from landscape.client.monitor.computertags import ComputerTags
from landscape.client.tests.helpers import MonitorHelper, LandscapeTest


class ComputerTagsTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super(ComputerTagsTest, self).setUp()
        self.plugin = ComputerTags()
        self.monitor.add(self.plugin)

    def test_tags_are_read(self):
        """
        Tags are read from the default config path
        """
        tags = 'check,linode,profile-test'
        file_text = "[client]\ntags = {}".format(tags)
        config_filename = self.config.default_config_filenames[0]
        self.makeFile(file_text, path=config_filename)
        self.assertEqual(self.plugin.get_data(), tags)

    def test_tags_are_read_from_args_path(self):
        """
        Tags are read from path specified in command line args
        """
        tags = 'check,linode,profile-test'
        file_text = "[client]\ntags = {}".format(tags)
        filename = self.makeFile(file_text)
        saved_argv = sys.argv
        try:
            sys.argv = ['hello.py', '--config', filename]
            data = self.plugin.get_data()
        finally:
            sys.argv = saved_argv
        self.assertEqual(data, tags)

    def test_tags_message_sent(self):
        """
        Tags message is sent correctly
        """
        tags = 'check,linode,profile-test'
        file_text = "[client]\ntags = {}".format(tags)
        config_filename = self.config.default_config_filenames[0]
        self.makeFile(file_text, path=config_filename)

        self.mstore.set_accepted_types(["computer-tags"])
        self.plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(messages[0]['tags'], tags)

    def test_invalid_tags(self):
        """
        If invalid tag detected then message contents should be None
        """
        tags = 'check,lin ode'
        file_text = "[client]\ntags = {}".format(tags)
        config_filename = self.config.default_config_filenames[0]
        self.makeFile(file_text, path=config_filename)
        self.assertEqual(self.plugin.get_data(), None)

    def test_empty_tags(self):
        """
        Makes sure no errors when tags section is empty
        """
        self.assertEqual(self.plugin.get_data(), None)
