from twisted.internet.defer import maybeDeferred

from landscape.lib.log import log_failure
from landscape.amp import ComponentPublisher, ComponentConnector, remote

from landscape.monitor.plugin import MonitorPlugin
from landscape.user.changes import UserChanges
from landscape.user.provider import UserProvider


class UserMonitor(MonitorPlugin):
    """
    A plugin which monitors the system user databases.
    """

    persist_name = "users"
    scope = "users"
    run_interval = 3600  # 1 hour
    name = "usermonitor"

    def __init__(self, provider=None):
        if provider is None:
            provider = UserProvider()
        self._provider = provider
        self._publisher = None

    def register(self, registry):
        super(UserMonitor, self).register(registry)

        self.call_on_accepted("users", self._run_detect_changes, None)

        self._publisher = ComponentPublisher(self, self.registry.reactor,
                                             self.registry.config)
        self._publisher.start()

    def stop(self):
        """Stop listening for incoming AMP connections."""
        if self._publisher:
            self._publisher.stop()
            self._publisher = None

    def _reset(self):
        """Reset user and group data."""
        super(UserMonitor, self)._reset()
        return self._run_detect_changes()

    @remote
    def detect_changes(self, operation_id=None):
        return self.registry.broker.call_if_accepted(
            "users", self._run_detect_changes, operation_id)

    run = detect_changes

    def _run_detect_changes(self, operation_id=None):
        """
        If changes are detected an C{urgent-exchange} is fired to send
        updates to the server immediately.

        @param operation_id: When present it will be included in the
            C{operation-id} field.
        """
        from landscape.manager.usermanager import RemoteUserManagerConnector
        user_manager_connector = RemoteUserManagerConnector(
            self.registry.reactor, self.registry.config)

        # We'll skip checking the locked users if we're in monitor-only mode.
        if getattr(self.registry.config, "monitor_only", False):
            result = maybeDeferred(self._detect_changes,
                                   [], operation_id)
        else:

            def get_locked_usernames(user_manager):
                return user_manager.get_locked_usernames()

            def disconnect(locked_usernames):
                user_manager_connector.disconnect()
                return locked_usernames

            result = user_manager_connector.connect()
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
            result = self.registry.broker.send_message(
                message, self._session_id, urgent=True)
            result.addCallback(update_snapshot)
            result.addErrback(log_error)
            return result


class RemoteUserMonitorConnector(ComponentConnector):

    component = UserMonitor
