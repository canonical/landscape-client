"""
Extend the regular Twisted reactor with event-handling features.
"""
from landscape.lib.reactor import EventHandlingReactor
from landscape.client.lockfile import patch_lockfile

patch_lockfile()


class LandscapeReactor(EventHandlingReactor):
    """Wrap and add functionalities to the Twisted reactor.

    This is essentially a facade around the twisted.internet.reactor and
    will delegate to it for mostly everything except event handling features
    which are implemented using L{EventHandlingReactorMixin}.
    """
