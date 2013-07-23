import logging
import os

from twisted.python.failure import Failure
from twisted.internet.utils import getProcessValue, getProcessOutputAndValue
from twisted.internet.defer import succeed

from landscape.lib.log import log_failure
from landscape.manager.plugin import ManagerPlugin, SUCCEEDED, FAILED


class CharmScriptError(Exception):
    """
    Raised when a charm-provided script fails with a non-zero exit code.

    @ivar script: the name of the failed script
    @ivar code: the exit code of the failed script
    """

    def __init__(self, script, code):
        self.script = script
        self.code = code
        Exception.__init__(self, self._get_message())

    def _get_message(self):
        return ("Failed charm script: %s exited with return code %d." %
                (self.script, self.code))


class RunPartsError(Exception):
    """
    Raised when a charm-provided health script run-parts directory contains
    a health script that fails with a non-zero exit code.

    @ivar stderr: the stderr from the failed run-parts command
    """

    def __init__(self, stderr):
        self.message = ("%s" % stderr.split(":")[1].strip())
        Exception.__init__(self, self._get_message())

    def _get_message(self):
        return "Failed charm script: %s." % self.message


class HAService(ManagerPlugin):
    """
    Plugin to manage this computer's active participation in a
    high-availability cluster. It depends on charms delivering both health
    scripts and cluster_add cluster_remove scripts to function.
    """

    JUJU_UNITS_BASE = "/var/lib/juju/agents"
    CLUSTER_ONLINE = "add_to_cluster"
    CLUSTER_STANDBY = "remove_from_cluster"
    HEALTH_SCRIPTS_DIR = "health_checks.d"
    STATE_STANDBY = u"standby"
    STATE_ONLINE = u"online"

    def register(self, registry):
        super(HAService, self).register(registry)
        registry.register_message("change-ha-service",
                                  self.handle_change_ha_service)

    def _respond(self, status, data, operation_id):
        message = {"type": "operation-result",
                   "status": status,
                   "operation-id": operation_id}
        if data:
            message["result-text"] = data.decode("utf-8", "replace")
        return self.registry.broker.send_message(
            message, self._session_id, True)

    def _respond_success(self, data, message, operation_id):
        logging.info(message)
        return self._respond(SUCCEEDED, data, operation_id)

    def _respond_failure(self, failure, operation_id):
        """Handle exception failures."""
        log_failure(failure)
        return self._respond(FAILED, failure.getErrorMessage(), operation_id)

    def _respond_failure_string(self, failure_string, operation_id):
        """Only handle string failures."""
        logging.error(failure_string)
        return self._respond(FAILED, failure_string, operation_id)

    def _run_health_checks(self, scripts_path):
        """
        Exercise any discovered health check scripts, will return a deferred
        success or fail.
        """
        health_dir = os.path.join(scripts_path, self.HEALTH_SCRIPTS_DIR)
        if not os.path.exists(health_dir) or not os.listdir(health_dir):
            # No scripts, no problem
            message = (
                "Skipping juju charm health checks. No scripts at %s." %
                health_dir)
            logging.info(message)
            return succeed(message)

        def parse_output((stdout_data, stderr_data, status)):
            if status != 0:
                raise RunPartsError(stderr_data)
            else:
                return "All health checks succeeded."

        result = getProcessOutputAndValue(
            "run-parts", [health_dir], env=os.environ)
        return result.addCallback(parse_output)

    def _change_cluster_participation(self, _, scripts_path, service_state):
        """
        Enables or disables a unit's participation in a cluster based on
        running charm-delivered CLUSTER_ONLINE and CLUSTER_STANDBY scripts
        if they exist. If the charm doesn't deliver scripts, return succeed().
        """
        if service_state == u"online":
            script_name = self.CLUSTER_ONLINE
        else:
            script_name = self.CLUSTER_STANDBY

        script = os.path.join(scripts_path, script_name)

        if not os.path.exists(script):
            logging.info("Ignoring juju charm cluster state change to '%s'. "
                         "Charm script does not exist at %s." %
                         (service_state, script))
            return succeed(
                "This computer is always a participant in its high-availabilty"
                " cluster. No juju charm cluster settings changed.")

        def run_script(script):
            result = getProcessValue(script, env=os.environ)

            def validate_exit_code(code, script):
                if code != 0:
                    raise CharmScriptError(script, code)
                else:
                    return "%s succeeded." % script
            return result.addCallback(validate_exit_code, script)

        return run_script(script)

    def _perform_state_change(self, scripts_path, service_state, operation_id):
        """
        Handle specific state change requests through calls to available
        charm scripts like C{CLUSTER_ONLINE}, C{CLUSTER_STANDBY} and any
        health check scripts. Assume success in any case where no scripts
        exist for a given task.
        """
        d = succeed(None)
        if service_state == self.STATE_ONLINE:
            # Validate health of local service before we bring it online
            # in the HAcluster
            d = self._run_health_checks(scripts_path)
        d.addCallback(
            self._change_cluster_participation, scripts_path, service_state)
        return d

    def handle_change_ha_service(self, message):
        """Parse incoming change-ha-service messages"""
        operation_id = message["operation-id"]
        try:
            error_message = u""

            service_name = message["service-name"]   # keystone
            unit_name = message["unit-name"]         # keystone/0
            service_state = message["service-state"]  # "online" | "standby"
            change_message = (
                "%s high-availability service set to %s" %
                (service_name, service_state))

            if service_state not in [self.STATE_STANDBY, self.STATE_ONLINE]:
                error_message = (
                    u"Invalid cluster participation state requested %s." %
                    service_state)

            unit_path = "unit-" + unit_name.replace("/", "-")
            charm_path = os.path.join(self.JUJU_UNITS_BASE, unit_path, "charm")
            if not os.path.exists(self.JUJU_UNITS_BASE):
                error_message = (
                    u"This computer is not deployed with juju. "
                    u"Changing high-availability service not supported.")
            elif not os.path.exists(charm_path):
                error_message = (
                    u"This computer is not juju unit %s. Unable to "
                    u"modify high-availability services." % unit_name)

            if error_message:
                return self._respond_failure_string(
                    error_message, operation_id)

            scripts_path = os.path.join(charm_path, "scripts")
            d = self._perform_state_change(
                scripts_path, service_state, operation_id)
            d.addCallback(self._respond_success, change_message, operation_id)
            d.addErrback(self._respond_failure, operation_id)
            return d
        except:
            self._respond_failure(Failure(), operation_id)
            return d
