from twisted.internet.defer import succeed, fail

from landscape.broker.amp import RemoteClient
from landscape.tests.helpers import (
    LandscapeTest, BrokerServerHelper, DEFAULT_ACCEPTED_TYPES)


class BrokerServerTest(LandscapeTest):

    helpers = [BrokerServerHelper]

    def test_send_message(self):
        """
        The L{BrokerServer.send_message} method forwards a message to the
        broker's exchanger.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        self.broker.send_message(message)
        self.assertMessages(self.mstore.get_pending_messages(),
                            [message])
        self.assertFalse(self.exchanger.is_urgent())

    def test_send_message_with_urgent(self):
        """
        The L{BrokerServer.send_message} can optionally specify the urgency
        of the message.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        self.broker.send_message(message, True)
        self.assertMessages(self.mstore.get_pending_messages(),
                            [message])
        self.assertTrue(self.exchanger.is_urgent())

    def test_is_pending(self):
        """
        The L{BrokerServer.is_pending} method indicates if a message with
        the given id is pending waiting for delivery in the message store.
        """
        self.assertFalse(self.broker.is_message_pending(123))
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        message_id = self.broker.send_message(message)
        self.assertTrue(self.broker.is_message_pending(message_id))

    def test_register_client(self):
        """
        The L{BrokerServer.register_client} method can be used to register
        client components that need to communicate with the server. After
        the registration they can be fetched with L{BrokerServer.get_clients}.
        """
        self.assertEquals(self.broker.get_clients(), [])
        self.broker.register_client("test", None)
        [client] = self.broker.get_clients()
        self.assertTrue(isinstance(client, RemoteClient))
        self.assertEquals(client.name, "test")

    def test_stop_clients(self):
        """
        The L{BrokerServer.stop_clients} method calls the C{exit} method
        of each registered client, and returns a deferred resulting in C{None}
        if all C{exit} calls were successful.
        """
        self.broker.register_client("foo", None)
        self.broker.register_client("bar", None)
        exited_clients = []
        for client in self.broker.get_clients():

            def create_exit_func(client):

                def exit():
                    exited_clients.append(client.name)
                    return succeed(None)
                return exit
            client.exit = create_exit_func(client)

        def assert_result(result):
            self.assertIdentical(result, None)
            self.assertEquals(sorted(exited_clients), ["bar", "foo"])

        clients_stopped = self.broker.stop_clients()
        return clients_stopped.addCallback(assert_result)

    def test_stop_clients_with_failure(self):
        """
        The L{BrokerServer.stop_clients} method calls the C{exit} method
        of each registered client, and returns a deferred resulting in C{None}
        if all C{exit} calls were successful.
        """
        self.broker.register_client("foo", None)
        self.broker.register_client("bar", None)
        for client in self.broker.get_clients():
            if client.name == "foo":
                client.exit = lambda: succeed(None)
            else:
                client.exit = lambda: fail(Exception("bar"))
        clients_stopped = self.broker.stop_clients()
        self.assertFailure(clients_stopped, Exception)

        def assert_error(error):
            self.assertEquals(error.args[0], "bar")

        return clients_stopped.addCallback(assert_error)

    def test_reload_configuration(self):
        """
        The L{BrokerServer.reload_configuration} method forces the config
        file associated with the broker server to be reloaded.
        """
        open(self.config_filename, "a").write("computer_title = New Title")
        config_reloaded = self.broker.reload_configuration()

        def assert_config(result):
            self.assertEquals(self.config.computer_title, "New Title")

        return config_reloaded.addCallback(assert_config)

    def test_reload_configuration_stops_clients(self):
        """
        The L{BrokerServer.reload_configuration} method forces the config
        file associated with the broker server to be reloaded.
        """
        self.broker.register_client("foo", None)
        self.broker.register_client("bar", None)
        exited_clients = []
        for client in self.broker.get_clients():

            def create_exit_func(client):

                def exit():
                    exited_clients.append(client.name)
                    return succeed(None)
                return exit
            client.exit = create_exit_func(client)

        config_reloaded = self.broker.reload_configuration()

        def assert_exited_clients(result):
            self.assertEquals(sorted(exited_clients), ["bar", "foo"])

        return config_reloaded.addCallback(assert_exited_clients)

    def test_register(self):
        """
        The L{BrokerServer.register} method attempts to register with the
        Ladscape server and waits for a C{set-id} message from it.
        """
        registered = self.broker.register()
        # This should callback the deferred.
        self.exchanger.handle_message({"type": "set-id", "id": "abc",
                                       "insecure-id": "def"})
        return registered.addCallback(self.assertEquals, None)

    def test_get_accepted_types_empty(self):
        """
        The L{BrokerServer.get_accepted_message_types} returns an empty list
        if no message types are accepted by the Landscape server.
        """
        self.mstore.set_accepted_types([])
        self.assertEquals(self.broker.get_accepted_message_types(), [])

    def test_get_accepted_message_types(self):
        """
        The L{BrokerServer.get_accepted_message_types} returns the list of
        message types accepted by the Landscape server.
        """
        self.mstore.set_accepted_types(["foo", "bar"])
        self.assertEquals(sorted(self.broker.get_accepted_message_types()),
                          ["bar", "foo"])

    def test_get_server_uuid_with_unset_uuid(self):
        """
        The L{BrokerServer.get_server_uuid} method returns C{None} if the uuid
        of the Landscape server we're pointing at is unknown.
        """
        self.assertEquals(self.broker.get_server_uuid(), None)

    def test_get_server_uuid(self):
        """
        The L{BrokerServer.get_server_uuid} method returns the uuid of the
        Landscape server we're pointing at.
        """
        self.mstore.set_server_uuid("the-uuid")
        self.assertEquals(self.broker.get_server_uuid(), "the-uuid")

    def test_register_client_accepted_message_type(self):
        """
        The L{BrokerServer.register_client_accepted_message_type} method can
        register new message types accepted by this Landscape client.
        """
        self.broker.register_client_accepted_message_type("type1")
        self.broker.register_client_accepted_message_type("type2")
        self.assertEquals(self.exchanger.get_client_accepted_message_types(),
                          sorted(["type1", "type2"] + DEFAULT_ACCEPTED_TYPES))

    def test_exit(self):
        """
        The L{BrokerServer.exit} method stops all registered clients.
        """
        self.broker.register_client("foo", None)
        self.broker.register_client("bar", None)
        exited_clients = []
        for client in self.broker.get_clients():

            def create_exit_func(client):

                def exit():
                    exited_clients.append(client.name)
                    return succeed(None)
                return exit
            client.exit = create_exit_func(client)

        def assert_exited_clients(ignored):
            self.assertEquals(sorted(exited_clients), ["bar", "foo"])

        broker_exited = self.broker.exit()
        return broker_exited.addCallback(assert_exited_clients)

    def test_exit_exits_when_other_daemons_blow_up(self):
        """
        If a broker client blow up in its exit() methods, exit should ignore
        the error and exit anyway.
        """
        self.broker.register_client("foo", None)
        [client] = self.broker.get_clients()
        client_exit_calls = []

        def client_exit():
            client_exit_calls.append(True)
            return fail(ZeroDivisionError())

        client.exit = client_exit

        post_exits = []
        self.reactor.call_on("post-exit", lambda: post_exits.append(True))

        def assert_result(result):
            self.assertEquals(client_exit_calls, [True])
            self.assertEquals(result, None)
            self.assertEquals(post_exits, [True])

        broker_exited = self.broker.exit()
        return broker_exited.addCallback(assert_result)

    def test_exit_fires_reactor_events(self):
        """
        The L{BrokerServer.exit} method fires a C{pre-exit} event before the
        clients are stopped and a C{post-exit} event after.
        """
        self.broker.register_client("foo", None)
        [client] = self.broker.get_clients()
        client_exit_calls = []

        def client_exit():
            client_exit_calls.append(True)
            return fail(ZeroDivisionError())

        client.exit = client_exit

        fired_exit_calls = []

        def pre_exit():
            self.assertEquals(client_exit_calls, [])
            fired_exit_calls.append("pre")

        def post_exit():
            self.assertEquals(client_exit_calls, [True])
            fired_exit_calls.append("post")

        self.reactor.call_on("pre-exit", pre_exit)
        self.reactor.call_on("post-exit", post_exit)

        def assert_exit_calls(result):
            self.assertEquals(fired_exit_calls, ["pre", "post"])

        broker_exited = self.broker.exit()
        return broker_exited.addCallback(assert_exit_calls)
