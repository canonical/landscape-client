import logging
import sys

from landscape.client.broker.config import BrokerConfiguration
from landscape.client.monitor.plugin import DataWatcher
from landscape.lib.tag import is_valid_tag_list


class ComputerTags(DataWatcher):

    persist_name = "computer-tags"
    message_type = "computer-tags"
    message_key = "tags"
    run_interval = 3600  # Every hour only when data changed
    run_immediately = True

    def get_data(self):
        config = BrokerConfiguration()
        config.load(sys.argv)  # Load the default or specified config
        tags = config.tags
        if not is_valid_tag_list(tags):
            tags = None
            logging.warning("Invalid tags provided for computer-tags message.")
        return tags
