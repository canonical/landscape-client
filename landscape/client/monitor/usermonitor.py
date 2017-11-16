import logging
import os
import os.path

from twisted.internet.defer import maybeDeferred

from landscape.lib.log import log_failure
from landscape.client.amp import ComponentPublisher, ComponentConnector, remote

from landscape.client.monitor.plugin import MonitorPlugin
from landscape.client.user.changes import UserChanges
from landscape.client.user.provider import UserProvider


# Part of bug 1048576 remediation:
USER_UPDATE_FLAG_FILE = "user-update-flag"


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

    def _resynchronize(self, scopes=None):
        """Reset user and group data."""
        deferred = super(UserMonitor, self)._resynchronize(scopes=scopes)
        # Wait for the superclass' asynchronous _resynchronize method to
        # complete, so we have a new session ID at hand and we can craft a
        # valid message (l.broker.client.BrokerClientPlugin._resynchronize).
        deferred.addCallback(lambda _: self._run_detect_changes())
        return deferred

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
        from landscape.client.manager.usermanager import (
                RemoteUserManagerConnector)
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

    def _detect_changes(self, locked_users, operation_id=None,
                        UserChanges=UserChanges):

        def update_snapshot(result):
            changes.snapshot()
            return result

        def log_error(result):
            log_failure(result, "Error occured calling send_message in "
                        "_detect_changes")

        self._provider.locked_users = locked_users
        changes = UserChanges(self._persist, self._provider)

        # Part of bug 1048576 remediation: If the flag file exists, we need to
        # do a full update of user data.
        full_refresh = os.path.exists(self.user_update_flag_file_path)
        if full_refresh:
            # Clear the record of what changes have been sent to the server in
            # order to force sending of all user data which will do one of two
            # things server side:  either the server has no user data at all,
            # in which case it will now have a complete copy, otherwise it
            # will have at least some user data which this message will
            # duplicate, provoking the server to note the inconsistency and
            # request a full resync of the user data.  Either way, the result
            # is the same: the client and server will be in sync with regard
            # to users.
            changes.clear()

        message = changes.create_diff()

        if message:
            message["type"] = "users"
            if operation_id:
                message["operation-id"] = operation_id
            result = self.registry.broker.send_message(
                message, self._session_id, urgent=True)
            result.addCallback(update_snapshot)

            # Part of bug 1048576 remediation:
            if full_refresh:
                # If we are doing a full refresh, we want to remove the flag
                # file that triggered the refresh if it completes successfully.
                result.addCallback(lambda _: self._remove_update_flag_file())

            result.addErrback(log_error)
            return result

    def _remove_update_flag_file(self):
        """Remove the full update flag file, logging any errors.

        This is part of the bug 1048576 remediation.
        """
        try:
            os.remove(self.user_update_flag_file_path)
        except OSError:
            logging.exception("Error removing user update flag file.")

    @property
    def user_update_flag_file_path(self):
        """Location of the user update flag file.

        This is part of the bug 1048576 remediation.
        """
        return os.path.join(
            self.registry.config.data_path, USER_UPDATE_FLAG_FILE)


class RemoteUserMonitorConnector(ComponentConnector):

    component = UserMonitor
