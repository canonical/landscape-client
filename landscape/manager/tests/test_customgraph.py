import os
import pwd

from twisted.internet.error import ProcessDone
from twisted.python.failure import Failure

from landscape.manager.customgraph import CustomGraphPlugin
from landscape.manager.store import ManagerStore

from landscape.tests.helpers import (
    LandscapeTest, ManagerHelper, StubProcessFactory, DummyProcess)
from landscape.tests.mocker import ANY


class CustomGraphManagerTests(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super(CustomGraphManagerTests, self).setUp()
        self.store = ManagerStore(":memory:")
        self.manager.store = self.store
        self.broker_service.message_store.set_accepted_types(
            ["custom-graph"])
        self.data_path = self.make_dir()
        self.manager.config.data_path = self.data_path
        self.manager.config.script_users = "ALL"
        self.graph_manager = CustomGraphPlugin(
            create_time=range(1500, 0, -300).pop)
        self.manager.add(self.graph_manager)

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

        self.assertEquals(
            self.store.get_graphs(),
            [(123,
              os.path.join(self.data_path, "custom-graph-scripts",
                           "graph-123"),
              username)])

    def test_add_graph_for_user(self):
        mock_chown = self.mocker.replace("os.chown", passthrough=False)
        mock_chown(ANY, 1234, 5678)

        mock_chmod = self.mocker.replace("os.chmod", passthrough=False)
        mock_chmod(ANY, 0777)
        mock_chmod(ANY, 0700)

        mock_getpwnam = self.mocker.replace("pwd.getpwnam", passthrough=False)
        class pwnam(object):
            pw_uid = 1234
            pw_gid = 5678
            pw_dir = self.make_path()

        self.expect(mock_getpwnam("bar")).result(pwnam)
        self.mocker.replay()
        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo hi!",
                     "username": "bar",
                     "graph-id": 123})
        self.assertEquals(
            self.store.get_graphs(),
            [(123, os.path.join(self.data_path, "custom-graph-scripts",
                                "graph-123"),
                   "bar")])

    def test_remove_unknown_graph(self):
        self.manager.dispatch_message(
            {"type": "custom-graph-remove",
                     "graph-id": 123})

    def test_remove_graph(self):
        filename = self.makeFile()
        tempfile = file(filename, "w")
        tempfile.write("foo")
        tempfile.close()
        self.store.add_graph(123, filename, u"user")
        self.manager.dispatch_message(
            {"type": "custom-graph-remove",
                     "graph-id": 123})
        self.assertFalse(os.path.exists(filename))

    def test_run(self):
        filename = self.makeFile()
        tempfile = file(filename, "w")
        tempfile.write("#!/bin/sh\necho 1")
        tempfile.close()
        os.chmod(filename, 0777)
        self.store.add_graph(123, filename, None)
        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data":
                      {123: {"error": u"",
                             "values": [(300, 1.0)],
                             "script-hash": "483f2304b49063680c75e3c9e09cf6d0"
                            }
                      },
                  "type": "custom-graph"}])
        return self.graph_manager.run().addCallback(check)

    def test_run_cast_result_error(self):
        self.store.add_graph(123, "foo", None)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        self.graph_manager._get_script_hash = lambda x: "md5"
        result = self.graph_manager.run()

        self.assertEquals(len(factory.spawns), 1)
        spawn = factory.spawns[0]
        self.assertEquals(spawn[1], "foo")

        protocol = spawn[0]
        protocol.childDataReceived(1, "foobar")
        for fd in (0, 1, 2):
            protocol.childConnectionLost(fd)
        protocol.processEnded(Failure(ProcessDone(0)))

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data":
                      {123: {"error":
                          u"ValueError: invalid literal for float(): foobar",
                             "values": [], "script-hash": "md5"}},
                  "type": "custom-graph"}])
        return result.addCallback(check)

    def test_run_user(self):
        self.store.add_graph(123, "foo", "bar")
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        self.graph_manager._get_script_hash = lambda x: "md5"

        mock_getpwnam = self.mocker.replace("pwd.getpwnam", passthrough=False)
        class pwnam(object):
            pw_uid = 1234
            pw_gid = 5678
            pw_dir = self.make_path()

        self.expect(mock_getpwnam("bar")).result(pwnam)
        self.mocker.replay()

        result = self.graph_manager.run()

        self.assertEquals(len(factory.spawns), 1)
        spawn = factory.spawns[0]
        self.assertEquals(spawn[1], "foo")
        self.assertEquals(spawn[2], ())
        self.assertEquals(spawn[3], {})
        self.assertEquals(spawn[4], "/")
        self.assertEquals(spawn[5], 1234)
        self.assertEquals(spawn[6], 5678)

        protocol = spawn[0]
        protocol.childDataReceived(1, "spam")
        for fd in (0, 1, 2):
            protocol.childConnectionLost(fd)
        protocol.processEnded(Failure(ProcessDone(0)))

        return result

    def test_run_dissallowed_user(self):
        uid = os.getuid()
        info = pwd.getpwuid(uid)
        username = info.pw_name
        self.manager.config.script_users = "foo"

        self.store.add_graph(123, "foo", username)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        self.graph_manager._get_script_hash = lambda x: "md5"
        result = self.graph_manager.run()

        self.assertEquals(len(factory.spawns), 0)

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {123:
                      {"error":
                          u"Custom graph cannot be run as user %s." %
                          (username,),
                       "script-hash": "md5",
                       "values": []}},
                  "type": "custom-graph"}])

        return result.addCallback(check)

    def test_run_timeout(self):
        self.store.add_graph(123, "foo", None)
        factory = StubProcessFactory()
        self.graph_manager.process_factory = factory
        self.graph_manager._get_script_hash = lambda x: "md5"
        result = self.graph_manager.run()

        self.assertEquals(len(factory.spawns), 1)
        spawn = factory.spawns[0]
        protocol = spawn[0]
        protocol.makeConnection(DummyProcess())
        self.assertEquals(spawn[1], "foo")

        self.manager.reactor.advance(110)
        protocol.processEnded(Failure(ProcessDone(0)))

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": {123: {"error":
                                    u"Process exceed the 10 seconds limit",
                                "script-hash": "md5",
                                "values": []}},
                  "type": "custom-graph"}])

        return result.addCallback(check)

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
            [{"api": "3.1",
              "data": {123: {"error": u"",
                             "script-hash": "e00a2f44dbc7b6710ce32af2348aec9b",
                             "values": []}},
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
        self.graph_manager._get_script_hash = lambda x: 1/0
        self.graph_manager.do_send = True
        self.graph_manager.exchange()
        self.assertMessages(
            self.broker_service.message_store.get_pending_messages(),
            [{"api": "3.1",
              "data": {123: {"error": u"",
                             "script-hash": "e00a2f44dbc7b6710ce32af2348aec9b",
                             "values": []}},
              "timestamp": 0,
              "type": "custom-graph"},
             {"api": "3.1",
              "data": {123: {"error": u"",
                             "script-hash": "e00a2f44dbc7b6710ce32af2348aec9b",
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
            [{"api": "3.1",
              "data": {123: {"error": u"",
                             "script-hash": "e00a2f44dbc7b6710ce32af2348aec9b",
                             "values": []}},
              "timestamp": 0,
              "type": "custom-graph"},
             {"api": "3.1",
              "data": {123: {"error": u"",
                             "script-hash": "d483816dc0fbb51ede42502a709b0e2a",
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

        self.assertEquals(len(factory.spawns), 1)
        spawn = factory.spawns[0]

        self.manager.dispatch_message(
            {"type": "custom-graph-add",
                     "interpreter": "/bin/sh",
                     "code": "echo 2.0",
                     "username": username,
                     "graph-id": 123})

        protocol = spawn[0]
        protocol.childDataReceived(1, "1.0")
        for fd in (0, 1, 2):
            protocol.childConnectionLost(fd)
        protocol.processEnded(Failure(ProcessDone(0)))

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"api": "3.1",
                  "data": {123: {"error": u"",
                                 "script-hash": "991e15a81929c79fe1d243b2afd99c62",
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

        self.assertEquals(len(factory.spawns), 1)
        spawn = factory.spawns[0]

        self.manager.dispatch_message(
            {"type": "custom-graph-remove",
                     "graph-id": 123})

        protocol = spawn[0]
        protocol.childDataReceived(1, "1.0")
        for fd in (0, 1, 2):
            protocol.childConnectionLost(fd)
        protocol.processEnded(Failure(ProcessDone(0)))

        def check(ignore):
            self.graph_manager.exchange()
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"api": "3.1", "data": {}, "timestamp": 0, "type":
                  "custom-graph"}])
        return result.addCallback(check)
