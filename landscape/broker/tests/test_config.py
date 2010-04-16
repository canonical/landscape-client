import os

from landscape.broker.config import BrokerConfiguration
from landscape.tests.helpers import LandscapeTest, EnvironSaverHelper


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
        self.assertEquals(os.environ["http_proxy"], "foo")
        self.assertEquals(os.environ["https_proxy"], "bar")

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
        self.assertEquals(os.environ["http_proxy"], "heyo")
        self.assertEquals(os.environ["https_proxy"], "baroo")

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
        self.assertEquals(os.environ["http_proxy"], "x")
        self.assertEquals(os.environ["https_proxy"], "y")

        configuration.load(["--url", "whatever"])
        self.assertEquals(os.environ["http_proxy"], "original")
        self.assertEquals(os.environ["https_proxy"], "originals")

    def test_intervals_are_ints(self):
        """
        The 'urgent_exchange_interval and 'exchange_interval' values specified
        in the configuration file are converted to integers.
        """
        filename = self.makeFile("[client]\n"
                                 "urgent_exchange_interval = 12\n"
                                 "exchange_interval = 34\n")

        configuration = BrokerConfiguration()
        configuration.load(["--config", filename, "--url", "whatever"])

        self.assertEquals(configuration.urgent_exchange_interval, 12)
        self.assertEquals(configuration.exchange_interval, 34)
