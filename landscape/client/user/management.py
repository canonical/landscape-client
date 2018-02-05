# XXX: There is the potential for some sort of "unixadmin" package
# which wraps up the commands which we use in this module in a Python
# API, with thorough usage of exceptions and such, instead of pipes to
# subprocesses. liboobs (i.e. System Tools) is a possibility, and has
# documentation now in the 2.17 series, but is not wrapped to Python.

import logging
import subprocess

from landscape.client.user.provider import UserManagementError, UserProvider


class UserManagement(object):
    """Manage system users and groups."""

    def __init__(self, provider=None):
        self._provider = provider or UserProvider()

    def add_user(self, username, name, password, require_password_reset,
                 primary_group_name, location, work_phone, home_phone):
        """Add C{username} to the computer.

        @raises UserManagementError: Raised when C{adduser} fails.
        @raises UserManagementError: Raised when C{passwd} fails.
        """
        logging.info("Adding user %s.", username)
        gecos = "%s,%s,%s,%s" % (name, location or "", work_phone or "",
                                 home_phone or "")
        command = ["adduser", username, "--disabled-password", "--gecos",
                   gecos]
        if primary_group_name:
            command.extend(["--gid", str(self._provider.get_gid(
                primary_group_name))])
        result, output = self.call_popen(command)
        if result != 0:
            raise UserManagementError("Error adding user %s.\n%s" %
                                      (username, output))

        self._set_password(username, password)
        if require_password_reset:
            result, new_output = self.call_popen(["passwd", username, "-e"])
            if result != 0:
                raise UserManagementError("Error resetting password for user "
                                          "%s.\n%s" % (username, new_output))
            else:
                output += new_output
        return output

    def _set_password(self, username, password):
        chpasswd_input = "{}:{}".format(username, password).encode("utf-8")
        chpasswd = self._provider.popen(["chpasswd"],
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
        output, stderr = chpasswd.communicate(chpasswd_input)
        result = chpasswd.returncode
        if result != 0:
            username = username.encode("utf-8")
            raise UserManagementError(
                "Error setting password for user {}.\n{} {}".format(
                    username, output, stderr))
        return output

    def _set_primary_group(self, username, groupname):
        primary_gid = self._provider.get_gid(groupname)
        command = ["usermod", "-g", str(primary_gid), username]
        result, output = self.call_popen(command)
        if result != 0:
            raise UserManagementError("Error setting primary group to %d for"
                                      "%s.\n%s" % (primary_gid, username,
                                                   output))
        return output

    def set_user_details(self, username, password=None, name=None,
                         location=None, work_number=None, home_number=None,
                         primary_group_name=None):
        """Update details for the account matching C{uid}."""
        uid = self._provider.get_uid(username)
        logging.info("Updating data for user %s (UID %d).", username, uid)
        if password:
            self._set_password(username, password)

        if primary_group_name:
            self._set_primary_group(username, primary_group_name)

        command = ["chfn"]
        for option, value in [("-r", location), ("-f", name),
                              ("-w", work_number), ("-h", home_number)]:
            if value is not None:
                command += [option, value]

        if len(command) > 1:
            result, output = self.call_popen(command + [username])
            if result != 0:
                raise UserManagementError("Error setting details for user "
                                          "%s.\n%s" % (username, output))
            return output

    def lock_user(self, username):
        """
        Lock the account matching C{username} to prevent them from logging in.
        """
        uid = self._provider.get_uid(username)
        logging.info("Locking out user %s (UID %d).", username, uid)
        result, output = self.call_popen(["usermod", "-L", username])
        if result != 0:
            raise UserManagementError("Error locking user %s.\n%s" %
                                      (username, output))

    def unlock_user(self, username):
        """Unlock the account matching C{username}."""
        uid = self._provider.get_uid(username)
        logging.info("Unlocking user %s (UID %d).", username, uid)

        result, output = self.call_popen(["usermod", "-U", username])
        if result != 0:
            raise UserManagementError("Error unlocking user %s.\n%s"
                                      % (username, output))
        return output

    def remove_user(self, username, delete_home=False):
        """Remove the account matching C{username} from the computer."""
        uid = self._provider.get_uid(username)
        command = ["deluser", username]
        if delete_home:
            logging.info("Removing user %s (UID %d) and deleting their home "
                         "directory.", username, uid)
            command.append("--remove-home")
        else:
            logging.info("Removing user %s (UID %d) without deleting their "
                         "home directory.", username, uid)

        result, output = self.call_popen(command)
        if result != 0:
            raise UserManagementError("Error removing user %s (UID %d).\n%s"
                                      % (username, uid, output))
        return output

    def add_group(self, groupname):
        """Add C{group} with the C{addgroup} system command."""
        logging.info("Adding group %s.", groupname)
        result, output = self.call_popen(["addgroup", groupname])
        if result != 0:
            raise UserManagementError("Error adding group %s.\n%s" %
                                      (groupname, output))
        return output

    def set_group_details(self, groupname, new_name):
        """Update details for the group matching C{gid}."""
        gid = self._provider.get_gid(groupname)
        logging.info("Renaming group %s (GID %d) to %s.",
                     groupname, gid, new_name)
        command = ["groupmod", "-n", new_name, groupname]
        result, output = self.call_popen(command)
        if result != 0:
            raise UserManagementError("Error renaming group %s (GID %d) to "
                                      "%s.\n%s" % (groupname, gid, new_name,
                                                   output))
        return output

    def add_group_member(self, username, groupname):
        """
        Add the user matching C{username} to the group matching C{groupname}
        with the C{gpasswd} system command.
        """
        uid = self._provider.get_uid(username)
        gid = self._provider.get_gid(groupname)
        logging.info("Adding user %s (UID %d) to group %s (GID %d).",
                     username, uid, groupname, gid)
        result, output = self.call_popen(["gpasswd", "-a", username,
                                          groupname])
        if result != 0:
            raise UserManagementError("Error adding user %s (UID %d) to "
                                      "group %s (GID %d).\n%s" %
                                      (username, uid, groupname, gid, output))
        return output

    def remove_group_member(self, username, groupname):
        """
        Remove the user matching C{username} from the group matching
        C{groupname} with the C{gpasswd} system command.
        """
        uid = self._provider.get_uid(username)
        gid = self._provider.get_gid(groupname)
        logging.info("Removing user %s (UID %d) from group %s (GID %d).",
                     username, uid, groupname, gid)
        result, output = self.call_popen(["gpasswd", "-d", username,
                                          groupname])
        if result != 0:
            raise UserManagementError("Error removing user %s (UID %d) "
                                      "from group %s (GID (%d).\n%s"
                                      % (username, uid, groupname,
                                         gid, output))
        return output

    def remove_group(self, groupname):
        """Remove the account matching C{groupname} from the computer."""
        gid = self._provider.get_gid(groupname)
        logging.info("Removing group %s (GID %d).", groupname, gid)
        result, output = self.call_popen(["groupdel", groupname])
        if result != 0:
            raise UserManagementError("Error removing group %s (GID %d).\n%s" %
                                      (groupname, gid, output))
        return output

    def call_popen(self, args):
        popen = self._provider.popen(args,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
        output = popen.stdout.read()
        result = popen.wait()
        return result, output
