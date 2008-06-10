from twisted.python import log

from landscape.lib.dbus_util import get_object, method, Object

from landscape.user.management import UserManagement
from landscape.manager.manager import ManagerPlugin
from landscape.manager.manager import BUS_NAME, OBJECT_PATH, IFACE_NAME
from landscape.monitor.usermonitor import UserMonitorDBusObject


class UserManagerDBusObject(Object):
    """
    A DBUS object which provides an privileged read-only interface to the
    system shadow file.
    """
    object_path = OBJECT_PATH + "/UserManager"
    iface_name = IFACE_NAME + ".UserManager"
    bus_name = BUS_NAME

    def __init__(self, bus, shadow_file):
        super(UserManagerDBusObject, self).__init__(bus)
        self._shadow_file = shadow_file

    @method(iface_name, out_signature="as")
    def get_locked_usernames(self):
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
                log.err("Error reading shadow file. %s" % e)
        return locked_users


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
        # Register user management operation handlers.
        self._user_service = get_object(registry.bus,
                                        UserMonitorDBusObject.bus_name,
                                        UserMonitorDBusObject.object_path)
        for message_type in self._message_types:
            self._registry.register_message(message_type,
                                            self._message_dispatch)
        self._dbus_object = UserManagerDBusObject(registry.bus,
                                                  self._shadow_file)

    def _message_dispatch(self, message):
        result = self._user_service.detect_changes()
        result.addCallback(self._perform_operation, message)
        result.addCallback(self._send_changes, message)
        return result

    def _perform_operation(self, result, message):
        message_type = message["type"]
        message_method = self._message_types[message_type]
        return self.call_with_operation_result(message, message_method, message)

    def _send_changes(self, result, message):
        return self._user_service.detect_changes(message["operation-id"])

    def _add_user(self, message):
        """Run an C{add-user} operation."""
        return self._management.add_user(message["username"], message["name"],
                                         message["password"],
                                         message["require-password-reset"],
                                         message["primary-group-name"])

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

