class RemoteClient(object):
    """A connected client utilizing features provided by a L{BrokerServer}."""

    def __init__(self, name):
        """
        @param name: Name of the broker client.
        """
        self.name = name
