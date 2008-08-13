from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.loggedusers import LoggedUsers
from landscape.lib.tests.test_sysstats import FakeWhoQTest
from landscape.tests.helpers import LandscapeTest


class LoggedUsersTest(FakeWhoQTest):

    def setUp(self):
        super(LoggedUsersTest, self).setUp()
        self.logged_users = LoggedUsers()
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.logged_users)

    def test_run_returns_succeeded_deferred(self):
        self.assertDeferredSucceeded(self.logged_users.run())

    def test_run_adds_header(self):
        self.fake_who("one two three")
        self.logged_users.run()
        self.assertEquals(self.sysinfo.get_headers(),
                          [("Logged users", "3")])
