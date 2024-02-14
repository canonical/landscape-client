# XXX: There is the potential for some sort of "unixadmin" package
# which wraps up the commands which we use in this module in a Python
# API, with thorough usage of exceptions and such, instead of pipes to
# subprocesses. liboobs (i.e. System Tools) is a possibility, and has
# documentation now in the 2.17 series, but is not wrapped to Python.
import logging
import subprocess

from landscape.client import snap_http
from landscape.client.snap_http import SnapdHttpException
from landscape.client.snap_utils import parse_assertion
from landscape.client.user.provider import UserManagementError
from landscape.client.user.provider import UserProvider


class UserManagement:
    """Manage system users and groups."""

    def __init__(self, provider=None):
        self._provider = provider or UserProvider()

    def add_user(self, message):
        """Add C{username} to the computer.

        @raises UserManagementError: Raised when C{adduser} fails.
        @raises UserManagementError: Raised when C{passwd} fails.
        """
        username = message["username"]
        name = message["name"]
        password = message["password"]
        require_password_reset = message["require-password-reset"]
        primary_group_name = message["primary-group-name"]
        location = message["location"]
        work_phone = message["work-number"]
        home_phone = message["home-number"]

        logging.info("Adding user %s.", username)
        gecos = "{},{},{},{}".format(
            name,
            location or "",
            work_phone or "",
            home_phone or "",
        )
        command = [
            "adduser",
            username,
            "--disabled-password",
            "--gecos",
            gecos,
        ]
        if primary_group_name:
            command.extend(
                ["--gid", str(self._provider.get_gid(primary_group_name))],
            )
        result, output = self.call_popen(command)
        if result != 0:
            raise UserManagementError(
                f"Error adding user {username}.\n{output}",
            )

        self._set_password(username, password)
        if require_password_reset:
            result, new_output = self.call_popen(["passwd", username, "-e"])
            if result != 0:
                raise UserManagementError(
                    "Error resetting password for user "
                    f"{username}.\n{new_output}",
                )
            else:
                output += new_output
        return output

    def _set_password(self, username, password):
        chpasswd_input = f"{username}:{password}".encode("utf-8")
        chpasswd = self._provider.popen(
            ["chpasswd"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output, stderr = chpasswd.communicate(chpasswd_input)
        result = chpasswd.returncode
        if result != 0:
            username = username.encode("utf-8")
            raise UserManagementError(
                "Error setting password for user {}.\n{} {}".format(
                    username,
                    output,
                    stderr,
                ),
            )
        return output

    def _set_primary_group(self, username, groupname):
        primary_gid = self._provider.get_gid(groupname)
        command = ["usermod", "-g", str(primary_gid), username]
        result, output = self.call_popen(command)
        if result != 0:
            raise UserManagementError(
                f"Error setting primary group to {primary_gid:d} for"
                f"{username}.\n{output}",
            )
        return output

    def set_user_details(
        self,
        username,
        password=None,
        name=None,
        location=None,
        work_number=None,
        home_number=None,
        primary_group_name=None,
    ):
        """Update details for the account matching C{uid}."""
        uid = self._provider.get_uid(username)
        logging.info("Updating data for user %s (UID %d).", username, uid)
        if password:
            self._set_password(username, password)

        if primary_group_name:
            self._set_primary_group(username, primary_group_name)

        command = ["chfn"]
        for option, value in [
            ("-r", location),
            ("-f", name),
            ("-w", work_number),
            ("-h", home_number),
        ]:
            if value is not None:
                command += [option, value]

        if len(command) > 1:
            result, output = self.call_popen(command + [username])
            if result != 0:
                raise UserManagementError(
                    "Error setting details for user " f"{username}.\n{output}",
                )
            return output

    def lock_user(self, username):
        """
        Lock the account matching C{username} to prevent them from logging in.
        """
        uid = self._provider.get_uid(username)
        logging.info("Locking out user %s (UID %d).", username, uid)
        result, output = self.call_popen(["usermod", "-L", username])
        if result != 0:
            raise UserManagementError(
                f"Error locking user {username}.\n{output}",
            )

    def unlock_user(self, username):
        """Unlock the account matching C{username}."""
        uid = self._provider.get_uid(username)
        logging.info("Unlocking user %s (UID %d).", username, uid)

        result, output = self.call_popen(["usermod", "-U", username])
        if result != 0:
            raise UserManagementError(
                f"Error unlocking user {username}.\n{output}",
            )
        return output

    def remove_user(self, message):
        """Remove the account matching C{username} from the computer."""
        username = message["username"]
        delete_home = message.get("delete-home", False)

        uid = self._provider.get_uid(username)
        command = ["deluser", username]
        if delete_home:
            logging.info(
                "Removing user %s (UID %d) and deleting their home "
                "directory.",
                username,
                uid,
            )
            command.append("--remove-home")
        else:
            logging.info(
                "Removing user %s (UID %d) without deleting their "
                "home directory.",
                username,
                uid,
            )

        result, output = self.call_popen(command)
        if result != 0:
            raise UserManagementError(
                f"Error removing user {username} (UID {uid:d}).\n{output}",
            )
        return output

    def add_group(self, groupname):
        """Add C{group} with the C{addgroup} system command."""
        logging.info("Adding group %s.", groupname)
        result, output = self.call_popen(["addgroup", groupname])
        if result != 0:
            raise UserManagementError(
                f"Error adding group {groupname}.\n{output}",
            )
        return output

    def set_group_details(self, groupname, new_name):
        """Update details for the group matching C{gid}."""
        gid = self._provider.get_gid(groupname)
        logging.info(
            "Renaming group %s (GID %d) to %s.",
            groupname,
            gid,
            new_name,
        )
        command = ["groupmod", "-n", new_name, groupname]
        result, output = self.call_popen(command)
        if result != 0:
            raise UserManagementError(
                f"Error renaming group {groupname} (GID {gid:d}) to "
                f"{new_name}.\n{output}",
            )
        return output

    def add_group_member(self, username, groupname):
        """
        Add the user matching C{username} to the group matching C{groupname}
        with the C{gpasswd} system command.
        """
        uid = self._provider.get_uid(username)
        gid = self._provider.get_gid(groupname)
        logging.info(
            "Adding user %s (UID %d) to group %s (GID %d).",
            username,
            uid,
            groupname,
            gid,
        )
        result, output = self.call_popen(
            ["gpasswd", "-a", username, groupname],
        )
        if result != 0:
            raise UserManagementError(
                f"Error adding user {username} (UID {uid:d}) to "
                f"group {groupname} (GID {gid:d}).\n{output}",
            )
        return output

    def remove_group_member(self, username, groupname):
        """
        Remove the user matching C{username} from the group matching
        C{groupname} with the C{gpasswd} system command.
        """
        uid = self._provider.get_uid(username)
        gid = self._provider.get_gid(groupname)
        logging.info(
            "Removing user %s (UID %d) from group %s (GID %d).",
            username,
            uid,
            groupname,
            gid,
        )
        result, output = self.call_popen(
            ["gpasswd", "-d", username, groupname],
        )
        if result != 0:
            raise UserManagementError(
                f"Error removing user {username} (UID {uid:d}) "
                f"from group {groupname} (GID ({gid:d}).\n{output}",
            )
        return output

    def remove_group(self, groupname):
        """Remove the account matching C{groupname} from the computer."""
        gid = self._provider.get_gid(groupname)
        logging.info("Removing group %s (GID %d).", groupname, gid)
        result, output = self.call_popen(["groupdel", groupname])
        if result != 0:
            raise UserManagementError(
                f"Error removing group {groupname} (GID {gid:d}).\n{output}",
            )
        return output

    def call_popen(self, args):
        popen = self._provider.popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = popen.stdout.read()
        result = popen.wait()
        return result, output


class SnapdUserManagement:
    """Manage users via the Snapd API."""

    def __init__(self, provider=None):
        self._provider = provider or UserProvider(
            passwd_file="/var/lib/extrausers/passwd",
            group_file="/var/lib/extrausers/group",
        )

    def add_user(self, message):
        """Add a user via the Snapd API.

        Message formats can be in two forms:
            - SSO User (username, email, sudoer, force-managed)
            - System User (assertion, sudoer, force-managed)
        """
        if "assertion" in message:
            assertion = self._add_system_user_assertion(message["assertion"])
            username = assertion["username"]
            email = assertion["email"]
            known = True
        else:
            # Ubuntu One SSO User
            username = message["username"]
            email = message["email"]
            known = False

        sudoer = message.get("sudoer", False)
        force_managed = message.get("force-managed", False)

        try:
            response = snap_http.add_user(
                username,
                email,
                sudoer=sudoer,
                force_managed=force_managed,
                known=known,
            )
        except SnapdHttpException as e:
            result = e.json["result"]
            raise UserManagementError(result)

        return response.result

    def _add_system_user_assertion(self, assertion):
        """Add a system user assertion."""
        try:
            # adding an assertion is idempotent
            snap_http.add_assertion(assertion)
        except SnapdHttpException as e:
            result = e.json["result"]
            raise UserManagementError(result)

        return parse_assertion(*assertion.split("\n\n"))

    def set_user_details(self, *_):
        """Update a user's details."""

    def lock_user(self, *_):
        """Lock a user's account to prevent them from logging in."""

    def unlock_user(self, *_):
        """Unlock a user's account."""

    def remove_user(self, message):
        """Remove a user via the Snapd API."""
        try:
            response = snap_http.remove_user(message["username"])
        except SnapdHttpException as e:
            result = e.json["result"]
            raise UserManagementError(result)

        return response.result

    def add_group(self, *_):
        """Add a group to the computer."""

    def set_group_details(self, *_):
        """Update group details."""

    def add_group_member(self, *_):
        """Add a member to a group."""

    def remove_group_member(self, *_):
        """Remove a member from a group."""

    def remove_group(self, *_):
        """Remove a group from the computer."""
