import os

from twisted.internet.defer import maybeDeferred

from landscape.lib.log import log_failure
from landscape.lib.amp import RemoteObject
from landscape.amp import (
    ComponentProtocol, ComponentProtocolFactory, RemoteComponentConnector)

from landscape.monitor.monitor import MonitorPlugin
from landscape.user.changes import UserChanges
from landscape.user.provider import UserProvider


class UserMonitor(MonitorPlugin):
    """
    A plugin which monitors the system user databases.
    """

    persist_name = "users"
    run_interval = 3600 # 1 hour
    name = "usermonitor"

    def __init__(self, provider=None):
        if provider is None:
            provider = UserProvider()
        self._provider = provider
        self._port = None

    def register(self, registry):
        super(UserMonitor, self).register(registry)

        self.registry.reactor.call_on("resynchronize", self._resynchronize)
        self.call_on_accepted("users", self._run_detect_changes, None)

        factory = UserMonitorProtocolFactory(object=self)
        socket = os.path.join(self.registry.config.data_path,
                              self.name + ".sock")
        self._port = self.registry.reactor.listen_unix(socket, factory)
        from landscape.manager.usermanager import RemoteUserManagerConnector
        self._user_manager_connector = RemoteUserManagerConnector(
            self.registry.reactor, self.registry.config)

    def stop(self):
        """Stop listening for incoming AMP connections."""
        if self._port:
            self._port.stopListening()
            self._port = None

    def _resynchronize(self):
        """Resynchronize user and group data."""
        changes = UserChanges(self._persist, self._provider)
        changes.clear()
        return self._run_detect_changes()

    def run(self, operation_id=None):
        return self.registry.broker.call_if_accepted(
            "users", self._run_detect_changes, operation_id)

    detect_changes = run

    def _run_detect_changes(self, operation_id=None):
        """
        If changes are detected an C{urgent-exchange} is fired to send
        updates to the server immediately.

        @param operation_id: When present it will be included in the
            C{operation-id} field.
        """
        # We'll skip checking the locked users if we're in monitor-only mode.
        if getattr(self.registry.config, "monitor_only", False):
            result = maybeDeferred(self._detect_changes,
                                   [], operation_id)
        else:

            def get_locked_usernames(user_manager):
                return user_manager.get_locked_usernames()

            def disconnect(locked_usernames):
                self._user_manager_connector.disconnect()
                return locked_usernames

            result = self._user_manager_connector.connect()
            result.addCallback(get_locked_usernames)
            result.addCallback(disconnect)
            result.addCallback(self._detect_changes, operation_id)
            result.addErrback(lambda f: self._detect_changes([], operation_id))
        return result

    def _detect_changes(self, locked_users, operation_id=None):

        def update_snapshot(result):
            changes.snapshot()
            return result

        def log_error(result):
            log_failure(result, "Error occured calling send_message in "
                        "_detect_changes")

        self._provider.locked_users = locked_users
        changes = UserChanges(self._persist, self._provider)
        message = changes.create_diff()

        if message:
            message["type"] = "users"
            if operation_id:
                message["operation-id"] = operation_id
            result = self.registry.broker.send_message(message, urgent=True)
            result.addCallback(update_snapshot)
            result.addErrback(log_error)
            return result


class UserMonitorProtocol(ComponentProtocol):
    """L{AMP}-based protocol for calling L{UserMonitor}'s methods remotely."""

    methods = ["detect_changes"]


class UserMonitorProtocolFactory(ComponentProtocolFactory):

    protocol = UserMonitorProtocol


class RemoteUserMonitor(RemoteObject):
    """A connected remote L{UserMonitor}."""


class RemoteUserMonitorConnector(RemoteComponentConnector):

    factory = ComponentProtocolFactory
    remote = RemoteUserMonitor
    component = UserMonitor
