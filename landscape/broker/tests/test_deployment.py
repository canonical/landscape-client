from landscape.lib.bpickle import dumps
from landscape.tests.mocker import ANY

from landscape.broker.config import BrokerConfiguration
from landscape.broker.deployment import BrokerService
from landscape.tests.helpers import (
    LandscapeIsolatedTest, FakeRemoteBrokerHelper, RemoteBrokerHelper)
from landscape.reactor import FakeReactor
from landscape.broker.transport import FakeTransport
from landscape.lib.fetch import fetch_async


class DBusTestTest(LandscapeIsolatedTest):

    helpers = [RemoteBrokerHelper]

    def test_session_bus(self):
        """
        Deploying the broker should start a MessageExchange listener
        on the session bus.
        """
        service = self.broker_service
        self.assertTrue(service.bus.get_object(service.dbus_object.bus_name,
                                               service.dbus_object.object_path,
                                               introspect=False))


class DeploymentTest(LandscapeIsolatedTest):
    # Ideally most of these tests won't need to be isolated.  But since the
    # deployment.BrokerService listens on DBUS unconditionally during
    # startService(),
    # we need them to be for now.

    helpers = [FakeRemoteBrokerHelper]

    def test_pinger(self):
        """
        The BrokerDBusObject sets up an active pinger which will cause
        exchanges to occur.
        """
        patched_fetch = self.mocker.replace("landscape.lib.fetch.fetch")

        # The FakeRemoteBrokerHelper defines this URL in the configuration
        patched_fetch("http://localhost:91910/", post=True,
                      data="insecure_id=42", headers=ANY)
        self.mocker.result(dumps({"messages": True}))
        self.mocker.count(2)

        self.mocker.replay()
        self.broker_service.identity.insecure_id = 42
        self.broker_service.startService()
        # 30 is the default interval between pings, and 60 is the urgent
        # exchange interval.  If we wait 60 seconds, we should get 2
        # pings and one exchange.
        self.broker_service.reactor.advance(60)
        self.assertEquals(len(self.broker_service.transport.payloads), 1)

    def test_post_exit_event_will_stop_reactor(self):
        reactor_mock = self.mocker.replace("twisted.internet.reactor")
        reactor_mock.stop()
        self.mocker.replay()

        self.broker_service.reactor.fire("post-exit")

    def test_registration_instantiation(self):

        class MyBrokerConfiguration(BrokerConfiguration):
            default_config_filenames = [self.config_filename]

        config = MyBrokerConfiguration()
        config.load(["--bus", "session", "--data-path", self.data_path])

        class FakeBrokerService(BrokerService):
            """A broker which uses a fake reactor and fake transport."""
            reactor_factory = FakeReactor
            transport_factory = FakeTransport

        self.assertFalse(config.cloud)
        service = FakeBrokerService(config)
        self.assertFalse(service.registration._config.cloud)
        self.assertIdentical(service.registration._fetch_async, fetch_async)

        config.cloud = True
        service = FakeBrokerService(config)
        self.assertTrue(service.registration._config.cloud)
