import logging
import os

from twisted.internet.utils import getProcessValue
from twisted.internet.defer import succeed, fail

from landscape.manager.plugin import ManagerPlugin, SUCCEEDED, FAILED


class HAService(ManagerPlugin):
    """
    Plugin to manage this computer's active participation in a
    high-availability cluster. It depends on charms delivering both health
    scripts and cluster_add cluster_remove scripts to function.
    """

    JUJU_UNITS_BASE = "/var/lib/juju/units"
    CLUSTER_ONLINE = "add_to_cluster"
    CLUSTER_STANDBY = "remove_from_cluster"
    HEALTH_SCRIPTS_DIR = "health_checks.d"
    STATE_STANDBY = u"standby"
    STATE_ONLINE = u"online"

    def register(self, registry):
        super(HAService, self).register(registry)
        registry.register_message("change-ha-service",
                                  self._handle_change_ha_service)

    def _respond(self, status, data, opid):
        message = {"type": "operation-result",
                   "status": status,
                   "operation-id": opid}
        if data and not isinstance(data, unicode):
            # Let's decode result-text, replacing non-printable
            # characters
            message["result-text"] = data.decode("utf-8", "replace")
        return self.registry.broker.send_message(message, True)

    def _validate_exit_code(self, code, script):
        """Validates each script return code as success"""
        if code != 0:
            return fail("Failed charm script: %s" % script)

    def _respond_success(self, data, message, opid):
        logging.info(message)
        return self._respond(SUCCEEDED, data, opid)

    def _respond_failure(self, failure, opid):
        if hasattr(failure, "value"):
            failure = "%s" % (failure.value)
        logging.error(failure)
        return self._respond(FAILED, str(failure), opid)

    def _format_exception(self, e):
        return u"%s: %s" % (e.__class__.__name__, e.args[0])

    def _run_health_checks(self, unit_name):
        """
        Exercise any discovered health check scripts, return True on success.
        """
        health_dir = self.HEALTH_SCRIPTS_DIR % unit_name
        if not os.path.exists(health_dir) or len(os.listdir(health_dir)) == 0:
            # No scripts, no problem
            message = (
                "Skipping juju charm health checks. No scripts at %s." %
                health_dir)
            return succeed(message)

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
        unit_dir = "%s/%s/" % (self.JUJU_UNITS_BASE, unit_name)
        if service_state == u"online":
            script = unit_dir + self.CLUSTER_ONLINE
        else:
            script = unit_dir + self.CLUSTER_STANDBY

        if not os.path.exists(script):
            logging.info("Ignoring juju charm cluster state change to '%s'. "
                         "Charm script does not exist at %s." %
                         (service_state, script))
            return succeed(
                "Computer is a default participant in high-availabilty "
                "cluster. No juju charm cluster settings changed.")
        d = getProcessValue(script)
        d.addCallback(self._validate_exit_code, script)
        return d

    def _perform_state_change(self, unit_name, service_state, opid):
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
            d = self._run_health_checks(unit_name)
        d.addCallback(
            self._change_cluster_participation, unit_name, service_state)
        return d

    def _handle_change_ha_service(self, message):
        """Parse incoming change-ha-service messages"""
        opid = message["operation-id"]
        try:
            error_message = u""

            service_name = message["service-name"]   # keystone
            unit_name = message["unit-name"]         # keystone-0
            service_state = message["service-state"]  # "online" | "standby"
            change_message = (
                "%s high-availability service set to %s" %
                (service_name, service_state))

            if service_state not in [self.STATE_STANDBY, self.STATE_ONLINE]:
                error_message = (
                   u"Invalid cluster participation state requested %s." %
                   service_state)

            unit_dir = "%s/%s" % (self.JUJU_UNITS_BASE, unit_name)
            if not os.path.exists(self.JUJU_UNITS_BASE):
                error_message = (
                    u"This computer is not deployed with JUJU. "
                    u"Changing high-availability service not supported.")
            elif not os.path.exists(unit_dir):
                error_message = (
                    u"This computer is not JUJU unit %s. Unable to "
                    u"modify high-availability services." % unit_name)

            if error_message:
                return self._respond_failure(error_message, opid)

            if service_state == self.STATE_ONLINE:
                d = self._run_health_checks(unit_name)
                d.addErrback(self._respond_failure, opid)

            d = self._perform_state_change(unit_name, service_state, opid)
            d.addCallback(self._respond_success, change_message, opid)
            d.addErrback(self._respond_failure, opid)
        except Exception, e:
            self._respond_failure(self._format_exception(e), opid)
