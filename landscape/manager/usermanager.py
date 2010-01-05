import logging

from landscape.lib.amp import (
    Method, MethodCallProtocol, MethodCallFactory, RemoteObjectCreator)
from landscape.lib.twisted_util import gather_results

from landscape.user.management import UserManagement
from landscape.manager.manager import ManagerPlugin
from landscape.monitor.usermonitor import RemoteUserMonitorCreator


class UserManagerProtocol(MethodCallProtocol):
    """L{AMP}-based protocol for calling L{UserManager}'s methods remotely."""

    methods = [Method("get_locked_usernames")]


class UserManagerFactory(MethodCallFactory):

    protocol = UserManagerProtocol


class RemoteUserManagerCreator(RemoteObjectCreator):

    protocol = UserManagerProtocol

    def __init__(self, reactor, config):
        super(RemoteUserManagerCreator, self).__init__(
            reactor._reactor, config.user_manager_socket_filename)


class UserManager(ManagerPlugin):

    def __init__(self, management=None, shadow_file="/etc/shadow"):
        self._management = management or UserManagement()
        self._shadow_file = shadow_file

        self._message_types = {"add-user": self._add_user,
                               "edit-user": self._edit_user,
                               "lock-user": self._lock_user,
                               "unlock-user": self._unlock_user,
                               "remove-user": self._remove_user,
                               "add-group": self._add_group,
                               "edit-group": self._edit_group,
                               "remove-group": self._remove_group,
                               "add-group-member": self._add_group_member,
                               "remove-group-member": self._remove_group_member}

    def register(self, registry):
        """
        Schedule reactor events for generic L{Plugin} callbacks, user
        and group management operations, and resynchronization.
        """
        super(UserManager, self).register(registry)
        self._registry = registry
        results = []

        socket = self.registry.config.user_manager_socket_filename
        factory = UserManagerFactory(self.registry.reactor, self)
        self._port = self.registry.reactor._reactor.listenUNIX(socket, factory)
        self._user_monitor_creator = RemoteUserMonitorCreator(
            self.registry.reactor, self.registry.config)

        for message_type in self._message_types:
            result = self._registry.register_message(message_type,
                                                     self._message_dispatch)
            results.append(result)
        return gather_results(results)

    def get_locked_usernames(self):
        """Return a list of usernames with locked system accounts."""
        locked_users = []
        if self._shadow_file:
            try:
                shadow_file = open(self._shadow_file, "r")
                for line in shadow_file:
                    parts = line.split(":")
                    if len(parts)>1:
                        if parts[1].startswith("!"):
                            locked_users.append(parts[0].strip())
            except IOError, e:
                logging.error("Error reading shadow file. %s" % e)
        return locked_users

    def _message_dispatch(self, message):

        def detect_changes(user_monitor):
            self._user_monitor = user_monitor
            return user_monitor.detect_changes()

#        def disconnect(result):
#            self._user_monitor_creator.disconnect()
#            return result

        result = self._user_monitor_creator.connect()
        result.addCallback(detect_changes)
#        result.addCallback(disconnect)
        result.addCallback(self._perform_operation, message)
        result.addCallback(self._send_changes, message)
        return result

    def _perform_operation(self, result, message):
        message_type = message["type"]
        message_method = self._message_types[message_type]
        return self.call_with_operation_result(message, message_method, message)

    def _send_changes(self, result, message):
        result = self._user_monitor.detect_changes(message["operation-id"])
        result.addCallback(lambda x: self._user_monitor_creator.disconnect())
        return result

    def _add_user(self, message):
        """Run an C{add-user} operation."""
        return self._management.add_user(message["username"], message["name"],
                                         message["password"],
                                         message["require-password-reset"],
                                         message["primary-group-name"],
                                         message["location"],
                                         message["work-number"],
                                         message["home-number"])

    def _edit_user(self, message):
        """Run an C{edit-user} operation."""
        return self._management.set_user_details(
                 message["username"], password=message["password"],
                 name=message["name"], location=message["location"],
                 work_number=message["work-number"],
                 home_number=message["home-number"],
                 primary_group_name=message["primary-group-name"])

    def _lock_user(self, message):
        """Run a C{lock-user} operation."""
        return self._management.lock_user(message["username"])

    def _unlock_user(self, message):
        """Run an C{unlock-user} operation."""
        return self._management.unlock_user(message["username"])

    def _remove_user(self, message):
        """Run a C{remove-user} operation."""
        return self._management.remove_user(message["username"],
                                            message["delete-home"])

    def _add_group(self, message):
        """Run an C{add-group} operation."""
        return self._management.add_group(message["groupname"])

    def _edit_group(self, message):
        """Run an C{edit-group} operation."""
        return self._management.set_group_details(message["groupname"],
                                                  message["new-name"])

    def _add_group_member(self, message):
        """Run an C{add-group-member} operation."""
        return self._management.add_group_member(message["username"],
                                                 message["groupname"])

    def _remove_group_member(self, message):
        """Run a C{remove-group-member} operation."""
        return self._management.remove_group_member(message["username"],
                                                    message["groupname"])

    def _remove_group(self, message):
        """Run an C{remove-group} operation."""
        return self._management.remove_group(message["groupname"])
