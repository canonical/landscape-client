import time

from landscape.client.reactor import LandscapeReactor
from landscape.lib.tests.test_reactor import ReactorTestMixin
from landscape.client.tests.helpers import LandscapeTest


class LandscapeReactorTest(LandscapeTest, ReactorTestMixin):

    def get_reactor(self):
        reactor = LandscapeReactor()
        # It's not possible to stop the reactor in a Trial test, calling
        # reactor.crash instead
        saved_stop = reactor._reactor.stop
        reactor._reactor.stop = reactor._reactor.crash
        self.addCleanup(lambda: setattr(reactor._reactor, "stop", saved_stop))
        return reactor

    def test_real_time(self):
        reactor = self.get_reactor()
        self.assertTrue(reactor.time() - time.time() < 3)
