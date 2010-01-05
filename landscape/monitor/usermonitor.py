from twisted.internet.defer import maybeDeferred

from landscape.lib.log import log_failure
from landscape.lib.amp import (
    Method, MethodCallProtocol, MethodCallFactory, RemoteObjectCreator)

from landscape.monitor.monitor import MonitorPlugin
from landscape.user.changes import UserChanges
from landscape.user.provider import UserProvider


class UserMonitorProtocol(MethodCallProtocol):
    """L{AMP}-based protocol for calling L{UserMonitor}'s methods remotely."""

    methods = [Method("detect_changes")]


class UserMonitorFactory(MethodCallFactory):

    protocol = UserMonitorProtocol


class RemoteUserMonitorCreator(RemoteObjectCreator):

    protocol = UserMonitorProtocol

    def __init__(self, reactor, config):
        super(RemoteUserMonitorCreator, self).__init__(
            reactor._reactor, config.user_monitor_socket_filename)


class UserMonitor(MonitorPlugin):
    """
    A plugin which monitors the system user databases.
    """

    persist_name = "users"
    run_interval = 3600 # 1 hour

    def __init__(self, provider=None):
        if provider is None:
            provider = UserProvider()
        self._provider = provider

    def register(self, registry):
        super(UserMonitor, self).register(registry)

        self.registry.reactor.call_on("resynchronize", self._resynchronize)
        self.call_on_accepted("users", self._run_detect_changes, None)

        from landscape.manager.usermanager import RemoteUserManagerCreator
        self._start()
        self._user_manager_creator = RemoteUserManagerCreator(
            self.registry.reactor, self.registry.config)

    def _start(self):
        socket = self.registry.config.user_monitor_socket_filename
        factory = UserMonitorFactory(self.registry.reactor._reactor, self)
        self._port = self.registry.reactor._reactor.listenUNIX(socket, factory)

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
                self._user_manager_creator.disconnect()
                return locked_usernames

            result = self._user_manager_creator.connect()
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
