from twisted.internet.defer import fail

from landscape.monitor.usermonitor import UserMonitor, RemoteUserMonitorCreator
from landscape.manager.usermanager import UserManager, UserManagerFactory
from landscape.user.tests.helpers import FakeUserProvider
from landscape.tests.helpers import (
    LandscapeTest, MonitorHelper_, RemoteBrokerHelper_)
from landscape.tests.mocker import ANY


class UserMonitorNoManagerTest(LandscapeTest):

    helpers = [MonitorHelper_, RemoteBrokerHelper_]

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

        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        plugin = UserMonitor(provider=provider)
        plugin.register(self.monitor)
        plugin._port.stopListening()
        self.broker_service.message_store.set_accepted_types(["users"])
        result = plugin.run()
        result.addCallback(got_result)
        return result


class UserMonitorTest(LandscapeTest):

    helpers = [MonitorHelper_, RemoteBrokerHelper_]

    def setUp(self):

        def add(ignored):
            self.shadow_file = self.makeFile(
                "jdoe:$1$xFlQvTqe$cBtrNEDOIKMy/BuJoUdeG0:13348:0:99999:7:::\n"
                "psmith:!:13348:0:99999:7:::\n"
                "sam:$1$q7sz09uw$q.A3526M/SHu8vUb.Jo1A/:13349:0:99999:7:::\n")
            self.user_manager = UserManager(shadow_file=self.shadow_file)
            reactor = self.reactor._reactor
            factory = UserManagerFactory(reactor, self.user_manager)
            socket = self.config.user_manager_socket_filename
            self.port = self.reactor._reactor.listenUNIX(socket, factory)
            self.provider = FakeUserProvider()
            self.plugin = UserMonitor(self.provider)

        super_setup = super(UserMonitorTest, self).setUp()
        return super_setup.addCallback(add)

    def tearDown(self):
        self.port.stopListening()
        if hasattr(self.plugin, "_port"):
            self.plugin._port.stopListening()
        return super(UserMonitorTest, self).tearDown()

    def test_constants(self):
        """
        L{UserMonitor.persist_name} and
        L{UserMonitor.run_interval} need to be present for
        L{Plugin} to work properly.
        """
        self.assertEquals(self.plugin.persist_name, "users")
        self.assertEquals(self.plugin.run_interval, 3600)

    def test_wb_resynchronize_event(self):
        """
        When a C{resynchronize} event occurs any cached L{UserChange}
        snapshots should be cleared and a new message with users generated.
        """

        def resynchronize_complete(result, plugin):

            def resynchronization_new_messages(result):
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

            persist = plugin._persist
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
            deferred = self.monitor.reactor.fire("resynchronize")[0]
            deferred.addCallback(resynchronization_new_messages)
            return deferred

        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                                "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.broker_service.message_store.set_accepted_types(["users"])
        self.monitor.add(self.plugin)
        deferred = self.plugin.run()
        deferred.addCallback(resynchronize_complete, self.plugin)
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
        creator = RemoteUserMonitorCreator(self.reactor, self.config)
        result = creator.connect()
        result.addCallback(lambda remote: remote.detect_changes())
        result.addCallback(got_result)
        result.addCallback(lambda x: creator.disconnect())
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
        creator = RemoteUserMonitorCreator(self.reactor, self.config)
        result = creator.connect()
        result.addCallback(lambda remote: remote.detect_changes(1001))
        result.addCallback(got_result)
        result.addCallback(lambda x: creator.disconnect())
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
        creator = RemoteUserMonitorCreator(self.reactor, self.config)
        result = creator.connect()
        result.addCallback(lambda remote: remote.detect_changes(1001))
        result.addCallback(got_result)
        result.addCallback(lambda x: creator.disconnect())
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
        self.monitor.broker.send_message(ANY, urgent=True)
        self.mocker.result(fail(RuntimeError()))
        self.mocker.replay()

        self.provider.users = [("jdoe", "x", 1000, 1000, "JD,,,,",
                       "/home/jdoe", "/bin/sh")]
        self.provider.groups = [("webdev", "x", 1000, ["jdoe"])]
        self.monitor.add(self.plugin)
        creator = RemoteUserMonitorCreator(self.reactor, self.config)
        result = creator.connect()
        result.addCallback(lambda remote: remote.detect_changes(1001))
        result.addCallback(got_result)
        result.addCallback(lambda x: creator.disconnect())
        return result
