from landscape.lib.persist import Persist
from landscape.broker.tests.helpers import BrokerServiceHelper
from landscape.monitor.config import MonitorConfiguration
from landscape.monitor.monitor import Monitor


class MonitorHelper(BrokerServiceHelper):
    """
    Provides everything that L{BrokerServiceHelper} does plus a
    L{Monitor} instance.
    """

    def set_up(self, test_case):

        def set_monitor(ignored):
            persist = Persist()
            persist_filename = test_case.makePersistFile()
            test_case.config = MonitorConfiguration()
            test_case.config.load(["-c", test_case.config_filename])
            test_case.reactor = test_case.broker_service.reactor
            test_case.monitor = Monitor(
                test_case.remote, test_case.reactor, test_case.config,
                persist, persist_filename)

        broker_started = super(MonitorHelper, self).set_up(test_case)
        return broker_started.addCallback(set_monitor)
