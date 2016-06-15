import os

from mock import patch, ANY, Mock

from twisted.internet.defer import Deferred, succeed

from landscape.manager.haservice import HAService
from landscape.manager.plugin import SUCCEEDED, FAILED
from landscape.tests.helpers import LandscapeTest, ManagerHelper
from landscape.tests.mocker import ANY


class HAServiceTests(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super(HAServiceTests, self).setUp()
        self.ha_service = HAService()
        self.ha_service.JUJU_UNITS_BASE = self.makeDir()

        self.unit_name = "my-service/9"
        self.unit_path = "unit-" + self.unit_name.replace("/", "-")

        self.scripts_dir = os.path.join(
            self.ha_service.JUJU_UNITS_BASE, self.unit_path, "charm/scripts")
        self.health_check_d = os.path.join(
            self.scripts_dir, self.ha_service.HEALTH_SCRIPTS_DIR)
        # create entire dir path
        os.makedirs(self.health_check_d)

        self.manager.add(self.ha_service)

        cluster_online = self.makeFile(
            content="#!/bin/bash\nexit 0",
            basename="add_to_cluster", dirname=self.scripts_dir)
        os.chmod(cluster_online, 0755)
        cluster_standby = self.makeFile(
            content="#!/bin/bash\nexit 0",
            basename="remove_from_cluster", dirname=self.scripts_dir)
        os.chmod(cluster_standby, 0755)

        service = self.broker_service
        service.message_store.set_accepted_types(["operation-result"])

    @patch("logging.error",
           return_value="Invalid cluster participation state requested BOGUS.")
    def test_invalid_server_service_state_request(self, logging_mock):
        """
        When the landscape server requests a C{service-state} other than
        'online' or 'standby' the client responds with the appropriate error.
        """
        self.manager.dispatch_message(
            {"type": "change-ha-service", "service-name": "my-service",
             "unit-name": self.unit_name, "service-state": "BOGUS",
             "operation-id": 1})

        service = self.broker_service
        self.assertMessages(
            service.message_store.get_pending_messages(),
            [{"type": "operation-result", "result-text":
              u"Invalid cluster participation state requested BOGUS.",
              "status": FAILED, "operation-id": 1}])

    @patch("logging.error",
           return_value=("This computer is not deployed with juju. "
                         "Changing high-availability service not supported."))
    def test_not_a_juju_computer(self, loggin_mock):
        """
        When not a juju charmed computer, L{HAService} reponds with an error
        due to missing JUJU_UNITS_BASE dir.
        """
        self.ha_service.JUJU_UNITS_BASE = "/I/don't/exist"

        self.manager.dispatch_message(
            {"type": "change-ha-service", "service-name": "my-service",
             "unit-name": self.unit_name,
             "service-state": self.ha_service.STATE_STANDBY,
             "operation-id": 1})

        service = self.broker_service
        self.assertMessages(
            service.message_store.get_pending_messages(),
            [{"type": "operation-result", "result-text":
              u"This computer is not deployed with juju. Changing "
              u"high-availability service not supported.",
              "status": FAILED, "operation-id": 1}])

    @patch("logging.error",
           return_value=("This computer is not juju unit some-other-service-0."
                         " Unable to modify high-availability services."))
    def test_incorrect_juju_unit(self, logging_mock):
        """
        When not the specific juju charmed computer, L{HAService} reponds
        with an error due to missing the JUJU_UNITS_BASE/$JUJU_UNIT dir.
        """
        self.manager.dispatch_message(
            {"type": "change-ha-service", "service-name": "some-other-service",
             "unit-name": "some-other-service-0", "service-state": "standby",
             "operation-id": 1})

        service = self.broker_service
        self.assertMessages(
            service.message_store.get_pending_messages(),
            [{"type": "operation-result", "result-text":
              u"This computer is not juju unit some-other-service-0. "
              u"Unable to modify high-availability services.",
              "status": FAILED, "operation-id": 1}])

    def test_wb_no_health_check_directory(self):
        """
        When unable to find a valid C{HEALTH_CHECK_DIR}, L{HAService} will
        succeed but log an informational message.
        """
        self.ha_service.HEALTH_SCRIPTS_DIR = "I/don't/exist"

        def should_not_be_called(result):
            self.fail(
                "_run_health_checks failed on absent health check directory.")

        def check_success_result(result):
            self.assertEqual(
                result,
                "Skipping juju charm health checks. No scripts at "
                "%s/I/don't/exist." % self.scripts_dir)

        result = self.ha_service._run_health_checks(self.scripts_dir)
        result.addCallbacks(check_success_result, should_not_be_called)

    def test_wb_no_health_check_scripts(self):
        """
        When C{HEALTH_CHECK_DIR} exists but, no scripts exist, L{HAService}
        will log an informational message, but succeed.
        """
        # In setup we created a health check directory but placed no health
        # scripts in it.
        def should_not_be_called(result):
            self.fail(
                "_run_health_checks failed on empty health check directory.")

        def check_success_result(result):
            self.assertEqual(
                result,
                "Skipping juju charm health checks. No scripts at "
                "%s/%s." %
                (self.scripts_dir, self.ha_service.HEALTH_SCRIPTS_DIR))

        result = self.ha_service._run_health_checks(self.scripts_dir)
        result.addCallbacks(check_success_result, should_not_be_called)

    def test_wb_failed_health_script(self):
        """
        L{HAService} runs all health check scripts found in the
        C{HEALTH_CHECK_DIR}. If any script fails, L{HAService} will return a
        deferred L{fail}.
        """

        def expected_failure(result):
            self.assertEqual(
                str(result.value),
                "Failed charm script: %s/%s/my-health-script-2 "
                "exited with return code 1." %
                (self.scripts_dir, self.ha_service.HEALTH_SCRIPTS_DIR))

        def check_success_result(result):
            self.fail(
                "_run_health_checks succeded despite a failed health script.")

        for number in [1, 2, 3]:
            script_path = (
                "%s/my-health-script-%d" % (self.health_check_d, number))
            health_script = file(script_path, "w")
            if number == 2:
                health_script.write("#!/bin/bash\nexit 1")
            else:
                health_script.write("#!/bin/bash\nexit 0")
            health_script.close()
            os.chmod(script_path, 0755)

        result = self.ha_service._run_health_checks(self.scripts_dir)
        result.addCallbacks(check_success_result, expected_failure)
        return result

    def test_missing_cluster_standby_or_cluster_online_scripts(self):
        """
        When no cluster status change scripts are delivered by the charm,
        L{HAService} will still return a L{succeeded}.
        C{HEALTH_CHECK_DIR}. If any script fails, L{HAService} will return a
        deferred L{fail}.
        """

        def should_not_be_called(result):
            self.fail(
                "_change_cluster_participation failed on absent charm script.")

        def check_success_result(result):
            self.assertEqual(
                result,
                "This computer is always a participant in its high-availabilty"
                " cluster. No juju charm cluster settings changed.")

        self.ha_service.CLUSTER_ONLINE = "I/don't/exist"
        self.ha_service.CLUSTER_STANDBY = "I/don't/exist"

        result = self.ha_service._change_cluster_participation(
            None, self.scripts_dir, self.ha_service.STATE_ONLINE)
        result.addCallbacks(check_success_result, should_not_be_called)

        # Now test the cluster standby script
        result = self.ha_service._change_cluster_participation(
            None, self.scripts_dir, self.ha_service.STATE_STANDBY)
        result.addCallbacks(check_success_result, should_not_be_called)
        return result

    def test_failed_cluster_standby_or_cluster_online_scripts(self):
        def expected_failure(result, script_path):
            self.assertEqual(
                str(result.value),
                "Failed charm script: %s exited with return code 2." %
                (script_path))

        def check_success_result(result):
            self.fail(
                "_change_cluster_participation ignored charm script failure.")

        # Rewrite both cluster scripts as failures
        for script_name in [
            self.ha_service.CLUSTER_ONLINE, self.ha_service.CLUSTER_STANDBY]:

            cluster_online = file(
                "%s/%s" % (self.scripts_dir, script_name), "w")
            cluster_online.write("#!/bin/bash\nexit 2")
            cluster_online.close()

        result = self.ha_service._change_cluster_participation(
            None, self.scripts_dir, self.ha_service.STATE_ONLINE)
        result.addCallback(check_success_result)
        script_path = (
            "%s/%s" % (self.scripts_dir, self.ha_service.CLUSTER_ONLINE))
        result.addErrback(expected_failure, script_path)

        # Now test the cluster standby script
        result = self.ha_service._change_cluster_participation(
            None, self.scripts_dir, self.ha_service.STATE_STANDBY)
        result.addCallback(check_success_result)
        script_path = (
            "%s/%s" % (self.scripts_dir, self.ha_service.CLUSTER_STANDBY))
        result.addErrback(expected_failure, script_path)
        return result

    def test_run_success_cluster_standby(self):
        """
        When receives a C{change-ha-service message} with C{STATE_STANDBY}
        requested the manager runs the C{CLUSTER_STANDBY} script and returns
        a successful operation-result to the server.
        """
        message = ({"type": "change-ha-service", "service-name": "my-service",
                    "unit-name": self.unit_name,
                    "service-state": self.ha_service.STATE_STANDBY,
                    "operation-id": 1})

        real_respond_success = self.ha_service._respond_success

        def validate_message(data, message, operation_id):
            cluster_script = "%s/%s" % (
                self.scripts_dir, self.ha_service.CLUSTER_STANDBY)

            result = real_respond_success(data, message, operation_id)
            service = self.broker_service
            messages = service.message_store.get_pending_messages()
            self.assertMessages(
                messages,
                [{"type": "operation-result",
                  "result-text": u"%s succeeded." % cluster_script,
                  "status": SUCCEEDED, "operation-id": 1}])
            return result
        
        self.ha_service._respond_success = Mock(side_effect=validate_message)

        self.manager.add(self.ha_service)
        handler = self.manager.dispatch_message(message)

        # Just to be sure we're really running the assertion
        self.ha_service._respond_success.has_call(ANY)        
        return handler

    def test_run_success_cluster_online(self):
        """
        When receives a C{change-ha-service message} with C{STATE_ONLINE}
        requested the manager runs the C{CLUSTER_ONLINE} script and returns
        a successful operation-result to the server.
        """
        message = ({"type": "change-ha-service", "service-name": "my-service",
                    "unit-name": self.unit_name,
                    "service-state": self.ha_service.STATE_ONLINE,
                    "operation-id": 1})


        real_respond_success = self.ha_service._respond_success

        def validate_message(data, message, operation_id):
            cluster_script = "%s/%s" % (
                self.scripts_dir, self.ha_service.CLUSTER_ONLINE)

            result = real_respond_success(data, message, operation_id)
            service = self.broker_service
            messages = service.message_store.get_pending_messages()
            self.assertMessages(
                messages,
                [{"type": "operation-result",
                  "result-text": u"%s succeeded." % cluster_script,
                  "status": SUCCEEDED, "operation-id": 1}])
            return result
        
        self.ha_service._respond_success = Mock(side_effect=validate_message)

        self.manager.add(self.ha_service)
        handler = self.manager.dispatch_message(message)

        # Just to be sure we're really running the assertion
        self.ha_service._respond_success.has_call(ANY)        
        return handler
