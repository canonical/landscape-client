"""Configuration class for the broker."""

import os

from landscape.client.deployment import Configuration


class BrokerConfiguration(Configuration):
    """Specialized configuration for the Landscape Broker.

    @cvar required_options: C{["url"]}
    """

    def __init__(self):
        super(BrokerConfiguration, self).__init__()
        self._original_http_proxy = os.environ.get("http_proxy")
        self._original_https_proxy = os.environ.get("https_proxy")

    @property
    def exchange_store_path(self):
        return os.path.join(self.data_path, "exchange.database")

    def make_parser(self):
        """Parser factory for broker-specific options.

        @return: An L{OptionParser} preset for all the options
            from L{Configuration.make_parser} plus:
              - C{account_name}
              - C{registration_key}
              - C{computer_title}
              - C{exchange_interval} (C{15*60})
              - C{urgent_exchange_interval} (C{1*60})
              - C{http_proxy}
              - C{https_proxy}
        """
        parser = super(BrokerConfiguration, self).make_parser()

        parser.add_option("-a", "--account-name", metavar="NAME",
                          help="The account this computer belongs to.")
        parser.add_option("-p", "--registration-key", metavar="KEY",
                          help="The account-wide key used for "
                               "registering clients.")
        parser.add_option("-t", "--computer-title", metavar="TITLE",
                          help="The title of this computer")
        parser.add_option("--exchange-interval", default=15 * 60, type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between server "
                               "exchanges.")
        parser.add_option("--urgent-exchange-interval", default=1 * 60,
                          type="int", metavar="INTERVAL",
                          help="The number of seconds between urgent server "
                               "exchanges.")
        parser.add_option("--ping-interval", default=30, type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between pings.")
        parser.add_option("--http-proxy", metavar="URL",
                          help="The URL of the HTTP proxy, if one is needed.")
        parser.add_option("--https-proxy", metavar="URL",
                          help="The URL of the HTTPS proxy, if one is needed.")
        parser.add_option("--access-group", default="",
                          help="Suggested access group for this computer.")
        parser.add_option("--tags",
                          help="Comma separated list of tag names to be sent "
                               "to the server.")

        return parser

    @property
    def message_store_path(self):
        """Get the path to the message store."""
        return os.path.join(self.data_path, "messages")

    def load(self, args):
        """
        Load options from command line arguments and a config file.

        Load the configuration with L{Configuration.load}, and then set
        C{http_proxy} and C{https_proxy} environment variables based on
        that config data.
        """
        super(BrokerConfiguration, self).load(args)
        if self.http_proxy:
            os.environ["http_proxy"] = self.http_proxy
        elif self._original_http_proxy:
            os.environ["http_proxy"] = self._original_http_proxy

        if self.https_proxy:
            os.environ["https_proxy"] = self.https_proxy
        elif self._original_https_proxy:
            os.environ["https_proxy"] = self._original_https_proxy
