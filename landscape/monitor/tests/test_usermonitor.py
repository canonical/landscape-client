from twisted.internet.defer import fail

from landscape.amp import ComponentPublisher
from landscape.monitor.usermonitor import (
    UserMonitor, RemoteUserMonitorConnector)
from landscape.manager.usermanager import UserManager
from landscape.user.tests.helpers import FakeUserProvider
from landscape.tests.helpers import LandscapeTest, MonitorHelper
from landscape.tests.mocker import ANY


class UserMonitorNoManagerTest(LandscapeTest):

    helpers = [MonitorHelper]

    def test_no_fetch_users_in_monitor_only_mode(self):
        """
        If we're in monitor_only mode, then all users are assumed to be
        unlocked.
        """
        self.config.monitor_only = True

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
            plugin.stop()

        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        plugin = UserMonitor(provider=provider)
        plugin.register(self.monitor)
        self.broker_service.message_store.set_accepted_types(["users"])
        result = plugin.run()
        result.addCallback(got_result)
        return result


class UserMonitorTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super(UserMonitorTest, self).setUp()
        self.shadow_file = self.makeFile(
            "jdoe:$1$xFlQvTqe$cBtrNEDOIKMy/BuJoUdeG0:13348:0:99999:7:::\n"
            "psmith:!:13348:0:99999:7:::\n"
            "sam:$1$q7sz09uw$q.A3526M/SHu8vUb.Jo1A/:13349:0:99999:7:::\n")
        self.user_manager = UserManager(shadow_file=self.shadow_file)
        self.publisher = ComponentPublisher(self.user_manager, self.reactor,
                                            self.config)
        self.publisher.start()
        self.provider = FakeUserProvider()
        self.plugin = UserMonitor(self.provider)

    def tearDown(self):
        self.publisher.stop()
        self.plugin.stop()
        return super(UserMonitorTest, self).tearDown()

    def test_constants(self):
        """
        L{UserMonitor.persist_name} and
        L{UserMonitor.run_interval} need to be present for
        L{Plugin} to work properly.
        """
        self.assertEqual(self.plugin.persist_name, "users")
        self.assertEqual(self.plugin.run_interval, 3600)

    def test_wb_resynchronize_event(self):
        """
        When a C{resynchronize} event occurs any cached L{UserChange}
        snapshots should be cleared and a new message with users generated.
        """
        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.broker_service.message_store.set_accepted_types(["users"])
        self.monitor.add(self.plugin)
        self.successResultOf(self.plugin.run())

        persist = self.plugin._persist
        self.assertTrue(persist.get("users"))
        self.assertTrue(persist.get("groups"))
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"create-group-members": {u"webdev":[u"jdoe"]},
              "create-groups": [{"gid": 1000, "name": u"webdev"}],
              "create-users": [{"enabled": True, "home-phone": None,
                                "location": None, "name": u"JD",
                                "primary-gid": 1000, "uid": 1000,
                                "username": u"jdoe", "work-phone": None}],
              "type": "users"}])

        # Clear all the messages from the message store
        self.broker_service.message_store.delete_all_messages()

        self.monitor.reactor.fire("resynchronize")

        self.successResultOf(self.plugin.run())
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"create-group-members": {u"webdev":[u"jdoe"]},
              "create-groups": [{"gid": 1000, "name": u"webdev"}],
              "create-users": [{"enabled": True, "home-phone": None,
                                "location": None, "name": u"JD",
                                "primary-gid": 1000, "uid": 1000,
                                "username": u"jdoe",
                                "work-phone": None}],
              "type": "users"}])

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

        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.broker_service.message_store.set_accepted_types(["users"])
        self.monitor.add(self.plugin)
        result = self.plugin.run()
        result.addCallback(got_result)
        return result

    def test_run_interval(self):
        """
        L{UserMonitor.register} calls the C{register} method on it's
        super class, which sets up a looping call to run the plugin
        every L{UserMonitor.run_interval} seconds.
        """
        self.plugin.run = self.mocker.mock()
        self.expect(self.plugin.run()).count(5)
        self.mocker.replay()
        self.monitor.add(self.plugin)

        self.broker_service.message_store.set_accepted_types(["users"])
        self.reactor.advance(self.plugin.run_interval * 5)

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

        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.monitor.add(self.plugin)
        self.broker_service.message_store.set_accepted_types(["users"])
        result = self.plugin.run(1001)
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
        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]

        self.monitor.add(self.plugin)
        connector = RemoteUserMonitorConnector(self.reactor, self.config)
        result = connector.connect()
        result.addCallback(lambda remote: remote.detect_changes())
        result.addCallback(got_result)
        result.addCallback(lambda x: connector.disconnect())
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
        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.monitor.add(self.plugin)
        connector = RemoteUserMonitorConnector(self.reactor, self.config)
        result = connector.connect()
        result.addCallback(lambda remote: remote.detect_changes(1001))
        result.addCallback(got_result)
        result.addCallback(lambda x: connector.disconnect())
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
        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.monitor.add(self.plugin)
        connector = RemoteUserMonitorConnector(self.reactor, self.config)
        result = connector.connect()
        result.addCallback(lambda remote: remote.detect_changes(1001))
        result.addCallback(got_result)
        result.addCallback(lambda x: connector.disconnect())
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

        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.monitor.add(self.plugin)

        self.broker_service.message_store.set_accepted_types(["users"])
        result = self.reactor.fire(
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
            persist = self.plugin._persist
            mstore = self.broker_service.message_store
            self.assertMessages(mstore.get_pending_messages(), [])
            self.assertFalse(persist.get("users"))
            self.assertFalse(persist.get("groups"))

        self.broker_service.message_store.set_accepted_types(["users"])
        self.monitor.broker.send_message = self.mocker.mock()
        self.monitor.broker.send_message(ANY, ANY, urgent=True)
        self.mocker.result(fail(RuntimeError()))
        self.mocker.replay()

        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                       "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.monitor.add(self.plugin)
        connector = RemoteUserMonitorConnector(self.reactor, self.config)
        result = connector.connect()
        result.addCallback(lambda remote: remote.detect_changes(1001))
        result.addCallback(got_result)
        result.addCallback(lambda x: connector.disconnect())
        return result
