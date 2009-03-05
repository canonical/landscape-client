from twisted.internet.defer import fail

from landscape.lib.persist import Persist
from landscape.lib.dbus_util import get_object

from landscape.monitor.monitor import MonitorPluginRegistry
from landscape.monitor.usermonitor import UserMonitor, UserMonitorDBusObject
from landscape.manager.usermanager import UserManagerDBusObject
from landscape.user.tests.helpers import FakeUserProvider
from landscape.tests.helpers import LandscapeIsolatedTest
from landscape.tests.helpers import MakePathHelper, RemoteBrokerHelper
from landscape.tests.mocker import ANY


class UserMonitorNoManagerTest(LandscapeIsolatedTest):

    helpers = [MakePathHelper, RemoteBrokerHelper]

    def setUp(self):
        super(UserMonitorNoManagerTest, self).setUp()
        self.persist = Persist()
        self.monitor = MonitorPluginRegistry(
            self.remote, self.broker_service.reactor,
            self.broker_service.config, self.broker_service.bus, self.persist)

    def test_no_fetch_users_in_monitor_only_mode(self):
        """
        If we're in monitor_only mode, then all users are assumed to be
        unlocked.
        """
        self.broker_service.config.monitor_only = True
        def got_result(result):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"create-group-members": {u"webdev":[u"jdoe"]},
                  "create-groups": [{"gid": 1000, "name": u"webdev"}],
                  "create-users": [{"enabled": True, "home-phone": None,
                                    "location": None, "name": u"JD",
                                    "primary-gid": 1000, "uid": 1000,
                                    "username": u"jdoe", "work-phone": None}],
                                    "type": "users"}])

        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        plugin = UserMonitor(provider=provider)
        self.monitor.add(plugin)
        self.broker_service.message_store.set_accepted_types(["users"])
        result = plugin.run()
        result.addCallback(got_result)
        return result


class UserMonitorTest(LandscapeIsolatedTest):

    helpers = [MakePathHelper, RemoteBrokerHelper]

    def setUp(self):
        super(UserMonitorTest, self).setUp()
        self.persist = Persist()
        self.monitor = MonitorPluginRegistry(
            self.remote, self.broker_service.reactor,
            self.broker_service.config, self.broker_service.bus,
            self.persist)
        self.shadow_file = self.make_path("""\
jdoe:$1$xFlQvTqe$cBtrNEDOIKMy/BuJoUdeG0:13348:0:99999:7:::
psmith:!:13348:0:99999:7:::
sbarnes:$1$q7sz09uw$q.A3526M/SHu8vUb.Jo1A/:13349:0:99999:7:::
""")

        self.service = UserManagerDBusObject(self.broker_service.bus,
                                             shadow_file=self.shadow_file)

    def test_constants(self):
        """
        L{UserMonitor.persist_name} and
        L{UserMonitor.run_interval} need to be present for
        L{Plugin} to work properly.
        """
        plugin = UserMonitor(FakeUserProvider())
        self.assertEquals(plugin.persist_name, "users")
        self.assertEquals(plugin.run_interval, 3600)

    def test_wb_resynchronize_event(self):
        """
        When a C{resynchronize} event occurs any cached L{UserChange}
        snapshots should be cleared.
        """
        def resynchronize_complete(result, plugin):
            persist = plugin._persist
            self.assertTrue(persist.get("users"))
            self.assertTrue(persist.get("groups"))
            self.monitor.reactor.fire("resynchronize")
            self.assertFalse(persist.get("users"))
            self.assertFalse(persist.get("groups"))

        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        self.broker_service.message_store.set_accepted_types(["users"])
        provider = FakeUserProvider(users=users, groups=groups)
        plugin = UserMonitor(provider=provider)
        self.monitor.add(plugin)
        deferred = plugin.run()
        deferred.addCallback(resynchronize_complete, plugin)
        return deferred

    def test_run(self):
        """
        The L{UserMonitor} should have message run which should enqueue a
        message with  a diff-like representation of changes since the last
        run.
        """
        def got_result(result):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"create-group-members": {u"webdev":[u"jdoe"]},
                  "create-groups": [{"gid": 1000, "name": u"webdev"}],
                  "create-users": [{"enabled": True, "home-phone": None,
                                    "location": None, "name": u"JD",
                                    "primary-gid": 1000, "uid": 1000,
                                    "username": u"jdoe", "work-phone": None}],
                                    "type": "users"}])

        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        plugin = UserMonitor(provider=provider)
        self.monitor.add(plugin)
        self.broker_service.message_store.set_accepted_types(["users"])
        result = plugin.run()
        result.addCallback(got_result)
        return result

    def test_run_interval(self):
        """
        L{UserMonitor.register} calls the C{register} method on it's
        super class, which sets up a looping call to run the plugin
        every L{UserMonitor.run_interval} seconds.
        """
        provider = FakeUserProvider(users=[], groups=[])
        plugin = UserMonitor(provider=provider)

        mock_plugin = self.mocker.patch(plugin)
        mock_plugin.run()
        self.mocker.count(5)
        self.mocker.replay()

        self.monitor.add(plugin)
        self.broker_service.message_store.set_accepted_types(["users"])
        self.monitor.reactor.advance(plugin.run_interval*5)

    def test_run_with_operation_id(self):
        """
        The L{UserMonitor} should have message run which should enqueue a
        message with  a diff-like representation of changes since the last
        run.
        """
        def got_result(result):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"create-group-members": {u"webdev":[u"jdoe"]},
                  "create-groups": [{"gid": 1000, "name": u"webdev"}],
                  "create-users": [{"enabled": True, "home-phone": None,
                                    "location": None, "name": u"JD",
                                    "primary-gid": 1000, "uid": 1000,
                                    "username": u"jdoe", "work-phone": None}],
                                    "operation-id": 1001,
                                    "type": "users"}])


        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)

        plugin = UserMonitor(provider=provider)
        self.monitor.add(plugin)
        self.broker_service.message_store.set_accepted_types(["users"])
        result = plugin.run(1001)
        result.addCallback(got_result)
        return result

    def test_detect_changes(self):
        def got_result(result):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"create-group-members": {u"webdev":[u"jdoe"]},
                  "create-groups": [{"gid": 1000, "name": u"webdev"}],
                  "create-users": [{"enabled": True, "home-phone": None,
                                    "location": None, "name": u"JD",
                                    "primary-gid": 1000, "uid": 1000,
                  "username": u"jdoe", "work-phone": None}],
                  "type": "users"}])

        self.broker_service.message_store.set_accepted_types(["users"])
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)

        plugin = UserMonitor(provider=provider)
        self.monitor.add(plugin)
        remote_service = get_object(self.broker_service.bus,
            UserMonitorDBusObject.bus_name, UserMonitorDBusObject.object_path)
        result = remote_service.detect_changes()
        result.addCallback(got_result)
        return result

    def test_detect_changes_with_operation_id(self):
        """
        The L{UserMonitor} should expose a remote
        C{remote_run} method which should call the remote
        """
        def got_result(result):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"create-group-members": {u"webdev":[u"jdoe"]},
                  "create-groups": [{"gid": 1000, "name": u"webdev"}],
                  "create-users": [{"enabled": True, "home-phone": None,
                                    "location": None, "name": u"JD",
                                    "primary-gid": 1000, "uid": 1000,
                                    "username": u"jdoe", "work-phone": None}],
                  "operation-id": 1001,
                  "type": "users"}])

        self.broker_service.message_store.set_accepted_types(["users"])
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)

        plugin = UserMonitor(provider=provider)
        self.monitor.add(plugin)

        remote_service = get_object(self.broker_service.bus,
            UserMonitorDBusObject.bus_name, UserMonitorDBusObject.object_path)
        result = remote_service.detect_changes(1001)
        result.addCallback(got_result)
        return result

    def test_no_message_if_not_accepted(self):
        """
        Don't add any messages at all if the broker isn't currently
        accepting their type.
        """
        def got_result(result):
            mstore = self.broker_service.message_store
            self.assertMessages(list(mstore.get_pending_messages()), [])
            mstore.set_accepted_types(["users"])
            self.assertMessages(list(mstore.get_pending_messages()), [])

        self.broker_service.message_store.set_accepted_types([])
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)

        plugin = UserMonitor(provider=provider)
        self.monitor.add(plugin)
        remote_service = get_object(self.broker_service.bus,
            UserMonitorDBusObject.bus_name, UserMonitorDBusObject.object_path)
        result = remote_service.detect_changes(1001)
        result.addCallback(got_result)
        return result

    def test_call_on_accepted(self):
        def got_result(result):
            mstore = self.broker_service.message_store
            self.assertMessages(mstore.get_pending_messages(),
                [{"create-group-members": {u"webdev":[u"jdoe"]},
                  "create-groups": [{"gid": 1000, "name": u"webdev"}],
                  "create-users": [{"enabled": True, "home-phone": None,
                                    "location": None, "name": u"JD",
                                    "primary-gid": 1000, "uid": 1000,
                                    "username": u"jdoe", "work-phone": None}],
                  "type": "users"}])

        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)

        plugin = UserMonitor(provider=provider)
        self.monitor.add(plugin)

        self.broker_service.message_store.set_accepted_types(["users"])
        result = self.broker_service.reactor.fire(
            ("message-type-acceptance-changed", "users"), True)
        result = [x for x in result if x][0]
        result.addCallback(got_result)
        return result

    def test_do_not_persist_changes_when_send_message_fails(self):
        """
        When the plugin is run it persists data that it uses on
        subsequent checks to calculate the delta to send.  It should
        only persist data when the broker confirms that the message
        sent by the plugin has been sent.
        """
        self.log_helper.ignore_errors(RuntimeError)
        def got_result(result):
            persist = plugin._persist
            mstore = self.broker_service.message_store
            self.assertMessages(mstore.get_pending_messages(), [])
            self.assertFalse(persist.get("users"))
            self.assertFalse(persist.get("groups"))

        self.broker_service.message_store.set_accepted_types(["users"])
        broker_mock = self.mocker.replace(self.monitor.broker)
        broker_mock.send_message(ANY, urgent=True)
        self.mocker.result(fail(RuntimeError()))
        self.mocker.replay()

        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        plugin = UserMonitor(provider=provider)
        self.monitor.add(plugin)
        remote_service = get_object(self.broker_service.bus,
            UserMonitorDBusObject.bus_name, UserMonitorDBusObject.object_path)
        result = remote_service.detect_changes(1001)
        result.addCallback(got_result)

        return result
