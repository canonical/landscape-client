import os
import pwd
import logging

import mock

from twisted.internet.error import ProcessDone
from twisted.python.failure import Failure

from landscape.client.manager.customgraph import CustomGraphPlugin
from landscape.client.manager.store import ManagerStore

from landscape.lib.testing import StubProcessFactory, DummyProcess
from landscape.client.tests.helpers import LandscapeTest, ManagerHelper


class CustomGraphManagerTests(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(CustomGraphManagerTests, self).setUp()
        self.store = ManagerStore(":memory:")
        self.manager.store = self.store
        self.broker_service.message_store.set_accepted_types(
            ["custom-graph"])
        self.data_path = self.makeDir()
        self.manager.config.data_path = self.data_path
        os.makedirs(os.path.join(self.data_path, "custom-graph-scripts"))
        self.manager.config.script_users = "ALL"
        self.graph_manager = CustomGraphPlugin(
            create_time=list(range(1500, 0, -300)).pop)
        self.manager.add(self.graph_manager)

    def _exit_process_protocol(self, protocol, stdout):
        protocol.childDataReceived(1, stdout)
        for fd in (0, 1, 2):
            protocol.childConnectionLost(fd)
        protocol.processEnded(Failure(ProcessDone(0)))

    def test_add_graph(self):
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo hi!",
                     "username": username,
                     "graph-id": 123})

        self.assertEqual(
            self.store.get_graphs(),
            [(123,
              os.path.join(self.data_path, "custom-graph-scripts",
                           "graph-123"),
              username)])

    @mock.patch("pwd.getpwnam")
    def test_add_graph_unknown_user(self, mock_getpwnam):
        """
        Attempting to add a graph with an unknown user should not result in an
        error, instead a message should be logged, the error will be picked up
        when the graph executes.
        """
        mock_getpwnam.side_effect = KeyError("foo")
        error_message = "Attempt to add graph with unknown user foo"
        self.log_helper.ignore_errors(error_message)
        self.logger.setLevel(logging.ERROR)

        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo hi!",
                     "username": "foo",
                     "graph-id": 123})
        graph = self.store.get_graph(123)
        self.assertEqual(graph[0], 123)
        self.assertEqual(graph[2], u"foo")
        self.assertTrue(error_message in self.logfile.getvalue())
        mock_getpwnam.assert_called_with("foo")

    @mock.patch("os.chown")
    @mock.patch("os.chmod")
    @mock.patch("pwd.getpwnam")
    def test_add_graph_for_user(self, mock_getpwnam, mock_chmod, mock_chown):

        class pwnam(object):
            pw_uid = 1234
            pw_gid = 5678
            pw_dir = self.makeFile()

        mock_getpwnam.return_value = pwnam

        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo hi!",
                     "username": "bar",
                     "graph-id": 123})
        self.assertEqual(
            self.store.get_graphs(),
            [(123,
              os.path.join(self.data_path, "custom-graph-scripts",
                           "graph-123"),
              "bar")])

        mock_chown.assert_called_with(mock.ANY, 1234, 5678)
        mock_chmod.assert_called_with(mock.ANY, 0o700)
        mock_getpwnam.assert_called_with("bar")

    def test_remove_unknown_graph(self):
        self.manager.dispatch_message(
            {"type": "custom-graph-remove",
                     "graph-id": 123})

    def test_remove_graph(self):
        filename = self.makeFile(content='foo')
        self.store.add_graph(123, filename, u"user")
        self.manager.dispatch_message(
            {"type": "custom-graph-remove",
                     "graph-id": 123})
        self.assertFalse(os.path.exists(filename))

    def test_run(self):
        filename = self.makeFile(content="#!/bin/sh\necho 1")
        os.chmod(filename, 0o777)
        self.store.add_graph(123, filename, None)

        def check(ignore):
            self.graph_manager.exchange()
            script_hash = b"483f2304b49063680c75e3c9e09cf6d0"
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {123: {"error": u"",
                                 "values": [(300, 1.0)],
                                 "script-hash": script_hash}},
                  "type": "custom-graph"}])
        return self.graph_manager.run().addCallback(check)

    def test_run_multiple(self):
        filename = self.makeFile(content="#!/bin/sh\necho 1")
        os.chmod(filename, 0o777)
        self.store.add_graph(123, filename, None)

        filename = self.makeFile(content="#!/bin/sh\necho 2")
        os.chmod(filename, 0o777)
        self.store.add_graph(124, filename, None)

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {
                      123: {"error": u"",
                            "values": [(300, 1.0)],
                            "script-hash": b"483f2304b49063680c75e3c9e09cf6d0",
                            },
                      124: {"error": u"",
                            "values": [(300, 2.0)],
                            "script-hash": b"73a74b1530b2256db7edacb9b9cc385e",
                            },
                      },
                  "type": "custom-graph"}])
        return self.graph_manager.run().addCallback(check)

    def test_run_with_nonzero_exit_code(self):
        filename = self.makeFile(content="#!/bin/sh\nexit 1")
        os.chmod(filename, 0o777)
        self.store.add_graph(123, filename, None)

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {
                    123: {
                        "error": u" (process exited with code 1)",
                        "values": [],
                        "script-hash": b"eaca3ba1a3bf1948876eba320148c5e9",
                        }
                    },
                  "type": "custom-graph"}])
        return self.graph_manager.run().addCallback(check)

    def test_run_cast_result_error(self):
        filename = self.makeFile("some_content")
        self.store.add_graph(123, filename, None)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 1)
        spawn = factory.spawns[0]
        self.assertEqual(spawn[1], filename)

        self._exit_process_protocol(spawn[0], b"foobar")

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {
                    123: {
                        "error": (u"InvalidFormatError: Failed to convert to "
                                  u"number: 'foobar'"),
                        "values": [],
                        "script-hash": b"baab6c16d9143523b7865d46896e4596",
                        },
                    },
                  "type": "custom-graph"}])
        return result.addCallback(check)

    def test_run_no_output_error(self):
        filename = self.makeFile("some_content")
        self.store.add_graph(123, filename, None)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 1)
        spawn = factory.spawns[0]
        self.assertEqual(spawn[1], filename)

        self._exit_process_protocol(spawn[0], b"")

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {
                    123: {
                        "error": (u"NoOutputError: Script did not output "
                                  u"any value"),
                        "values": [],
                        "script-hash": b"baab6c16d9143523b7865d46896e4596",
                        },
                    },
                  "type": "custom-graph"}])
        return result.addCallback(check)

    def test_run_no_output_error_with_other_result(self):
        filename1 = self.makeFile("some_content")
        self.store.add_graph(123, filename1, None)
        filename2 = self.makeFile("some_content")
        self.store.add_graph(124, filename2, None)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 2)
        spawn = factory.spawns[0]
        self._exit_process_protocol(spawn[0], b"")
        spawn = factory.spawns[1]
        self._exit_process_protocol(spawn[0], b"0.5")

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {
                      123: {
                          "error": (u"NoOutputError: Script did not output "
                                    u"any value"),
                          "script-hash": b"baab6c16d9143523b7865d46896e4596",
                          "values": []},
                      124: {
                          "error": u"",
                          "script-hash": b"baab6c16d9143523b7865d46896e4596",
                          "values": [(300, 0.5)]},
                      },
                  "type": "custom-graph"}])
        return result.addCallback(check)

    def test_multiple_errors(self):
        filename1 = self.makeFile("some_content")
        self.store.add_graph(123, filename1, None)
        filename2 = self.makeFile("some_content")
        self.store.add_graph(124, filename2, None)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 2)
        spawn = factory.spawns[0]
        self._exit_process_protocol(spawn[0], b"foo")
        spawn = factory.spawns[1]
        self._exit_process_protocol(spawn[0], b"")

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {
                      123: {
                          "error": (u"InvalidFormatError: Failed to convert "
                                    u"to number: 'foo'"),
                          "script-hash": b"baab6c16d9143523b7865d46896e4596",
                          "values": []},
                      124: {
                          "error": (u"NoOutputError: Script did not output "
                                    u"any value"),
                          "script-hash": b"baab6c16d9143523b7865d46896e4596",
                          "values": []},
                      },
                  "type": "custom-graph"}])
        return result.addCallback(check)

    @mock.patch("pwd.getpwnam")
    def test_run_user(self, mock_getpwnam):
        filename = self.makeFile("some content")
        self.store.add_graph(123, filename, "bar")
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory

        class pwnam(object):
            pw_uid = 1234
            pw_gid = 5678
            pw_dir = self.makeFile()

        mock_getpwnam.return_value = pwnam

        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 1)
        spawn = factory.spawns[0]
        self.assertEqual(spawn[1], filename)
        self.assertEqual(spawn[2], (filename,))
        self.assertEqual(spawn[3], {})
        self.assertEqual(spawn[4], "/")
        self.assertEqual(spawn[5], 1234)
        self.assertEqual(spawn[6], 5678)
        mock_getpwnam.assert_called_with("bar")

        self._exit_process_protocol(spawn[0], b"spam")

        return result

    def test_run_dissallowed_user(self):
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        self.manager.config.script_users = "foo"

        self.store.add_graph(123, "filename", username)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 0)

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {
                    123: {
                        "error": (u"ProhibitedUserError: Custom graph cannot "
                                  u"be run as user %s") % (username,),
                        "script-hash": b"",
                        "values": []},
                    },
                  "type": "custom-graph"}])

        return result.addCallback(check)

    @mock.patch("pwd.getpwnam")
    def test_run_unknown_user(self, mock_getpwnam):
        mock_getpwnam.side_effect = KeyError("foo")

        self.manager.config.script_users = "foo"

        self.store.add_graph(123, "filename", "foo")
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 0)

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {
                    123: {
                        "error": u"UnknownUserError: Unknown user 'foo'",
                        "script-hash": b"",
                        "values": []},
                    },
                  "type": "custom-graph"}])
            mock_getpwnam.assert_called_with("foo")

        return result.addCallback(check)

    def test_run_timeout(self):
        filename = self.makeFile("some content")
        self.store.add_graph(123, filename, None)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 1)
        spawn = factory.spawns[0]
        protocol = spawn[0]
        protocol.makeConnection(DummyProcess())
        self.assertEqual(spawn[1], filename)

        self.manager.reactor.advance(110)
        protocol.processEnded(Failure(ProcessDone(0)))

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {
                    123: {
                        "error": u"Process exceeded the 10 seconds limit",
                        "script-hash": b"9893532233caff98cd083a116b013c0b",
                        "values": []},
                    },
                  "type": "custom-graph"}])

        return result.addCallback(check)

    def test_run_removed_file(self):
        """
        If run is called on a script file that has been removed, it doesn't try
        to run it, but report it with an empty hash value.
        """
        self.store.add_graph(123, "/nonexistent", None)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 0)

        self.graph_manager.exchange()
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"data": {123: {"error": u"", "script-hash": b"", "values": []}},
              "type": "custom-graph"}])

    def test_send_message_add_stored_graph(self):
        """
        C{send_message} send the graph with no data, to notify the server of
        the existence of the script, even if the script hasn't been run yet.
        """
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo hi!",
                     "username": username,
                     "graph-id": 123})
        self.graph_manager.exchange()
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"api": b"3.2",
              "data": {123: {"error": u"",
                             "script-hash":
                                 b"e00a2f44dbc7b6710ce32af2348aec9b",
                             "values": []}},
              "timestamp": 0,
              "type": "custom-graph"}])

    def test_send_message_check_not_present_graph(self):
        """C{send_message} checks the presence of the custom-graph script."""
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo hi!",
                     "username": username,
                     "graph-id": 123})
        filename = self.store.get_graph(123)[1]
        os.unlink(filename)
        self.graph_manager.exchange()
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"api": b"3.2",
              "data": {},
              "timestamp": 0,
              "type": "custom-graph"}])

    def test_send_message_dont_rehash(self):
        """
        C{send_message} uses hash already stored if still no data has been
        found.
        """
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo hi!",
                     "username": username,
                     "graph-id": 123})
        self.graph_manager.exchange()
        self.graph_manager._get_script_hash = lambda x: 1 / 0
        self.graph_manager.do_send = True
        self.graph_manager.exchange()
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"api": b"3.2",
              "data": {123: {"error": u"",
                             "script-hash":
                                 b"e00a2f44dbc7b6710ce32af2348aec9b",
                             "values": []}},
              "timestamp": 0,
              "type": "custom-graph"},
             {"api": b"3.2",
              "data": {123: {"error": u"",
                             "script-hash":
                                 b"e00a2f44dbc7b6710ce32af2348aec9b",
                             "values": []}},
              "timestamp": 0,
              "type": "custom-graph"}])

    def test_send_message_rehash_if_necessary(self):
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo hi!",
                     "username": username,
                     "graph-id": 123})
        self.graph_manager.exchange()
        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo bye!",
                     "username": username,
                     "graph-id": 123})
        self.graph_manager.do_send = True
        self.graph_manager.exchange()
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"api": b"3.2",
              "data": {123: {"error": u"",
                             "script-hash":
                                 b"e00a2f44dbc7b6710ce32af2348aec9b",
                             "values": []}},
              "timestamp": 0,
              "type": "custom-graph"},
             {"api": b"3.2",
              "data": {123: {"error": u"",
                             "script-hash":
                                 b"d483816dc0fbb51ede42502a709b0e2a",
                             "values": []}},
              "timestamp": 0,
              "type": "custom-graph"}])

    def test_run_with_script_updated(self):
        """
        If a script is updated while a data point is being retrieved, the data
        point is discarded and no value is sent, but the new script is
        mentioned.
        """
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
             "code": "echo 1.0",
                     "username": username,
                     "graph-id": 123})

        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 1)
        spawn = factory.spawns[0]

        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo 2.0",
                     "username": username,
                     "graph-id": 123})

        self._exit_process_protocol(spawn[0], b"1.0")

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"api": b"3.2",
                  "data": {123: {"error": u"",
                                 "script-hash":
                                     b"991e15a81929c79fe1d243b2afd99c62",
                                 "values": []}},
                  "timestamp": 0,
                  "type": "custom-graph"}])

        return result.addCallback(check)

    def test_run_with_script_removed(self):
        """
        If a script is removed while a data point is being retrieved, the data
        point is discarded and no data is sent at all.
        """
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo 1.0",
                     "username": username,
                     "graph-id": 123})

        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 1)
        spawn = factory.spawns[0]

        self.manager.dispatch_message(
            {"type": "custom-graph-remove",
                     "graph-id": 123})

        self._exit_process_protocol(spawn[0], b"1.0")

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"api": b"3.2", "data": {}, "timestamp": 0, "type":
                  "custom-graph"}])
        return result.addCallback(check)

    def test_run_not_accepted_types(self):
        """
        If "custom-graph" is not an accepted message-type anymore,
        C{CustomGraphPlugin.run} shouldn't even run the graph scripts.
        """
        self.broker_service.message_store.set_accepted_types([])

        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo 1.0",
                     "username": username,
                     "graph-id": 123})

        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 0)

        return result.addCallback(self.assertIdentical, None)

    def test_run_without_graph(self):
        """
        If no graph is available, C{CustomGraphPlugin.run} doesn't even call
        C{call_if_accepted} on the broker and return immediately an empty list
        of results.
        """
        self.graph_manager.registry.broker.call_if_accepted = (
            lambda *args: 1 / 0)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 0)

        return result.addCallback(self.assertEqual, [])

    def test_run_unknown_user_with_unicode(self):
        """
        Using a non-existent user containing unicode characters fails with the
        appropriate error message.
        """
        username = u"non-existent-f\N{LATIN SMALL LETTER E WITH ACUTE}e"

        self.manager.config.script_users = "ALL"

        filename = self.makeFile("some content")
        self.store.add_graph(123, filename, username)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        result = self.graph_manager.run()

        self.assertEqual(len(factory.spawns), 0)

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {
                    123: {
                        "error":
                            u"UnknownUserError: Unknown user '%s'" % username,
                        "script-hash": b"9893532233caff98cd083a116b013c0b",
                        "values": []}},
                  "type": "custom-graph"}])

        return result.addCallback(check)
