import os

from landscape.client.broker.config import BrokerConfiguration
from landscape.lib.testing import EnvironSaverHelper
from landscape.client.tests.helpers import LandscapeTest


class ConfigurationTests(LandscapeTest):

    helpers = [EnvironSaverHelper]

    def test_loading_sets_http_proxies(self):
        """
        The L{BrokerConfiguration.load} method sets the 'http_proxy' and
        'https_proxy' enviroment variables to the provided values.
        """
        if "http_proxy" in os.environ:
            del os.environ["http_proxy"]
        if "https_proxy" in os.environ:
            del os.environ["https_proxy"]

        configuration = BrokerConfiguration()
        configuration.load(["--http-proxy", "foo",
                            "--https-proxy", "bar",
                            "--url", "whatever"])
        self.assertEqual(os.environ["http_proxy"], "foo")
        self.assertEqual(os.environ["https_proxy"], "bar")

    def test_loading_without_http_proxies_does_not_touch_environment(self):
        """
        The L{BrokerConfiguration.load} method doesn't override the
        'http_proxy' and 'https_proxy' enviroment variables if they
        are already set and no new value was specified.
        """
        os.environ["http_proxy"] = "heyo"
        os.environ["https_proxy"] = "baroo"

        configuration = BrokerConfiguration()
        configuration.load(["--url", "whatever"])
        self.assertEqual(os.environ["http_proxy"], "heyo")
        self.assertEqual(os.environ["https_proxy"], "baroo")

    def test_loading_resets_http_proxies(self):
        """
        User scenario:

        Runs landscape-config, fat-fingers a random character into the
        http_proxy field when he didn't mean to. runs it again, this time
        leaving it blank. The proxy should be reset to whatever
        environment-supplied proxy there was at startup.
        """
        os.environ["http_proxy"] = "original"
        os.environ["https_proxy"] = "originals"

        configuration = BrokerConfiguration()
        configuration.load(["--http-proxy", "x",
                            "--https-proxy", "y",
                            "--url", "whatever"])
        self.assertEqual(os.environ["http_proxy"], "x")
        self.assertEqual(os.environ["https_proxy"], "y")

        configuration.load(["--url", "whatever"])
        self.assertEqual(os.environ["http_proxy"], "original")
        self.assertEqual(os.environ["https_proxy"], "originals")

    def test_default_exchange_intervals(self):
        """Exchange intervales are set to sane defaults."""
        configuration = BrokerConfiguration()
        self.assertEqual(60, configuration.urgent_exchange_interval)
        self.assertEqual(900, configuration.exchange_interval)

    def test_intervals_are_ints(self):
        """
        The 'urgent_exchange_interval, 'exchange_interval' and 'ping_interval'
        values specified in the configuration file are converted to integers.
        """
        filename = self.makeFile("[client]\n"
                                 "urgent_exchange_interval = 12\n"
                                 "exchange_interval = 34\n"
                                 "ping_interval = 6\n")

        configuration = BrokerConfiguration()
        configuration.load(["--config", filename, "--url", "whatever"])

        self.assertEqual(configuration.urgent_exchange_interval, 12)
        self.assertEqual(configuration.exchange_interval, 34)
        self.assertEqual(configuration.ping_interval, 6)

    def test_tag_handling(self):
        """
        The 'tags' value specified in the configuration file is not converted
        to a list (it must be a string). See bug #1228301.
        """
        filename = self.makeFile("[client]\n"
                                 "tags = check,linode,profile-test")

        configuration = BrokerConfiguration()
        configuration.load(["--config", filename, "--url", "whatever"])

        self.assertEqual(configuration.tags, "check,linode,profile-test")

    def test_access_group_handling(self):
        """
        The 'access_group' value specified in the configuration file is
        passed through.
        """
        filename = self.makeFile("[client]\n"
                                 "access_group = webserver")

        configuration = BrokerConfiguration()
        configuration.load(["--config", filename, "--url", "whatever"])

        self.assertEqual(configuration.access_group, "webserver")

    def test_missing_url_is_defaulted(self):
        """
        Test that if we don't explicitly pass a URL, then this value is
        defaulted.
        """
        filename = self.makeFile("[client]\n")

        configuration = BrokerConfiguration()
        configuration.load(["--config", filename])

        self.assertEqual(configuration.url,
                         "https://landscape.canonical.com/message-system")
