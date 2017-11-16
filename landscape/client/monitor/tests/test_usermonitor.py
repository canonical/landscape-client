import os

from mock import Mock, ANY
from twisted.internet.defer import fail

from landscape.client.amp import ComponentPublisher
from landscape.client.monitor.usermonitor import (
    UserMonitor, RemoteUserMonitorConnector)
from landscape.client.manager.usermanager import UserManager
from landscape.client.user.tests.helpers import FakeUserProvider
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper
import landscape.client.monitor.usermonitor


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
                [{"create-group-members": {u"webdev": [u"jdoe"]},
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
        # Part of bug 1048576 remediation:
        self._original_USER_UPDATE_FLAG_FILE = (
            landscape.client.monitor.usermonitor.USER_UPDATE_FLAG_FILE)

    def tearDown(self):
        self.publisher.stop()
        self.plugin.stop()
        # Part of bug 1048576 remediation:
        landscape.client.monitor.usermonitor.USER_UPDATE_FLAG_FILE = (
            self._original_USER_UPDATE_FLAG_FILE)
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
        When a C{resynchronize} event, with 'users' scope, occurs any cached
        L{UserChange} snapshots should be cleared and a new message with users
        generated.
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
                [{"create-group-members": {u"webdev": [u"jdoe"]},
                  "create-groups": [{"gid": 1000, "name": u"webdev"}],
                  "create-users": [{"enabled": True, "home-phone": None,
                                    "location": None, "name": u"JD",
                                    "primary-gid": 1000, "uid": 1000,
                                    "username": u"jdoe", "work-phone": None}],
                  "type": "users"}])
        self.broker_service.message_store.delete_all_messages()
        deferred = self.monitor.reactor.fire(
            "resynchronize", scopes=["users"])[0]
        self.successResultOf(deferred)
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"create-group-members": {u"webdev": [u"jdoe"]},
              "create-groups": [{"gid": 1000, "name": u"webdev"}],
              "create-users": [{"enabled": True, "home-phone": None,
                                "location": None, "name": u"JD",
                                "primary-gid": 1000, "uid": 1000,
                                "username": u"jdoe",
                                "work-phone": None}],
              "type": "users"}])

    def test_new_message_after_resynchronize_event(self):
        """
        When a 'resynchronize' reactor event is fired, a new session is
        created and the UserMonitor creates a new message.
        """
        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.broker_service.message_store.set_accepted_types(["users"])
        self.monitor.add(self.plugin)
        self.plugin.client.broker.message_store.drop_session_ids()
        deferred = self.reactor.fire("resynchronize")[0]
        self.successResultOf(deferred)
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"create-group-members": {u"webdev": [u"jdoe"]},
              "create-groups": [{"gid": 1000, "name": u"webdev"}],
              "create-users": [{"enabled": True, "home-phone": None,
                                "location": None, "name": u"JD",
                                "primary-gid": 1000, "uid": 1000,
                                "username": u"jdoe", "work-phone": None}],
              "type": "users"}])

    def test_wb_resynchronize_event_with_global_scope(self):
        """
        When a C{resynchronize} event, with global scope, occurs we act exactly
        as if it had 'users' scope.
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
                [{"create-group-members": {u"webdev": [u"jdoe"]},
                  "create-groups": [{"gid": 1000, "name": u"webdev"}],
                  "create-users": [{"enabled": True, "home-phone": None,
                                    "location": None, "name": u"JD",
                                    "primary-gid": 1000, "uid": 1000,
                                    "username": u"jdoe", "work-phone": None}],
                  "type": "users"}])
        self.broker_service.message_store.delete_all_messages()
        deferred = self.monitor.reactor.fire("resynchronize")[0]
        self.successResultOf(deferred)
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"create-group-members": {u"webdev": [u"jdoe"]},
              "create-groups": [{"gid": 1000, "name": u"webdev"}],
              "create-users": [{"enabled": True, "home-phone": None,
                                "location": None, "name": u"JD",
                                "primary-gid": 1000, "uid": 1000,
                                "username": u"jdoe",
                                "work-phone": None}],
              "type": "users"}])

    def test_do_not_resynchronize_with_other_scope(self):
        """
        When a C{resynchronize} event, with an irrelevant scope, occurs we do
        nothing.
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
                [{"create-group-members": {u"webdev": [u"jdoe"]},
                  "create-groups": [{"gid": 1000, "name": u"webdev"}],
                  "create-users": [{"enabled": True, "home-phone": None,
                                    "location": None, "name": u"JD",
                                    "primary-gid": 1000, "uid": 1000,
                                    "username": u"jdoe", "work-phone": None}],
                  "type": "users"}])
        self.broker_service.message_store.delete_all_messages()
        self.monitor.reactor.fire("resynchronize", scopes=["disk"])[0]
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [])

    def test_run(self):
        """
        The L{UserMonitor} should have message run which should enqueue a
        message with  a diff-like representation of changes since the last
        run.
        """

        def got_result(result):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"create-group-members": {u"webdev": [u"jdoe"]},
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
        self.plugin.run = Mock()

        self.monitor.add(self.plugin)
        self.broker_service.message_store.set_accepted_types(["users"])
        self.reactor.advance(self.plugin.run_interval * 5)

        self.assertEqual(self.plugin.run.call_count, 5)

    def test_run_with_operation_id(self):
        """
        The L{UserMonitor} should have message run which should enqueue a
        message with  a diff-like representation of changes since the last
        run.
        """

        def got_result(result):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"create-group-members": {u"webdev": [u"jdoe"]},
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
                [{"create-group-members": {u"webdev": [u"jdoe"]},
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
                [{"create-group-members": {u"webdev": [u"jdoe"]},
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

    def test_detect_changes_clears_user_provider_if_flag_file_exists(self):
        """
        Temporary bug 1508110 remediation: If a special flag file exists,
        cached user data is dumped and a complete refresh of all user data is
        transmitted.
        """
        self.monitor.add(self.plugin)

        class FauxUserChanges(object):
            cleared = False

            def __init__(self, *args):
                pass

            def create_diff(self):
                return None

            def clear(self):
                self.__class__.cleared = True

        # Create the (temporary, test) user update flag file.
        landscape.client.monitor.usermonitor.USER_UPDATE_FLAG_FILE = \
            update_flag_file = self.makeFile("")
        self.addCleanup(lambda: os.remove(update_flag_file))

        # Trigger a detect changes.
        self.plugin._persist = None
        self.plugin._detect_changes([], UserChanges=FauxUserChanges)

        # The clear() method was called.
        self.assertTrue(FauxUserChanges.cleared)

    def test_detect_changes_deletes_flag_file(self):
        """
        Temporary bug 1508110 remediation: The total user data refresh flag
        file is deleted once the data has been sent.
        """

        def got_result(result):
            # The flag file has been deleted.
            self.assertFalse(os.path.exists(update_flag_file))

        # Create the (temporary, test) user update flag file.
        landscape.client.monitor.usermonitor.USER_UPDATE_FLAG_FILE = \
            update_flag_file = self.makeFile("")

        self.broker_service.message_store.set_accepted_types(["users"])
        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = []

        self.monitor.add(self.plugin)
        connector = RemoteUserMonitorConnector(self.reactor, self.config)
        result = connector.connect()
        result.addCallback(lambda remote: remote.detect_changes())
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
            self.assertMessages(
                mstore.get_pending_messages(),
                [{"create-group-members": {u"webdev": [u"jdoe"]},
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

        self.monitor.broker.send_message = Mock(return_value=fail(
            RuntimeError()))

        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.monitor.add(self.plugin)
        connector = RemoteUserMonitorConnector(self.reactor, self.config)
        result = connector.connect()
        result.addCallback(lambda remote: remote.detect_changes(1001))
        result.addCallback(got_result)
        result.addCallback(lambda x: connector.disconnect())
        self.monitor.broker.send_message.assert_called_once_with(
            ANY, ANY, urgent=True)
