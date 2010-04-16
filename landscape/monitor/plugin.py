from landscape.broker.client import BrokerClientPlugin


class MonitorPlugin(BrokerClientPlugin):
    """
    @cvar persist_name: If specified as a string, a C{_persist} attribute
    will be available after registration.
    """

    persist_name = None

    def register(self, monitor):
        super(MonitorPlugin, self).register(monitor)
        if self.persist_name is not None:
            self._persist = self.monitor.persist.root_at(self.persist_name)
        else:
            self._persist = None

    @property
    def persist(self):
        """Return our L{Persist}, if any."""
        return self._persist

    @property
    def monitor(self):
        """An alias for the C{client} attribute."""
        return self.client

    def call_on_accepted(self, type, callable, *args, **kwargs):
        """
        Register a callback fired upon a C{message-type-acceptance-changed}.
        """

        def acceptance_changed(acceptance):
            if acceptance:
                return callable(*args, **kwargs)

        self.monitor.reactor.call_on(("message-type-acceptance-changed",
                                       type), acceptance_changed)
