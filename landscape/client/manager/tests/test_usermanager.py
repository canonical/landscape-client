# -*- coding: utf-8 -*-
import os
from mock import Mock

from landscape.lib.persist import Persist
from landscape.lib.twisted_util import gather_results
from landscape.client.manager.plugin import SUCCEEDED, FAILED
from landscape.client.monitor.usermonitor import UserMonitor
from landscape.client.manager.usermanager import (
    UserManager, RemoteUserManagerConnector)
from landscape.client.user.tests.helpers import (
        FakeUserProvider, FakeUserManagement)
from landscape.client.tests.helpers import LandscapeTest, ManagerHelper
from landscape.client.user.provider import UserManagementError


class UserGroupTestBase(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(UserGroupTestBase, self).setUp()
        self.shadow_file = self.makeFile("""\
jdoe:$1$xFlQvTqe$cBtrNEDOIKMy/BuJoUdeG0:13348:0:99999:7:::
psmith:!:13348:0:99999:7:::
sbarnes:$1$q7sz09uw$q.A3526M/SHu8vUb.Jo1A/:13349:0:99999:7:::
""")
        accepted_types = ["operation-result", "users"]
        self.broker_service.message_store.set_accepted_types(accepted_types)

    def tearDown(self):
        super(UserGroupTestBase, self).tearDown()
        for plugin in self.plugins:
            plugin.stop()

    def setup_environment(self, users, groups, shadow_file):
        provider = FakeUserProvider(users=users, groups=groups,
                                    shadow_file=shadow_file)
        user_monitor = UserMonitor(provider=provider)
        management = FakeUserManagement(provider=provider)
        user_manager = UserManager(management=management,
                                   shadow_file=shadow_file)
        self.manager.persist = Persist()
        user_monitor.register(self.manager)
        user_manager.register(self.manager)
        self.plugins = [user_monitor, user_manager]
        return user_monitor


class UserOperationsMessagingTest(UserGroupTestBase):

    def test_add_user_event(self):
        """
        When an C{add-user} event is received the user should be
        added.  Two messages should be generated: a C{users} message
        with details about the change and an C{operation-result} with
        details of the outcome of the operation.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertMessages(messages,
                                [{"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 123, "timestamp": 0,
                                  "result-text": "add_user succeeded"},
                                 {"timestamp": 0, "type": "users",
                                  "operation-id": 123,
                                  "create-users": [{"home-phone": None,
                                                    "username": "jdoe",
                                                    "uid": 1000,
                                                    "enabled": True,
                                                    "location": "Room 101",
                                                    "work-phone": "+12345",
                                                    "name": u"John Doe",
                                                    "primary-gid": 1000}]}])

        self.setup_environment([], [], None)

        result = self.manager.dispatch_message(
            {"username": "jdoe", "name": "John Doe", "password": "password",
             "operation-id": 123, "require-password-reset": False,
             "primary-group-name": None, "location": "Room 101",
             "work-number": "+12345", "home-number": None,
             "type": "add-user"})

        result.addCallback(handle_callback)
        return result

    def test_add_user_event_utf8(self):
        """
        When an C{add-user} event with utf-8 unicode strings is received the
        user should be added.
        """
        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertMessages(messages,
                                [{"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 123, "timestamp": 0,
                                  "result-text": "add_user succeeded"},
                                 {"timestamp": 0, "type": "users",
                                  "operation-id": 123,
                                  "create-users": [{"home-phone": None,
                                                    "username": "jdoe",
                                                    "uid": 1000,
                                                    "enabled": True,
                                                    "location": "Room 101",
                                                    "work-phone": "+12345",
                                                    "name": u"請不要刪除",
                                                    "primary-gid": 1000}]}])

        self.setup_environment([], [], None)

        result = self.manager.dispatch_message(
            {"username": "jdoe", "name": "請不要刪除", "password": "password",
             "operation-id": 123, "require-password-reset": False,
             "primary-group-name": None, "location": "Room 101",
             "work-number": "+12345", "home-number": None,
             "type": "add-user"})

        result.addCallback(handle_callback)
        return result

    def test_add_user_event_utf8_wire_data(self):
        """
        When an C{add-user} event with utf-8 decoded unicode string is
        received the user should be added. This is what the server is
        sending over the wire in the real-world.
        """
        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertMessages(messages,
                                [{"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 123, "timestamp": 0,
                                  "result-text": "add_user succeeded"},
                                 {"timestamp": 0, "type": "users",
                                  "operation-id": 123,
                                  "create-users": [
                                      {"home-phone": u"請不要刪除",
                                       "username": u"請不要刪除",
                                       "uid": 1000,
                                       "enabled": True,
                                       "location": u"請不要刪除",
                                       "work-phone": u"請不要刪除",
                                       "name": u"請不要刪除",
                                       "primary-gid": 1000}]}])

        self.setup_environment([], [], None)

        result = self.manager.dispatch_message(
            {'username': u'\u8acb\u4e0d\u8981\u522a\u9664',
             'work-number': u'\u8acb\u4e0d\u8981\u522a\u9664',
             'home-number': u'\u8acb\u4e0d\u8981\u522a\u9664',
             'name': u'\u8acb\u4e0d\u8981\u522a\u9664',
             'operation-id': 123,
             'require-password-reset': False,
             'password': u'\u8acb\u4e0d\u8981\u522a\u9664',
             'type': 'add-user',
             'primary-group-name': u'\u8acb\u4e0d\u8981\u522a\u9664',
             'location': u'\u8acb\u4e0d\u8981\u522a\u9664'})

        result.addCallback(handle_callback)
        return result

    def test_failing_add_user_event(self):
        """
        When an C{add-user} event is received the user should be
        added. If not enough information is provided, we expect a single error,
        containing details of the failure.
        """
        self.log_helper.ignore_errors(KeyError)

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertMessages(messages,
                                [{"type": "operation-result", "status": FAILED,
                                  "operation-id": 123, "timestamp": 0,
                                  "result-text": "KeyError: 'username'"}])

        self.setup_environment([], [], None)

        result = self.manager.dispatch_message(
            {"name": "John Doe", "password": "password", "operation-id": 123,
             "require-password-reset": False, "type": "add-user"})
        result.addCallback(handle_callback)
        return result

    def test_add_user_event_in_sync(self):
        """
        The client and server should be in sync after an C{add-user}
        event is received and processed.  In other words, a snapshot
        should have been taken after the operation was handled.
        """

        def handle_callback1(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertTrue(messages)
            result = plugin.run()
            result.addCallback(handle_callback2, messages)
            return result

        def handle_callback2(result, messages):
            message_store = self.broker_service.message_store
            new_messages = message_store.get_pending_messages()
            self.assertEqual(messages, new_messages)
            return result

        plugin = self.setup_environment([], [], None)
        result = self.manager.dispatch_message(
            {"username": "jdoe", "name": "John Doe", "password": "password",
             "operation-id": 123, "require-password-reset": False,
             "primary-group-name": None, "type": "add-user",
             "location": None, "home-number": "+123456", "work-number": None})

        result.addCallback(handle_callback1)
        return result

    def test_add_user_event_with_external_changes(self):
        """
        If external user changes have been made but not detected by
        the client before an C{add-user} event is received, the client
        should first detect changes and then perform the operation.
        The results should be reported in separate messages.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            messages = [messages[0], messages[2]]
            self.assertMessages(messages,
                                [{"type": "users",
                                  "create-users": [{"home-phone": None,
                                                    "name": "Bo",
                                                    "username": "bo",
                                                    "uid": 1000,
                                                    "enabled": True,
                                                    "location": None,
                                                    "primary-gid": 1000,
                                                    "work-phone": None}]},
                                 {"type": "users", "operation-id": 123,
                                  "create-users": [{"home-phone": "+123456",
                                                    "username": "jdoe",
                                                    "uid": 1001,
                                                    "enabled": True,
                                                    "location": None,
                                                    "work-phone": None,
                                                    "name": "John Doe",
                                                    "primary-gid": 1001}]}])

        users = [("bo", "x", 1000, 1000, "Bo,,,,", "/home/bo", "/bin/zsh")]
        self.setup_environment(users, [], None)
        result = self.manager.dispatch_message(
            {"username": "jdoe", "name": "John Doe", "password": "password",
             "operation-id": 123, "require-password-reset": False,
             "type": "add-user", "primary-group-name": None,
             "location": None, "work-number": None, "home-number": "+123456"})
        result.addCallback(handle_callback)
        return result

    def test_edit_user_event(self):
        """
        When a C{edit-user} message is received the user should be
        updated.  Two messages should be generated: a C{users} message
        with details about the change and an C{operation-result} with
        details of the outcome of the operation.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            # Ignore the message created by plugin.run.
            self.assertMessages(messages[1:],
                                [{"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 99, "timestamp": 0,
                                  "result-text": "set_user_details succeeded"},
                                 {"update-users": [{"username": "jdoe",
                                                    "uid": 1001,
                                                    "enabled": True,
                                                    "work-phone": "789WORK",
                                                    "home-phone": "123HOME",
                                                    "location": "Everywhere",
                                                    "name": "John Doe",
                                                    "primary-gid": 1001}],
                                    "timestamp": 0, "type": "users",
                                  "operation-id": 99}])

        users = [("jdoe", "x", 1001, 1000, "John Doe,,,,",
                  "/home/bo", "/bin/zsh")]
        groups = [("users", "x", 1001, [])]
        self.setup_environment(users, groups, None)
        result = self.manager.dispatch_message(
            {"uid": 1001, "username": "jdoe", "password": "password",
             "name": "John Doe", "location": "Everywhere",
             "work-number": "789WORK", "home-number": "123HOME",
             "operation-id": 99, "primary-group-name": u"users",
             "type": "edit-user"})
        result.addCallback(handle_callback)
        return result

    def test_edit_user_event_in_sync(self):
        """
        The client and server should be in sync after a C{edit-user}
        event is received and processed.  In other words, a snapshot
        should have been taken after the operation was handled.
        """

        def handle_callback1(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertTrue(messages)
            result = plugin.run()
            result.addCallback(handle_callback2, messages)
            return result

        def handle_callback2(result, messages):
            mstore = self.broker_service.message_store
            new_messages = mstore.get_pending_messages()
            self.assertEqual(messages, new_messages)
            return result

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,",
                  "/home/bo", "/bin/zsh")]
        plugin = self.setup_environment(users, [], None)
        result = self.manager.dispatch_message(
            {"username": "jdoe", "password": "password", "name": "John Doe",
             "location": "Everywhere", "work-number": "789WORK",
             "home-number": "123HOME", "primary-group-name": None,
             "type": "edit-user", "operation-id": 99})
        result.addCallback(handle_callback1)
        return result

    def test_edit_user_event_with_external_changes(self):
        """
        If external user changes have been made but not detected by
        the client before a C{edit-user} event is received, the client
        should first detect changes and then perform the operation.
        The results should be reported in separate messages.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            self.assertMessages([messages[0], messages[2]],
                                [{"type": "users",
                                  "create-group-members": {u"users":
                                                           [u"jdoe"]},
                                  "create-groups": [{"gid": 1001,
                                                     "name": u"users"}],
                                  "create-users": [{"home-phone": None,
                                                    "work-phone": None,
                                                    "username": "jdoe",
                                                    "uid": 1000,
                                                    "enabled": True,
                                                    "location": None,
                                                    "name": "John Doe",
                                                    "primary-gid": 1000}]},
                                 {"type": "users", "operation-id": 99,
                                  "update-users": [{"username": "jdoe",
                                                    "uid": 1000,
                                                    "enabled": True,
                                                    "work-phone": "789WORK",
                                                    "home-phone": "123HOME",
                                                    "location": "Everywhere",
                                                    "primary-gid": 1001,
                                                    "name": "John Doe"}]}])

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/home/bo",
                  "/bin/zsh")]
        groups = [("users", "x", 1001, ["jdoe"])]
        self.setup_environment(users, groups, None)
        result = self.manager.dispatch_message(
            {"username": "jdoe", "password": "password", "name": "John Doe",
             "location": "Everywhere", "work-number": "789WORK",
             "home-number": "123HOME", "primary-group-name": u"users",
             "type": "edit-user", "operation-id": 99})
        result.addCallback(handle_callback)
        return result

    def test_remove_user_event(self):
        """
        When a C{remove-user} event is received, with the
        C{delete-home} parameter set to C{True}, the user and her home
        directory should be removed.  Two messages should be
        generated: a C{users} message with details about the change
        and an C{operation-result} with details of the outcome of the
        operation.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            # Ignore the message created by plugin.run.
            self.assertMessages([messages[2], messages[1]],
                                [{"timestamp": 0, "delete-users": ["jdoe"],
                                  "type": "users", "operation-id": 39},
                                 {"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 39, "timestamp": 0,
                                  "result-text": "remove_user succeeded"}])

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/home/bo",
                  "/bin/zsh")]
        self.setup_environment(users, [], None)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "delete-home": True,
             "type": "remove-user",
             "operation-id": 39})
        result.addCallback(handle_callback)
        return result

    def test_many_remove_user_events(self):
        """
        The L{UserManager} can handle multiple remove-user events at the same
        time.
        """
        users = [("foo", "x", 1000, 1000, "Foo,,,,", "/home/foo", "/bin/zsh"),
                 ("bar", "x", 1001, 1001, "Bar,,,,", "/home/bar", "/bin/zsh")]
        self.setup_environment(users, [], None)

        def handle_callback(ignored):
            messages = self.broker_service.message_store.get_pending_messages()
            # Ignore the message created by plugin.run.
            messages = sorted([messages[1], messages[3]],
                              key=lambda message: message["operation-id"])
            self.assertMessages(messages,
                                [{"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 39, "timestamp": 0,
                                  "result-text": "remove_user succeeded"},
                                 {"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 40, "timestamp": 0,
                                  "result-text": "remove_user succeeded"}])

        results = []
        results.append(self.manager.dispatch_message({"username": "foo",
                                                      "delete-home": True,
                                                      "type": "remove-user",
                                                      "operation-id": 39}))
        results.append(self.manager.dispatch_message({"username": "bar",
                                                      "delete-home": True,
                                                      "type": "remove-user",
                                                      "operation-id": 40}))
        return gather_results(results).addCallback(handle_callback)

    def test_failing_remove_user_event(self):
        """
        When a C{remove-user} event is received, and the user doesn't exist, we
        expect a single message with the failure message.
        """
        self.log_helper.ignore_errors(UserManagementError)

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 1)
            failure_string = "UserManagementError: remove_user failed"
            self.assertMessages(messages,
                                [{"type": "operation-result", "status": FAILED,
                                  "operation-id": 39, "timestamp": 0,
                                  "result-text": failure_string}])

        self.setup_environment([], [], None)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "delete-home": True,
             "type": "remove-user",
             "operation-id": 39})
        result.addCallback(handle_callback)
        return result

    def test_remove_user_event_leave_home(self):
        """
        When a C{remove-user} event is received, with the
        C{delete-home} parameter set to C{False}, the user should be
        removed without deleting the user's home directory.  Two
        messages should be generated: a C{users} message with details
        about the change and an C{operation-result} with details of
        the outcome of the operation.
        """

        def handle_callback(result):
            messages = (
                self.broker_service.message_store.get_pending_messages())
            self.assertEqual(len(messages), 3)
            # Ignore the message created by plugin.run.
            self.assertMessages([messages[2], messages[1]],
                                [{"timestamp": 0, "delete-users": ["jdoe"],
                                  "type": "users", "operation-id": 39},
                                 {"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 39, "timestamp": 0,
                                  "result-text": "remove_user succeeded"}])

        users = [("jdoe", "x", 1000, 1000,
                  "John Doe,,,,", "/home/bo", "/bin/zsh")]
        self.setup_environment(users, [], None)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "delete-home": False,
             "type": "remove-user",
             "operation-id": 39})
        result.addCallback(handle_callback)
        return result

    def test_remove_user_event_in_sync(self):
        """
        The client and server should be in sync after a C{remove-user}
        event is received and processed.  In other words, a snapshot
        should have been taken after the operation was handled.
        """

        def handle_callback1(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertTrue(messages)
            result = plugin.run()
            result.addCallback(handle_callback2, messages)
            return result

        def handle_callback2(result, messages):
            message_store = self.broker_service.message_store
            new_messages = message_store.get_pending_messages()
            self.assertEqual(messages, new_messages)

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/home/bo",
                  "/bin/zsh")]
        plugin = self.setup_environment(users, [], self.shadow_file)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "delete-home": True,
             "type": "remove-user",
             "operation-id": 39})
        result.addCallback(handle_callback1)
        return result

    def test_remove_user_event_with_external_changes(self):
        """
        If external user changes have been made but not detected by
        the client before a C{remove-user} event is received, the
        client should first detect changes and then perform the
        operation.  The results should be reported in separate
        messages.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            self.assertMessages([messages[0], messages[2]],
                                [{"type": "users",
                                  "create-users": [{"home-phone": None,
                                                    "username": "jdoe",
                                                    "uid": 1000,
                                                    "enabled": True,
                                                    "location": None,
                                                    "work-phone": None,
                                                    "primary-gid": 1000,
                                                    "name": "John Doe"}]},
                                 {"type": "users",
                                  "delete-users": ["jdoe"],
                                  "operation-id": 39}])

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/home/bo",
                  "/bin/zsh")]
        self.setup_environment(users, [], None)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "delete-home": True,
             "type": "remove-user",
             "operation-id": 39})
        result.addCallback(handle_callback)
        return result

    def test_lock_user_event(self):
        """
        When a C{lock-user} event is received the user should be
        locked out.  Two messages should be generated: a C{users}
        message with details about the change and an
        C{operation-result} with details of the outcome of the
        operation.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3, messages)
            # Ignore the message created by plugin.run.
            self.assertMessages([messages[2], messages[1]],
                                [{"timestamp": 0, "type": "users",
                                  "operation-id": 99,
                                  "update-users": [{"home-phone": None,
                                                    "username": "jdoe",
                                                    "uid": 1000,
                                                    "enabled": False,
                                                    "location": None,
                                                    "work-phone": None,
                                                    "primary-gid": 1000,
                                                    "name": u"John Doe"}]},
                                 {"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 99, "timestamp": 0,
                                  "result-text": "lock_user succeeded"}])

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/home/bo",
                  "/bin/zsh")]
        self.setup_environment(users, [], self.shadow_file)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "operation-id": 99,
             "type": "lock-user"})
        result.addCallback(handle_callback)
        return result

    def test_failing_lock_user_event(self):
        """
        When a C{lock-user} event is received the user should be
        locked out.  However, if the user doesn't exist in the user database,
        we expect only a single failure message to be generated.
        """
        self.log_helper.ignore_errors(UserManagementError)

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 1)
            failure_string = "UserManagementError: lock_user failed"
            self.assertMessages(messages,
                                [{"type": "operation-result",
                                  "status": FAILED,
                                  "operation-id": 99, "timestamp": 0,
                                  "result-text": failure_string}])

        self.setup_environment([], [], None)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "operation-id": 99,
             "type": "lock-user"})
        result.addCallback(handle_callback)
        return result

    def test_lock_user_event_in_sync(self):
        """
        The client and server should be in sync after a C{lock-user}
        event is received and processed.  In other words, a snapshot
        should have been taken after the operation was handled.
        """

        def handle_callback1(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertTrue(messages)
            result = plugin.run()
            result.addCallback(handle_callback2, messages)
            return result

        def handle_callback2(result, messages):
            message_store = self.broker_service.message_store
            new_messages = message_store.get_pending_messages()
            self.assertEqual(messages, new_messages)

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/home/bo",
                  "/bin/zsh")]
        plugin = self.setup_environment(users, [], self.shadow_file)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "type": "lock-user",
             "operation-id": 99})
        result.addCallback(handle_callback1)
        return result

    def test_lock_user_event_with_external_changes(self):
        """
        If external user changes have been made but not detected by
        the client before a C{lock-user} event is received, the client
        should first detect changes and then perform the operation.
        The results should be reported in separate messages.
        """
        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            self.assertMessages([messages[0], messages[2]],
                                [{"type": "users",
                                  "create-users": [{"home-phone": None,
                                                    "username": "jdoe",
                                                    "uid": 1000,
                                                    "enabled": True,
                                                    "location": None,
                                                    "work-phone": None,
                                                    "primary-gid": 1000,
                                                    "name": "John Doe"}]},
                                 {"type": "users", "operation-id": 99,
                                  "update-users": [{"home-phone": None,
                                                    "username": "jdoe",
                                                    "uid": 1000,
                                                    "enabled": False,
                                                    "location": None,
                                                    "work-phone": None,
                                                    "primary-gid": 1000,
                                                    "name": "John Doe"}]}])

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/home/bo",
                  "/bin/zsh")]
        self.setup_environment(users, [], self.shadow_file)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "type": "lock-user",
             "operation-id": 99})
        result.addCallback(handle_callback)
        return result

    def test_unlock_user_event(self):
        """
        When an C{unlock-user} event is received the user should be
        enabled.  Two messages should be generated: a C{users} message
        with details about the change and an C{operation-result} with
        details of the outcome of the operation.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            # Ignore the message created by plugin.run.
            self.assertMessages([messages[2], messages[1]],
                                [{"timestamp": 0, "type": "users",
                                  "operation-id": 99,
                                  "update-users": [{"home-phone": None,
                                                    "username": "psmith",
                                                    "uid": 1000,
                                                    "enabled": True,
                                                    "location": None,
                                                    "work-phone": None,
                                                    "primary-gid": 1000,
                                                    "name": u"Paul Smith"}]},
                                 {"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 99, "timestamp": 0,
                                  "result-text": "unlock_user succeeded"}])

        users = [("psmith", "x", 1000, 1000, "Paul Smith,,,,", "/home/psmith",
                  "/bin/zsh")]
        self.setup_environment(users, [], self.shadow_file)

        result = self.manager.dispatch_message(
            {"username": "psmith",
             "type": "unlock-user",
             "operation-id": 99})
        result.addCallback(handle_callback)
        return result

    def test_failing_unlock_user_event(self):
        """
        When an C{unlock-user} event is received the user should be
        enabled.  However, when the user doesn't exist in the user database, an
        error should be generated.
        """
        self.log_helper.ignore_errors(UserManagementError)

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 1)
            failure_string = "UserManagementError: unlock_user failed"
            self.assertMessages(messages,
                                [{"type": "operation-result",
                                  "status": FAILED,
                                  "operation-id": 99, "timestamp": 0,
                                  "result-text": failure_string}])

        self.setup_environment([], [], None)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "operation-id": 99,
             "type": "unlock-user"})
        result.addCallback(handle_callback)
        return result

    def test_unlock_user_event_in_sync(self):
        """
        The client and server should be in sync after an
        C{unlock-user} event is received and processed.  In other
        words, a snapshot should have been taken after the operation
        was handled.
        """

        def handle_callback(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertTrue(messages)
            result = plugin.run()
            result.addCallback(handle_callback2, messages)
            return result

        def handle_callback2(result, messages):
            message_store = self.broker_service.message_store
            new_messages = message_store.get_pending_messages()
            self.assertEqual(messages, new_messages)

        users = [("psmith", "x", 1000, 1000, "Paul Smith,,,,", "/home/psmith",
                  "/bin/zsh")]
        plugin = self.setup_environment(users, [], self.shadow_file)

        result = self.manager.dispatch_message(
            {"username": "psmith",
             "operation-id": 99,
             "type": "unlock-user"})
        result.addCallback(handle_callback)
        return result

    def test_unlock_user_event_with_external_changes(self):
        """
        If external user changes have been made but not detected by
        the client before a C{unlock-user} event is received, the
        client should first detect changes and then perform the
        operation.  The results should be reported in separate
        messages.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            self.assertMessages([messages[0], messages[2]],
                                [{"type": "users",
                                  "create-users": [{"home-phone": None,
                                                    "username": "psmith",
                                                    "uid": 1000,
                                                    "enabled": False,
                                                    "location": None,
                                                    "work-phone": None,
                                                    "primary-gid": 1000,
                                                    "name": "Paul Smith"}]},
                                 {"type": "users", "operation-id": 99,
                                  "update-users": [{"home-phone": None,
                                                    "username": "psmith",
                                                    "uid": 1000,
                                                    "enabled": True,
                                                    "location": None,
                                                    "work-phone": None,
                                                    "primary-gid": 1000,
                                                    "name": "Paul Smith"}]}])

        users = [("psmith", "x", 1000, 1000, "Paul Smith,,,,", "/home/psmith",
                  "/bin/zsh")]
        self.setup_environment(users, [], self.shadow_file)

        result = self.manager.dispatch_message(
            {"username": "psmith",
             "operation-id": 99,
             "type": "unlock-user"})
        result.addCallback(handle_callback)
        return result


class GroupOperationsMessagingTest(UserGroupTestBase):

    def test_add_group_event(self):
        """
        When an C{add-group} message is received the group should be
        created.  Two messages should be generated: a C{users} message
        with details about the change and an C{operation-result} with
        details of the outcome of the operation.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 2)
            # Ignore the message created by plugin.run.
            self.assertMessages([messages[1], messages[0]],
                                [{"type": "users", "timestamp": 0,
                                  "operation-id": 123,
                                  "create-groups": [{"gid": 1000,
                                                     "name": "bizdev"}]},
                                 {"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 123, "timestamp": 0,
                                  "result-text": "add_group succeeded"}])

        self.setup_environment([], [], None)
        result = self.manager.dispatch_message(
            {"groupname": "bizdev",
             "type": "add-group",
             "operation-id": 123})
        result.addCallback(handle_callback)
        return result

    def test_add_group_event_in_sync(self):
        """
        The client and server should be in sync after an C{add-group}
        event is received and processed.  In other words, a snapshot
        should have been taken after the operation was handled.
        """

        def handle_callback1(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertTrue(messages)
            result = plugin.run()
            result.addCallback(handle_callback2, messages)
            return result

        def handle_callback2(result, messages):
            message_store = self.broker_service.message_store
            new_messages = message_store.get_pending_messages()
            self.assertEqual(messages, new_messages)

        plugin = self.setup_environment([], [], None)
        result = self.manager.dispatch_message(
            {"groupname": "bizdev",
             "operation-id": 123,
             "type": "add-group"})
        result.addCallback(handle_callback1)
        return result

    def test_add_group_event_with_external_changes(self):
        """
        If external user changes have been made but not detected by
        the client before an C{add-group} event is received, the client
        should first detect changes and then perform the operation.
        The results should be reported in separate messages.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            # We skip the operation-result message.
            self.assertMessages([messages[0], messages[2]],
                                [{"type": "users",
                                  "create-groups": [{"gid": 1001,
                                                     "name": "sales"}]},
                                 {"type": "users", "operation-id": 123,
                                  "create-groups": [{"gid": 1002,
                                                     "name": "bizdev"}]}])

        groups = [("sales", "x", 1001, [])]
        self.setup_environment([], groups, None)
        result = self.manager.dispatch_message(
            {"groupname": "bizdev",
             "type": "add-group",
             "operation-id": 123})
        result.addCallback(handle_callback)
        return result

    def test_edit_group_event(self):
        """
        When an C{edit-group} message is received the specified group
        should be edited. This causes the originally named group to be
        removed and replaced with a newly named group with the new name.
        This generates C{users} message with details about the change
        and an C{operation-result} with details of the outcome of the
        operation.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            # Ignore the message created when the initial snapshot was
            # taken before the operation was performed.
            expected = [{"create-groups": [{"gid": 50,
                                            "name": "sales"}],
                         "timestamp": 0,
                         "type": "users"},
                        {"type": "operation-result",
                         "status": SUCCEEDED,
                         "operation-id": 123, "timestamp": 0,
                         "result-text": "set_group_details succeeded"},
                        {"delete-groups": ["sales"],
                         "create-groups": [{"gid": 50,
                                            "name": "bizdev"}],
                         "timestamp": 0,
                         "operation-id": 123,
                         "type": "users"},
                        ]
            self.assertMessages(messages, expected)

        groups = [("sales", "x", 50, [])]
        self.setup_environment([], groups, None)
        result = self.manager.dispatch_message(
            {"groupname": "sales",
             "new-name": "bizdev",
             "type": "edit-group",
             "operation-id": 123})
        result.addCallback(handle_callback)
        return result

    def test_edit_group_event_in_sync(self):
        """
        The client and server should be in sync after an C{edit-group}
        event is received and processed.  In other words, a snapshot
        should have been taken after the operation was handled.
        """

        def handle_callback1(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertTrue(messages)
            result = plugin.run()
            result.addCallback(handle_callback2, messages)
            return result

        def handle_callback2(result, messages):
            message_store = self.broker_service.message_store
            new_messages = message_store.get_pending_messages()
            self.assertEqual(messages, new_messages)

        groups = [("sales", "x", 50, [])]
        plugin = self.setup_environment([], groups, None)
        result = self.manager.dispatch_message(
            {"gid": 50,
             "groupname": "sales",
             "new-name": "bizdev",
             "operation-id": 123,
             "type": "edit-group"})
        result.addCallback(handle_callback1)
        return result

    def test_edit_group_event_with_external_changes(self):
        """
        If external user changes have been made but not detected by
        the client before an C{edit-group} event is received, the
        client should first detect changes and then perform the
        operation.  The results should be reported in separate
        messages.
        """

        def handle_callback1(result):
            result = self.manager.dispatch_message(
                {"groupname": "sales", "new-name": "webdev",
                 "operation-id": 123, "type": "edit-group"})

            result.addCallback(handle_callback2)
            return result

        def handle_callback2(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            self.assertMessages([messages[0], messages[2]],
                                [{"type": "users",
                                  "create-groups": [{"gid": 1001,
                                                     "name": "sales"}]},
                                 {"type": "users",
                                  "operation-id": 123,
                                  "delete-groups": ["sales"],
                                  "create-groups": [{"gid": 1001,
                                                     "name": "webdev"}]}])

        groups = [("sales", "x", 1001, [])]
        plugin = self.setup_environment([], groups, None)
        result = plugin.run()
        result.addCallback(handle_callback1)
        return result

    def test_add_group_member_event(self):
        """
        When an C{add-group-member} message is received the new user
        should be added to the group.  Two messages should be
        generated: a C{users} message with details about the change
        and an C{operation-result} with details of the outcome of the
        operation.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            # Ignore the message created when the initial snapshot was
            # taken before the operation was performed.
            expected = [{"type": "users", "timestamp": 0,
                         "operation-id": 123,
                         "create-group-members": {"bizdev": ["jdoe"]}},
                        {"type": "operation-result",
                         "timestamp": 0,
                         "status": SUCCEEDED,
                         "operation-id": 123,
                         "result-text": "add_group_member succeeded"}]
            self.assertMessages([messages[2], messages[1]], expected)

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/bin/sh",
                  "/home/jdoe")]
        groups = [("bizdev", "x", 1001, [])]
        self.setup_environment(users, groups, None)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "groupname": "bizdev",
             "operation-id": 123,
             "type": "add-group-member"})
        result.addCallback(handle_callback)
        return result

    def test_add_group_member_with_username_and_groupname_event(self):
        """
        When an C{add-group-member} message is received with a
        username and group name, instead of a UID and GID, the new
        user should be added to the group.  Two messages should be
        generated: a C{users} message with details about the change
        and an C{operation-result} with details of the outcome of the
        operation.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            # Ignore the message created when the initial snapshot was
            # taken before the operation was performed.
            expected = [{"type": "users", "timestamp": 0,
                         "operation-id": 123,
                         "create-group-members": {"bizdev": ["jdoe"]}},
                        {"type": "operation-result", "timestamp": 0,
                         "status": SUCCEEDED, "operation-id": 123,
                         "result-text": "add_group_member succeeded"}]
            self.assertMessages([messages[2], messages[1]], expected)

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/bin/sh",
                  "/home/jdoe")]
        groups = [("bizdev", "x", 1001, [])]
        self.setup_environment(users, groups, None)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "groupname": "bizdev",
             "type": "add-group-member",
             "operation-id": 123})
        result.addCallback(handle_callback)
        return result

    def test_add_group_member_event_in_sync(self):
        """
        The client and server should be in sync after an
        C{add-group-member} event is received and processed.  In other
        words, a snapshot should have been taken after the operation
        was handled.
        """

        def handle_callback(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertTrue(messages)
            result = plugin.run()
            result.addCallback(handle_callback2, messages)
            return result

        def handle_callback2(result, messages):
            message_store = self.broker_service.message_store
            new_messages = message_store.get_pending_messages()
            self.assertEqual(messages, new_messages)

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/bin/sh",
                  "/home/jdoe")]
        groups = [("bizdev", "x", 1001, ["jdoe"])]
        plugin = self.setup_environment(users, groups, None)
        result = self.manager.dispatch_message(
            {"username": u"jdoe",
             "groupname": u"bizdev",
             "type": "add-group-member",
             "operation-id": 123})
        result.addCallback(handle_callback)
        return result

    def test_add_group_member_event_with_external_changes(self):
        """
        If external user changes have been made but not detected by
        the client before an C{add-group-member} event is received,
        the client should first detect changes and then perform the
        operation.  The results should be reported in separate
        messages.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            expected = [{"type": "users",
                         "create-users": [{"home-phone": None,
                                           "username": "jdoe",
                                           "uid": 1000,
                                           "enabled": True,
                                           "location": None,
                                           "work-phone": None,
                                           "primary-gid": 1000,
                                           "name": "John Doe"}],
                         "create-groups": [{"gid": 1001,
                                            "name": "bizdev"}]},
                        {"type": "users", "operation-id": 123,
                         "create-group-members": {"bizdev": ["jdoe"]}}]
            self.assertMessages([messages[0], messages[2]], expected)

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/bin/sh",
                  "/home/jdoe")]
        groups = [("bizdev", "x", 1001, [])]
        self.setup_environment(users, groups, None)
        result = self.manager.dispatch_message(
            {"username": "jdoe",
             "groupname": "bizdev",
             "type": "add-group-member",
             "operation-id": 123})
        result.addCallback(handle_callback)
        return result

    def test_remove_group_member_event(self):
        """
        When an C{add-group-member} message is received the user
        should be removed from the group.  Two messages should be
        generated: a C{users} message with details about the change
        and an C{operation-result} with details of the outcome of the
        operation.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            # Ignore the message created by plugin.run.
            self.assertMessages(
                [messages[2], messages[1]],
                [{"type": "users", "timestamp": 0,
                  "operation-id": 123,
                  "delete-group-members": {"bizdev": ["jdoe"]}},
                 {"type": "operation-result",
                  "status": SUCCEEDED,
                  "operation-id": 123, "timestamp": 0,
                  "result-text": "remove_group_member succeeded"}])

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/bin/sh",
                  "/home/jdoe")]
        groups = [("bizdev", "x", 1001, ["jdoe"])]
        self.setup_environment(users, groups, None)
        result = self.manager.dispatch_message(
            {"username": "jdoe", "groupname": "bizdev",
             "type": "remove-group-member", "operation-id": 123})
        result.addCallback(handle_callback)
        return result

    def test_remove_group_member_event_in_sync(self):
        """
        The client and server should be in sync after an
        C{remove-group-member} event is received and processed.  In
        other words, a snapshot should have been taken after the
        operation was handled.
        """

        def handle_callback1(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertTrue(messages)
            result = plugin.run()
            result.addCallback(handle_callback2, messages)
            return result

        def handle_callback2(result, messages):
            message_store = self.broker_service.message_store
            new_messages = message_store.get_pending_messages()
            self.assertEqual(messages, new_messages)

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/bin/sh",
                  "/home/jdoe")]
        groups = [("bizdev", "x", 1001, ["jdoe"])]
        plugin = self.setup_environment(users, groups, None)
        result = self.manager.dispatch_message(
            {"username": "jdoe", "groupname": "bizdev",
             "type": "remove-group-member",
             "operation-id": 123})
        result.addCallback(handle_callback1)
        return result

    def test_remove_group_member_event_with_external_changes(self):
        """
        If external user changes have been made but not detected by
        the client before a C{remove-group-member} event is received,
        the client should first detect changes and then perform the
        operation.  The results should be reported in separate
        messages.
        """

        def handle_callback(result):
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            expected = [{"timestamp": 0, "type": "users",
                         "create-users": [{"home-phone": None,
                                           "username": "jdoe",
                                           "uid": 1000,
                                           "enabled": True,
                                           "location": None,
                                           "work-phone": None,
                                           "primary-gid": 1000,
                                           "name": "John Doe"}],
                         "create-groups": [{"gid": 1001,
                                            "name": "bizdev"}],
                         "create-group-members": {"bizdev": ["jdoe"]}},
                        {"type": "users", "operation-id": 123,
                         "delete-group-members": {"bizdev": ["jdoe"]}}]
            self.assertMessages([messages[0], messages[2]], expected)

        users = [("jdoe", "x", 1000, 1000, "John Doe,,,,", "/bin/sh",
                  "/home/jdoe")]
        groups = [("bizdev", "x", 1001, ["jdoe"])]
        self.setup_environment(users, groups, None)
        result = self.manager.dispatch_message(
            {"groupname": "bizdev",
             "username": "jdoe",
             "type": "remove-group-member",
             "operation-id": 123})
        result.addCallback(handle_callback)
        return result

    def test_remove_group_event(self):
        """
        When a C{remove-group} message is received the specified group
        should be removeed.  Two messages should be generated: a
        C{users} message with details about the change and an
        C{operation-result} with details of the outcome of the
        operation.
        """

        def handle_callback1(result):
            result = self.manager.dispatch_message(
                {"groupname": "sales", "type": "remove-group",
                 "operation-id": 123})

            result.addCallback(handle_callback2)
            return result

        def handle_callback2(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            # Ignore the message created when the initial snapshot was
            # taken before the operation was performed.
            self.assertMessages([messages[2], messages[1]],
                                [{"type": "users", "timestamp": 0,
                                  "operation-id": 123,
                                  "delete-groups": ["sales"]},
                                 {"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 123, "timestamp": 0,
                                  "result-text": "remove_group succeeded"}])

        groups = [("sales", "x", 1001, ["jdoe"])]
        plugin = self.setup_environment([], groups, None)
        result = plugin.run()
        result.addCallback(handle_callback1)
        return result

    def test_remove_group_event_in_sync(self):
        """
        The client and server should be in sync after a
        C{remove-group} event is received and processed.  In other
        words, a snapshot should have been taken after the operation
        was handled.
        """

        def handle_callback1(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertTrue(messages)
            result = plugin.run()
            result.addCallback(handle_callback2, messages)
            return result

        def handle_callback2(result, messages):
            message_store = self.broker_service.message_store
            new_messages = message_store.get_pending_messages()
            self.assertEqual(messages, new_messages)

        groups = [("sales", "x", 50, [])]
        plugin = self.setup_environment([], groups, None)
        result = self.manager.dispatch_message(
            {"groupname": "sales",
             "operation-id": 123,
             "type": "remove-group"})
        result.addCallback(handle_callback1)
        return result

    def test_remove_group_event_with_external_changes(self):
        """
        If external user changes have been made but not detected by
        the client before a C{remove-group} event is received, the
        client should first detect changes and then perform the
        operation.  The results should be reported in separate
        messages.
        """

        def handle_callback1(result):
            result = self.manager.dispatch_message(
                {"groupname": "sales", "operation-id": 123,
                 "type": "remove-group"})
            result.addCallback(handle_callback2)
            return result

        def handle_callback2(result):
            message_store = self.broker_service.message_store
            messages = message_store.get_pending_messages()
            self.assertEqual(len(messages), 3)
            self.assertMessages([messages[0], messages[2]],
                                [{"type": "users",
                                  "create-groups": [{"gid": 1001,
                                                     "name": "sales"}]},
                                 {"type": "users",
                                  "delete-groups": ["sales"],
                                  "operation-id": 123}])

        groups = [("sales", "x", 1001, [])]
        plugin = self.setup_environment([], groups, None)
        result = plugin.run()
        result.addCallback(handle_callback1)
        return result


class UserManagerTest(LandscapeTest):

    def setUp(self):
        super(UserManagerTest, self).setUp()
        self.shadow_file = self.makeFile()
        self.user_manager = UserManager(shadow_file=self.shadow_file)

    def test_get_locked_usernames(self):
        """
        The L{UserManager.get_locked_usernames} method returns only user names
        of locked users.
        """
        fd = open(self.shadow_file, "w")
        fd.write("jdoe:$1$xFlQvTqe$cBtrNEDOIKMy/BuJoUdeG0:13348:0:99999:7:::\n"
                 "psmith:!:13348:0:99999:7:::\n"
                 "yo:$1$q7sz09uw$q.A3526M/SHu8vUb.Jo1A/:13349:0:99999:7:::\n")
        fd.close()
        self.assertEqual(self.user_manager.get_locked_usernames(), ["psmith"])

    def test_get_locked_usernames_with_empty_shadow_file(self):
        """
        The L{UserManager.get_locked_usernames} method returns an empty C{list}
        if the shadow file is empty.
        """
        fd = open(self.shadow_file, "w")
        fd.write("\n")
        fd.close()
        self.assertEqual(self.user_manager.get_locked_usernames(), [])

    def test_get_locked_usernames_with_non_existing_shadow_file(self):
        """
        The L{UserManager.get_locked_usernames} method returns an empty C{list}
        if the shadow file can't be read.  An error message is logged as well.
        """
        self.log_helper.ignore_errors("Error reading shadow file.*")
        self.assertFalse(os.path.exists(self.shadow_file))
        self.assertEqual(self.user_manager.get_locked_usernames(), [])
        self.assertIn("Error reading shadow file. [Errno 2] No such file or "
                      "directory", self.logfile.getvalue())


class RemoteUserManagerTest(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(RemoteUserManagerTest, self).setUp()

        def set_remote(remote):
            self.remote_user_manager = remote

        self.shadow_file = self.makeFile()
        self.user_manager = UserManager(shadow_file=self.shadow_file)
        self.user_manager_connector = RemoteUserManagerConnector(self.reactor,
                                                                 self.config)
        self.user_manager.register(self.manager)
        connected = self.user_manager_connector.connect()
        return connected.addCallback(set_remote)

    def tearDown(self):
        self.user_manager_connector.disconnect()
        self.user_manager.stop()
        return super(RemoteUserManagerTest, self).tearDown()

    def test_get_locked_usernames(self):
        """
        The L{get_locked_usernames} method forwards the request to the
        remote L{UserManager} object.
        """
        self.user_manager.get_locked_usernames = Mock(return_value=["fred"])
        deferred = self.remote_user_manager.get_locked_usernames()
        result = self.successResultOf(deferred)
        self.assertEqual(result, ['fred'])
        self.user_manager.get_locked_usernames.assert_called_once_with()
