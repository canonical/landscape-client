import os

from twisted.internet.defer import Deferred

from landscape.manager.haservice import HAService
from landscape.manager.plugin import SUCCEEDED, FAILED

from landscape.lib.twisted_util import gather_results
from landscape.tests.helpers import LandscapeTest, ManagerHelper
from landscape.package.reporter import find_reporter_command


class HAServiceTests(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super(HAServiceTests, self).setUp()
        self.ha_service = HAService()
        self.ha_service.JUJU_UNITS_BASE = self.makeDir()

        self.unit_name = "my-service-9"
         
        self.health_check_d = os.path.join(
            self.ha_service.JUJU_UNITS_BASE, self.unit_name,
             self.ha_service.HEALTH_SCRIPTS_DIR)
        os.mkdir(os.path.join(self.ha_service.JUJU_UNITS_BASE, self.unit_name))
        os.mkdir(self.health_check_d)

        self.manager.add(self.ha_service)

        cluster_online = file(
            "%s/add_to_cluster" % self.ha_service.JUJU_UNITS_BASE, "w")
        cluster_online.write("#!/bin/bash\nexit 0")
        cluster_online.close()
        cluster_standby = file(
            "%s/remove_from_cluster" % self.ha_service.JUJU_UNITS_BASE, "w")
        cluster_standby.write("#!/bin/bash\nexit 0")
        cluster_standby.close()

        os.chmod(
            "%s/add_to_cluster" % self.ha_service.JUJU_UNITS_BASE, 0755)
        os.chmod(
            "%s/remove_from_cluster" % self.ha_service.JUJU_UNITS_BASE, 0755)

        service = self.broker_service
        service.message_store.set_accepted_types(["operation-result"])

#        self.sourceslist._run_process = lambda cmd, args, *aarg, **kargs: None

    def test_invalid_server_service_state_request(self):
        """
        When the landscape server requests a C{service-state} other than
        'online' or 'standby' the client responds with the appropriate error.
        """
        logging_mock = self.mocker.replace("logging.error")
        logging_mock("Invalid cluster participation state requested BOGUS.")
        self.mocker.replay()

        self.manager.dispatch_message(
            {"type": "change-ha-service", "service-name": "my-service",
             "unit-name": self.unit_name, "service-state": "BOGUS",
             "operation-id": 1})

        service = self.broker_service
        self.assertMessages(
            service.message_store.get_pending_messages(),
            [{"type": "operation-result", "result-text":
              u"This computer is not JUJU unit some-other-service-0. "
              u"Unable to modify high-availability services.",
              "status": FAILED, "operation-id": 1}])

    def test_not_a_juju_computer(self):
        """
        When not a JUJU charmed computer, L{HAService} reponds with an error
        due to missing JUJU_UNITS_BASE dir.
        """
        self.ha_service.JUJU_UNITS_BASE = "/I/dont/exist"

        logging_mock = self.mocker.replace("logging.error")
        logging_mock("This computer is not deployed with JUJU. "
                     "Changing high-availability service not supported.")
        self.mocker.replay()

        self.manager.dispatch_message(
            {"type": "change-ha-service", "service-name": "my-service",
             "unit-name": self.unit_name, "service-state": "standby",
             "operation-id": 1})

        service = self.broker_service
        self.assertMessages(
            service.message_store.get_pending_messages(),
            [{"type": "operation-result", "result-text":
              u"This computer is not deployed with JUJU. Changing "
              u"high-availability service not supported.",
              "status": FAILED, "operation-id": 1}])

    def test_incorrect_juju_unit(self):
        """
        When not the specific JUJU charmed computer, L{HAService} reponds
        with an error due to missing the JUJU_UNITS_BASE/$JUJU_UNIT dir.
        """
        logging_mock = self.mocker.replace("logging.error")
        logging_mock("This computer is not JUJU unit some-other-service-0. "
                     "Unable to modify high-availability services.")
        self.mocker.replay()

        self.manager.dispatch_message(
            {"type": "change-ha-service", "service-name": "some-other-service",
             "unit-name": "some-other-service-0", "service-state": "standby",
             "operation-id": 1})

        service = self.broker_service
        self.assertMessages(
            service.message_store.get_pending_messages(),
            [{"type": "operation-result", "result-text":
              u"This computer is not JUJU unit some-other-service-0. "
              u"Unable to modify high-availability services.",
              "status": FAILED, "operation-id": 1}])

    def test_no_health_check_directory(self):
        """
        When unable to find a valid C{HEALTH_CHECK_DIR}, L{HAService} will
        succeed but log an informational message.
        """
        logging_mock = self.mocker.replace("logging.info")
        logging_mock("Something logged")
        self.mocker.replay()

    def test_no_health_check_scripts(self):
        """
        When C{HEALTH_CHECK_DIR} exists but, no scripts exist, L{HAService}
        will log an informational message, but succeed.
        """
        logging_mock = self.mocker.replace("logging.info")
        logging_mock("Something logged")
        self.mocker.replay()

    def test_failed_health_script(self):
        pass

    def test_failed_remove_from_cluster_script(self):
        pass

    def test_missing_remove_from_cluster_script(self):
        pass

    def test_failed_add_to_cluster_script(self):
        pass

    def test_missing_add_to_cluster_script(self):
        pass

    def test_run_success(self):
        pass
