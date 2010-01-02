from landscape.broker.client import BrokerClientPlugin


class MonitorPlugin(BrokerClientPlugin):
    """
    @cvar persist_name: If specified as a string, a C{_persist} attribute
    will be available after registration.
    """

    persist_name = None

    def register(self, monitor):
        super(MonitorPlugin, self).register(monitor)
        self.monitor = self.client
        if self.persist_name is not None:
            self._persist = self.monitor.persist.root_at(self.persist_name)

    def call_on_accepted(self, type, callable, *args, **kwargs):
        """
        Register a callback fired upon a C{message-type-acceptance-changed}.
        """

        def acceptance_changed(acceptance):
            if acceptance:
                return callable(*args, **kwargs)

        self.monitor.reactor.call_on(("message-type-acceptance-changed",
                                       type), acceptance_changed)
