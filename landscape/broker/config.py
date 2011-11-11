"""Configuration class for the broker."""

import os

from landscape.deployment import Configuration


class BrokerConfiguration(Configuration):
    """Specialized configuration for the Landscape Broker.

    @cvar required_options: C{["url"]}
    """

    required_options = ["url"]

    def __init__(self):
        super(BrokerConfiguration, self).__init__()
        self._original_http_proxy = os.environ.get("http_proxy")
        self._original_https_proxy = os.environ.get("https_proxy")

    @property
    def exchange_store_path(self):
        return os.path.join(self.data_path, "exchange.database")

    @property
    def record_directory(self):
        return os.path.join(self.data_path, "exchanges")

    def make_parser(self):
        """Parser factory for broker-specific options.

        @return: An L{OptionParser} preset for all the options
            from L{Configuration.make_parser} plus:
              - C{account_name}
              - C{registration_password}
              - C{computer_title}
              - C{url}
              - C{ssl_public_key}
              - C{exchange_interval} (C{15*60})
              - C{urgent_exchange_interval} (C{1*60})
              - C{ping_url}
              - C{http_proxy}
              - C{https_proxy}
              - C{cloud}
              - C{otp}
              - C{record}
        """
        parser = super(BrokerConfiguration, self).make_parser()

        parser.add_option("-a", "--account-name", metavar="NAME",
                          help="The account this computer belongs to.")
        parser.add_option("-p", "--registration-password", metavar="PASSWORD",
                          help="The account-wide password used for "
                               "registering clients.")
        parser.add_option("-t", "--computer-title", metavar="TITLE",
                          help="The title of this computer")
        parser.add_option("-u", "--url",
                          help="The server URL to connect to.")
        parser.add_option("-k", "--ssl-public-key",
                          help="The public SSL key to verify the server. "
                               "Only used if the given URL is https.")
        parser.add_option("--exchange-interval", default=15 * 60, type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between server "
                               "exchanges.")
        parser.add_option("--urgent-exchange-interval", default=1 * 60,
                          type="int", metavar="INTERVAL",
                          help="The number of seconds between urgent server "
                               "exchanges.")
        parser.add_option("--ping-url",
                          help="The URL to perform lightweight exchange "
                               "initiation with.")
        parser.add_option("--ping-interval", default=30, type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between pings.")
        parser.add_option("--http-proxy", metavar="URL",
                          help="The URL of the HTTP proxy, if one is needed.")
        parser.add_option("--https-proxy", metavar="URL",
                          help="The URL of the HTTPS proxy, if one is needed.")
        parser.add_option("--cloud", action="store_true",
                          help="Set this if your computer is in an EC2 cloud.")
        parser.add_option("--otp", default="",
                          help="The OTP to use in cloud configuration.")
        parser.add_option("--tags",
                          help="Comma separated list of tag names to be sent "
                               "to the server.")
        parser.add_option("--record", action="store_true",
                          help="Record data sent to the server on filesystem.")
        parser.add_option("--provisioning-otp", default="",
                          help="The OTP to use for a provisioned machine.")
        return parser

    @property
    def message_store_path(self):
        """Get the path to the message store."""
        return os.path.join(self.data_path, "messages")

    def load(self, args, accept_nonexistent_config=False):
        """
        Load options from command line arguments and a config file.

        Load the configuration with L{Configuration.load}, and then set
        C{http_proxy} and C{https_proxy} environment variables based on
        that config data.
        """
        super(BrokerConfiguration, self).load(
            args, accept_nonexistent_config=accept_nonexistent_config)
        if self.http_proxy:
            os.environ["http_proxy"] = self.http_proxy
        elif self._original_http_proxy:
            os.environ["http_proxy"] = self._original_http_proxy

        if self.https_proxy:
            os.environ["https_proxy"] = self.https_proxy
        elif self._original_https_proxy:
            os.environ["https_proxy"] = self._original_https_proxy
