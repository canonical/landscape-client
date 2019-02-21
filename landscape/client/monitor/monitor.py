"""The Landscape monitor plugin system."""

import os

from landscape.client.broker.client import BrokerClient


class Monitor(BrokerClient):
    """The central point of integration in the Landscape monitor."""

    name = "monitor"

    def __init__(self, reactor, config, persist, persist_filename=None,
                 step_size=5 * 60):
        super(Monitor, self).__init__(reactor, config)
        self.reactor = reactor
        self.config = config
        self.persist = persist
        self.persist_filename = persist_filename
        if persist_filename and os.path.exists(persist_filename):
            self.persist.load(persist_filename)
        self._plugins = []
        self.step_size = step_size
        self.reactor.call_every(self.config.flush_interval, self.flush)

    def flush(self):
        """Flush data to disk."""
        if self.persist_filename:
            self.persist.save(self.persist_filename)

    def exchange(self):
        """Call C{exchange} on all plugins."""
        super(Monitor, self).exchange()
        self.flush()
