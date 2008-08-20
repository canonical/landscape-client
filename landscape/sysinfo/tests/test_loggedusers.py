from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.loggedusers import LoggedUsers
from landscape.lib.tests.test_sysstats import FakeWhoQTest


class LoggedUsersTest(FakeWhoQTest):

    def setUp(self):
        super(LoggedUsersTest, self).setUp()
        self.logged_users = LoggedUsers()
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.logged_users)

    def test_run_adds_header(self):
        self.fake_who("one two three")
        result = self.logged_users.run()
        def check_headers(result):
            self.assertEquals(self.sysinfo.get_headers(),
                              [("Logged users", "3")])
        return result.addCallback(check_headers)

    def test_order_is_preserved_even_if_asynchronous(self):
        self.fake_who("one two three")
        self.sysinfo.add_header("Before", "1")
        result = self.logged_users.run()
        self.sysinfo.add_header("After", "2")
        def check_headers(result):
            self.assertEquals(self.sysinfo.get_headers(),
                              [("Before", "1"),
                               ("Logged users", "3"),
                               ("After", "2")])
        return result.addCallback(check_headers)

    def test_ignore_errors_on_command(self):
        self.fake_who("")
        who = open(self.who_path, "w")
        who.write("#!/bin/sh\necho ERROR >&2\nexit 1\n")
        who.close()
        # Nothing bad should happen if who isn't installed, or
        # if anything else happens with the command execution.
        self.logged_users.run()
        self.assertEquals(self.sysinfo.get_headers(), [])
