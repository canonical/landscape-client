from landscape.broker.tests.helpers import BrokerServiceHelper
from landscape.manager.config import ManagerConfiguration
from landscape.manager.manager import Manager


class ManagerHelper(BrokerServiceHelper):
    """
    Provides everything that L{BrokerServiceHelper} does plus a
    L{Manager} instance.
    """

    def set_up(self, test_case):

        def set_manager(ignored):
            test_case.config = ManagerConfiguration()
            test_case.config.load(["-c", test_case.config_filename])
            test_case.reactor = test_case.broker_service.reactor
            test_case.manager = Manager(
                test_case.remote, test_case.reactor, test_case.config)

        broker_started = super(ManagerHelper, self).set_up(test_case)
        return broker_started.addCallback(set_manager)
