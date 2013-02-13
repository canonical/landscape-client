import logging
import os

from twisted.internet.utils import getProcessValue
from twisted.internet.defer import succeed, fail

from landscape.manager.plugin import ManagerPlugin, SUCCEEDED, FAILED


JUJU_UNITS_DIR = "/var/lib/juju/units"
CLUSTER_ONLINE = "add_to_cluster"
CLUSTER_STANDBY = "remove_from_cluster"
HEALTH_SCRIPTS_DIR = JUJU_UNITS_DIR + "/%s/health_checks.d/"
STATE_STANDBY = u"standby"
STATE_ONLINE = u"online"


class CharmScriptError(Exception):
    """
    Raised when a charm-provided script fails with a non-zero exit code.

    @ivar script: the name of the failed script
    """

    def __init__(self, script):
        self.script = script
        Exception.__init__(self, self._get_message())

    def _get_message(self):
        return "Failed charm script: '%s'" % self.script


class HAService(ManagerPlugin):
    """
    Plugin to manage this computer's active participation in a
    high-availability cluster. It depends on charms delivering both health
    scripts and cluster_add cluster_remove scripts to function.
    """

    def register(self, registry):
        super(HAService, self).register(registry)
        registry.register_message("change-ha-service",
                                  self._handle_change_ha_service)

    def _respond(self, status, data, opid):
        if not isinstance(data, unicode):
            # Let's decode result-text, replacing non-printable
            # characters
            data = data.decode("utf-8", "replace")
        message = {"type": "ha-service-change-result",
                   "status": status,
                   "result-text": data,
                   "operation-id": opid}
        return self.registry.broker.send_message(message, True)

    def _validate_exit_code(self, code, script):
        """Validates each script return code as success"""
        if code != 0:
            return fail(CharmScriptError(script))

    def _respond_success(self, data, opid):
        logging.error("CHAD succeeded %d: %s" % (opid, data))
        return self._respond(SUCCEEDED, data, opid)

    def _respond_failure(self, failure, opid):
        logging.error("CHAD failed sorry %d: %s" % (opid, failure))
        return self._respond(FAILED, str(failure), opid)

    def _format_exception(self, e):
        return u"%s: %s" % (e.__class__.__name__, e.args[0])

    def _run_health_checks(self, unit_name):
        """
        Exercise any discovered health check scripts, return True on success.
        """
        health_dir = HEALTH_SCRIPTS_DIR % unit_name
        if not os.path.exists(health_dir) or len(os.listdir(health_dir)) == 0:
            # No scripts, no problem
            logging.info("Skipping charm health checks. No scripts at %s." %
                         health_dir)
            return succeed(None)

        d = succeed(None)
        for filename in sorted(os.listdir(health_dir)):
            health_script = "%s/%s" % (health_dir, filename)
            d = getProcessValue(health_script)
            d.addBoth(self._validate_exit_code, health_script)
        return d

    def _change_cluster_participation(self, result, unit_name, service_state):
        """
        Enables or disables a unit's participation in a cluster based on
        running charm-delivered CLUSTER_ONLINE and CLUSTER_STANDBY scripts
        if they exist. If the charm doesn't deliver scripts, return succeed().
        """
        if service_state == u"online":
            script = "%s/%s/%s" % (JUJU_UNITS_DIR, unit_name, CLUSTER_ONLINE)
        else:
            script = "%s/%s/%s" % (JUJU_UNITS_DIR, unit_name, CLUSTER_STANDBY)

        if not os.path.exists(script):
            logging.info("Ignoring charm cluster state change: %s. "
                         "Charm scripts do not exist." % service_state)
            return succeed(None)
        return getProcessValue(script)

    def _perform_state_change(self, unit_name, service_state, opid):
        """
        Handle specific state change requests through calls to available
        charm scripts like C{CLUSTER_ONLINE}, C{CLUSTER_STANDBY} and any
        health check scripts. Assume success in any case where no scripts
        exist for a given task.
        """
        d = succeed(None)
        self.failed_scripts = []
        if service_state == STATE_ONLINE:
            # Validate health of local service before we bring it online
            # in the HAcluster
            d = self._run_health_checks(unit_name)
        d.addCallback(
            self._change_cluster_participation, unit_name, service_state)
        d.addErrback(self._respond_failure, opid)
        return d

    def _handle_change_ha_service(self, message):
        """Parse incoming change-ha-service messages"""
        self._respond_success("CHAD here", 113)
        return
        opid = message["operation-id"]
        try:
            message = u""

            service_name = message["service-name"]   # keystone
            unit_name = message["unit-name"]         # keystone-0
            service_state = message["service-state"]  # "online" | "standby"
            if service_state not in [u"online", u"standby"]:
                message = (
                   u"Invalid cluster participation state requested %s." %
                   service_state)

            if not os.path.exists(JUJU_UNITS_DIR):
                message = (u"This computer is not deployed with JUJU. Setting "
                           u"high-availability services not supported.")
            if not os.path.exists("%s/%s" % (JUJU_UNITS_DIR, unit_name)):
                message = (u"This computer is not JUJU unit %s. Unable to "
                           u"modify high-availability services." % unit_name)
            if not os.path.exists(HEALTH_SCRIPTS_DIR % unit_name):
                logging.info(u"JUJU charm %s doesn't implement health check "
                             u"scripts. Assuming service is healthy." %
                             service_name)

            if message:
                logging.warning(message)
                return self._respond_failure(message, opid)

            if service_state == STATE_ONLINE:
                d = self._run_health_checks(unit_name)
                d.addErrback(self._respond_failure, opid)

            d = self._perform_state_change(unit_name, service_state)
            d.addCallback(self._respond_success, opid)
            d.addErrback(self._respond_failure, opid)
        except Exception, e:
            self._respond(FAILED, self._format_exception(e), opid)
            raise
