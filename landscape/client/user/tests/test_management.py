from landscape.lib.testing import MockPopen
from landscape.client.user.management import (
        UserManagement, UserManagementError)
from landscape.client.user.tests.helpers import FakeUserProvider
from landscape.client.user.provider import (
        UserNotFoundError, GroupNotFoundError)
from landscape.client.tests.helpers import LandscapeTest


class UserWriteTest(LandscapeTest):

    def setUp(self):
        LandscapeTest.setUp(self)
        self.shadow_file = self.makeFile("""\
jdoe:$1$xFlQvTqe$cBtrNEDOIKMy/BuJoUdeG0:13348:0:99999:7:::
psmith:!:13348:0:99999:7:::
sbarnes:$1$q7sz09uw$q.A3526M/SHu8vUb.Jo1A/:13349:0:99999:7:::
""")

    def test_add_user(self):
        """L{UserManagement.add_user} should use C{adduser} to add users."""
        groups = [("users", "x", 1001, [])]
        provider = FakeUserProvider(groups=groups, popen=MockPopen(""))
        management = UserManagement(provider=provider)
        management.add_user("jdoe", "John Doe", "password", False, "users",
                            "Room 101", "+123456", None)
        self.assertEqual(len(provider.popen.popen_inputs), 2)
        self.assertEqual(provider.popen.popen_inputs[0],
                         ["adduser", "jdoe", "--disabled-password",
                          "--gecos", "John Doe,Room 101,+123456,",
                          "--gid", "1001"])

        chpasswd = provider.popen.popen_inputs[1]
        self.assertEqual(len(chpasswd), 1, chpasswd)
        self.assertEqual(b"jdoe:password", provider.popen.received_input)

    def test_add_user_error(self):
        """
        L{UserManagement.add_user} should raise an L{UserManagementError} if
        C{adduser} fails.
        """
        provider = FakeUserProvider(popen=MockPopen("", return_codes=[1, 0]))
        management = UserManagement(provider=provider)
        self.assertRaises(UserManagementError, management.add_user,
                          "jdoe", u"John Doe", "password", False, None, None,
                          None, None)

    def test_change_password_error(self):
        """
        UserManagement.add_user should raise a UserManagementError if
        chpasswd fails.
        """
        provider = FakeUserProvider(popen=MockPopen("", return_codes=[0, 1]))
        provider.popen.err_out = b"PAM is unhappy"
        management = UserManagement(provider=provider)
        with self.assertRaises(UserManagementError) as e:
            management.add_user("jdoe", u"John Doe", "password", False, None,
                                None, None, None)
        expected = "Error setting password for user {}.\n {}".format(
            b"jdoe", b"PAM is unhappy")
        self.assertEqual(expected, str(e.exception))

    def test_expire_password_error(self):
        """
        L{UserManagement.add_user} should raise an L{UserManagementError} if
        C{passwd} fails.
        """
        provider = FakeUserProvider(
            popen=MockPopen("", return_codes=[0, 0, 1]))
        management = UserManagement(provider=provider)
        self.assertRaises(UserManagementError, management.add_user,
                          "jdoe", u"John Doe", "password", True, None, None,
                          None, None)

    def test_set_password(self):
        """
        UserManagement.set_password should use chpasswd to change
        a user's password.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        management.set_user_details("jdoe", password="password")

        self.assertEqual(b"jdoe:password", provider.popen.received_input)
        self.assertEqual(provider.popen.popen_inputs, [["chpasswd"]])

    def test_set_password_with_system_user(self):
        """
        L{UserManagement.set_password} should allow us to edit system
        users.
        """
        data = [("root", "x", 0, 0, ",,,,", "/home/root", "/bin/zsh")]
        provider = FakeUserProvider(users=data,
                                    shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        management.set_user_details("root", password="password")
        self.assertEqual(len(provider.popen.popen_inputs), 1)
        self.assertEqual(b"root:password", provider.popen.received_input)

    def test_set_password_unicode(self):
        """
        Make sure passing unicode as username and password doesn't
        change things much (note that using something that's
        non-ASCII-encodable still probably won't work).
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        management.set_user_details("jdoe", password=u"password")

        self.assertEqual(len(provider.popen.popen_inputs), 1)
        self.assertEqual(b"jdoe:password", provider.popen.received_input)

    def test_set_name(self):
        """
        L{UserManagement.set_user_details} should use C{chfn} to
        change a user's name.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        management.set_user_details("jdoe", name="JD")

        self.assertEqual(len(provider.popen.popen_inputs), 1)
        self.assertEqual(provider.popen.popen_inputs,
                         [["chfn", "-f", "JD", "jdoe"]])

    def test_set_location(self):
        """
        L{UserManagement.set_user_details} should use C{chfn} to
        change a user's location.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        management.set_user_details("jdoe", location="Everywhere")

        self.assertEqual(len(provider.popen.popen_inputs), 1)
        self.assertEqual(provider.popen.popen_inputs,
                         [["chfn", "-r", "Everywhere", "jdoe"]])

    def test_clear_user_location(self):
        """
        L{UserManagement.set_user_details} should use C{chfn} to
        change a user's location.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,Room 101,,,", "/home/jdoe",
                 "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        management.set_user_details("jdoe", location="")
        self.assertEqual(len(provider.popen.popen_inputs), 1)
        self.assertEqual(provider.popen.popen_inputs,
                         [["chfn", "-r", "", "jdoe"]])

    def test_clear_telephone_numbers(self):
        """
        L{UserManagement.set_user_details} should use C{chfn} to
        change a user's telephone numbers.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,+123456,+123456", "/home/jdoe",
                 "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        management.set_user_details("jdoe", home_number="", work_number="")
        self.assertEqual(len(provider.popen.popen_inputs), 1)
        self.assertEqual(provider.popen.popen_inputs,
                         [["chfn", "-w", "", "-h", "", "jdoe"]])

    def test_set_user_details_fails(self):
        """
        L{UserManagement.set_user_details} should raise an
        L{EditUserError} if C{chfn} fails.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("", return_codes=[1]))
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.set_user_details, 1000,
                          name="John Doe")

    def test_contact_details_in_general(self):
        """
        L{UserManagement.set_user_details} should use C{chfn} to
        change a user's contact details.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        location = u"Everywhere"
        work_number = u"1-800-123-4567"
        home_number = u"764-4321"
        management.set_user_details("jdoe", location=location,
                                    work_number=work_number,
                                    home_number=home_number)

        self.assertEqual(len(provider.popen.popen_inputs), 1)
        self.assertEqual(provider.popen.popen_inputs,
                         [["chfn", "-r", location, "-w", work_number,
                           "-h", home_number, "jdoe"]])

    def test_set_user_details_with_unknown_username(self):
        """
        L{UserManagement.set_user_details} should raise a
        L{UserManagementError} if the user being edited doesn't exist.
        """
        provider = FakeUserProvider(popen=MockPopen(""))
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.set_user_details,
                          "kevin", name=u"John Doe")

    def test_set_primary_group(self):
        """
        L{UserManagement.set_set_user_details} should use C{usermod} to change
        the user's primary group.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("users", "x", 1001, [])]
        provider = FakeUserProvider(users=data, groups=groups,
                                    shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))

        management = UserManagement(provider=provider)
        management.set_user_details("jdoe", primary_group_name="users")

        self.assertEqual(provider.popen.popen_inputs,
                         [["usermod", "-g", "1001", "jdoe"]])

    def test_set_primary_group_unknown_group(self):
        """
        L{UserManagement.set_user_details should use C{usermod} to change the
        user's primary group, in the event that we have an invalid group, we
        should raise a UserManagement error.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("staff", "x", 1001, [])]
        provider = FakeUserProvider(users=data, groups=groups,
                                    shadow_file=self.shadow_file,
                                    popen=MockPopen("group id 1002 unknown",
                                                    return_codes=[1]),
                                    )
        management = UserManagement(provider=provider)
        self.assertRaises(GroupNotFoundError, management.set_user_details,
                          "jdoe", primary_group_name="unknown")

    def test_lock_user(self):
        """L{UserManagement.lock_user} should use C{usermod} to lock users."""
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        management.lock_user("jdoe")
        self.assertEqual(provider.popen.popen_inputs,
                         [["usermod", "-L", "jdoe"]])

    def test_lock_user_fails(self):
        """
        L{UserManagement.lock_user} should raise a L{UserManagementError} if
        a C{usermod} fails.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("", [1]))
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.lock_user, 1000)

    def test_lock_user_with_unknown_uid(self):
        """
        L{UserManagement.lock_user} should raise a L{UserManagementError}
        if the user being removed doesn't exist.
        """
        provider = FakeUserProvider(popen=MockPopen(""))
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.lock_user, 1000)

    def test_unlock_user(self):
        """
        L{UserManagement.unlock_user} should use C{usermod} to unlock
        users.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        management.unlock_user("jdoe")
        self.assertEqual(provider.popen.popen_inputs,
                         [["usermod", "-U", "jdoe"]])

    def test_unlock_user_fails(self):
        """
        L{UserManagement.unlock_user} should raise an
        L{UserManagementError} if a C{usermod} fails.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=MockPopen("", [1]))
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.unlock_user, 1000)

    def test_unlock_user_with_unknown_uid(self):
        """
        L{UserManagement.unlock_user} should raise a
        L{UserManagementError} if the user being removed doesn't exist.
        """
        provider = FakeUserProvider(popen=MockPopen(""))
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.unlock_user, 1000)

    def test_remove_user(self):
        """
        L{UserManagement.remove_user} should use C{deluser} to remove
        users.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        popen = MockPopen("Removing user `jdoe'...\r\ndone.")
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=popen)
        management = UserManagement(provider=provider)
        management.remove_user("jdoe")
        self.assertEqual(popen.popen_inputs, [["deluser", "jdoe"]])

    def test_remove_user_with_unknown_username(self):
        """
        L{UserManagement.remove_user} should raise a
        L{UserManagementError} if the user being removed doesn't exist.
        """
        provider = FakeUserProvider(popen=MockPopen(""))
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.remove_user, "smith")

    def test_remove_user_fails(self):
        """
        L{UserManagement.remove_user} should raise a
        L{UserManagementError} if the user can't be removed.
        """
        self.log_helper.ignore_errors(UserNotFoundError)
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        popen = MockPopen("/usr/sbin/deluser: Only root may remove a user or "
                          "group from the system.", [1])
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=popen)
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.remove_user, "smith")

    def test_remove_user_and_home(self):
        """
        L{UserManagement.remove_user} should use C{deluser} to remove
        the contents of a user's home directory.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        popen = MockPopen("Removing user `jdoe`...\r\ndone.", [0])
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    popen=popen)
        management = UserManagement(provider=provider)
        management.remove_user("jdoe", delete_home=True)
        self.assertEqual(popen.popen_inputs,
                         [["deluser", "jdoe", "--remove-home"]])


class GroupWriteTest(LandscapeTest):

    def setUp(self):
        LandscapeTest.setUp(self)
        self.shadow_file = self.makeFile("""\
jdoe:$1$xFlQvTqe$cBtrNEDOIKMy/BuJoUdeG0:13348:0:99999:7:::
psmith:!:13348:0:99999:7:::
sbarnes:$1$q7sz09uw$q.A3526M/SHu8vUb.Jo1A/:13349:0:99999:7:::
""")

    def test_add_group(self):
        """
        L{UserManagement.add_group} should use the system tool
        C{addgroup} to create groups.
        """
        provider = FakeUserProvider(popen=MockPopen("Result"))
        management = UserManagement(provider=provider)
        result = management.add_group("webdev")
        self.assertEqual(provider.popen.popen_inputs,
                         [["addgroup", "webdev"]])
        self.assertEqual(result, "Result")

    def test_add_group_handles_errors(self):
        """
        If the system tool C{addgroup} returns a non-0 exit code,
        L{UserManagement.add_group} should raise an L{UserManagementError}.
        """
        provider = FakeUserProvider(popen=MockPopen("Error Result", [1]))
        management = UserManagement(provider=provider)
        self.assertRaises(UserManagementError, management.add_group, "kaboom")

    def test_set_group_details(self):
        """
        L{UserManagement.set_group_details} should use C{groupmode} to
        change a group's name.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("bizdev", "x", 1001, [])]
        provider = FakeUserProvider(
            users=users, shadow_file=self.shadow_file,
            groups=groups, popen=MockPopen("no output"))
        management = UserManagement(provider=provider)
        management.set_group_details("bizdev", "sales")

        self.assertEqual(provider.popen.popen_inputs,
                         [["groupmod", "-n", "sales", "bizdev"]])

    def test_set_group_details_with_unknown_groupname(self):
        """
        L{UserManagement.set_group_details} should raise a
        L{UserManagementError} if the group being updated doesn't exist.
        """
        provider = FakeUserProvider(popen=MockPopen(""))
        management = UserManagement(provider=provider)
        self.assertRaises(GroupNotFoundError, management.set_group_details,
                          "sales", u"newsales")

    def test_set_group_details_fails(self):
        """
        L{UserManagement.set_group_details} should raise a
        L{UserManagementError} if the group can't be renamed.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("bizdev", "x", 1001, [])]
        popen = MockPopen("groupmod: sales is not a unique name", [1])
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups, popen=popen)
        management = UserManagement(provider=provider)
        self.assertRaises(UserManagementError, management.set_group_details,
                          "bizdev", u"sales")

    def test_add_member(self):
        """
        L{UserManagement.add_group_member} should use the system tool
        C{gpasswd} via the process factory to add a member to a group.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("bizdev", "x", 1001, [])]
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups,
                                    popen=MockPopen("Removing user jdoe "
                                                    "from group bizdev"),
                                    )
        management = UserManagement(provider=provider)

        output = management.add_group_member("jdoe", "bizdev")
        self.assertEqual(provider.popen.popen_inputs,
                         [["gpasswd", "-a", "jdoe", "bizdev"]])
        self.assertEqual(output, "Removing user jdoe from group bizdev")

    def test_add_member_with_unknown_groupname(self):
        """
        L{UserManagement.add_group_member} should raise a
        L{UserManagementError} if the group to add the member to doesn't
        exist.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    popen=MockPopen(""))
        management = UserManagement(provider=provider)
        self.assertRaises(GroupNotFoundError, management.add_group_member,
                          "jdoe", "bizdev")

    def test_add_member_with_unknown_username(self):
        """
        L{UserManagement.add_group_member} should raise a
        L{UserManagementError} if the user being associated doesn't
        exist.
        """
        groups = [("bizdev", "x", 1001, [])]
        provider = FakeUserProvider(groups=groups, popen=MockPopen(""))
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.add_group_member,
                          "bizdev", "smith")

    def test_add_member_failure(self):
        """
        If adding a member to a group fails,
        L{UserManagement.add_group_member} should raise an
        L{UserManagementError}.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("bizdev", "x", 1001, [])]
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups,
                                    popen=MockPopen("no output", [1]))
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.add_group_member,
                          1000, 1001)

    def test_remove_member(self):
        """
        L{UserManagement.remove_group_member} should use the system
        tool C{gpasswd} via the process factory to remove a member
        from a group.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("bizdev", "x", 1001, [])]
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups,
                                    popen=MockPopen("Removing user jdoe "
                                                    "from group bizdev"),
                                    )
        management = UserManagement(provider=provider)
        output = management.remove_group_member("jdoe", "bizdev")
        self.assertEqual(provider.popen.popen_inputs,
                         [["gpasswd", "-d", "jdoe", "bizdev"]])
        self.assertEqual(output, "Removing user jdoe from group bizdev")

    def test_remove_member_with_unknown_groupname(self):
        """
        L{UserManagement.remove_group_member} should raise a
        L{UserManagementError} if the group to remove the member to
        doesn't exist.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    popen=MockPopen("", return_codes=[2]))
        management = UserManagement(provider=provider)
        self.assertRaises(GroupNotFoundError, management.remove_group_member,
                          "jdoe", "bizdev")

    def test_remove_member_with_unknown_username(self):
        """
        L{UserManagement.remove_group_member} should raise a
        L{UserManagementError} if the user being associated doesn't
        exist.
        """
        groups = [("bizdev", "x", 1001, [])]
        provider = FakeUserProvider(groups=groups,
                                    popen=MockPopen("", return_codes=[4]))
        management = UserManagement(provider=provider)
        self.assertRaises(UserNotFoundError, management.remove_group_member,
                          "jdoe", "bizdev")

    def test_remove_member_failure(self):
        """
        If removing a member from a group fails,
        L{UserManagement.remove_group_member} should raise a
        L{UserManagementError}.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("bizdev", "x", 1001, [])]
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups,
                                    popen=MockPopen("no output", [1]))
        management = UserManagement(provider=provider)
        self.assertRaises(UserManagementError,
                          management.remove_group_member, "jdoe", "bizdev")

    def test_remove_group(self):
        """
        L{UserManagement.remove_group} should use C{groupdel} to
        remove groups.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("bizdev", "x", 50, [])]
        popen = MockPopen("Removing group `bizdev'...\r\ndone.")
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups, popen=popen)
        management = UserManagement(provider=provider)
        management.remove_group("bizdev")
        self.assertEqual(provider.popen.popen_inputs,
                         [["groupdel", "bizdev"]])

    def test_remove_group_with_unknown_groupname(self):
        """
        L{UserManagement.remove_group} should raise a
        L{GroupMissingError} if the group being removed doesn't exist.
        """
        provider = FakeUserProvider(popen=MockPopen(""))
        management = UserManagement(provider=provider)
        self.assertRaises(
            GroupNotFoundError, management.remove_group, "ubuntu")

    def test_remove_group_fails(self):
        """
        L{UserManagement.remove_user} should raise a
        L{RemoveUserError} if the user can't be removed.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("bizdev", "x", 50, [])]
        popen = MockPopen("/usr/sbin/deluser: Only root may remove a user or "
                          "group from the system.", [1])
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups, popen=popen)
        management = UserManagement(provider=provider)
        self.assertRaises(
            GroupNotFoundError, management.remove_group, "ubuntu")
