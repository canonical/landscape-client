import os

from landscape.lib.bpickle import dumps
from landscape.tests.mocker import ANY

from landscape.broker.deployment import BrokerConfiguration, BrokerService
from landscape.tests.helpers import (
    LandscapeTest, LandscapeIsolatedTest, FakeRemoteBrokerHelper,
    RemoteBrokerHelper, EnvironSaverHelper)
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
        self.assertFalse(service.registration._cloud)
        self.assertIdentical(service.registration._fetch_async, fetch_async)

        config.cloud = True
        service = FakeBrokerService(config)
        self.assertTrue(service.registration._cloud)


class ConfigurationTests(LandscapeTest):
    helpers = [EnvironSaverHelper]

    def test_loading_sets_http_proxies(self):
        if "http_proxy" in os.environ:
            del os.environ["http_proxy"]
        if "https_proxy" in os.environ:
            del os.environ["https_proxy"]

        configuration = BrokerConfiguration()
        configuration.load(["--http-proxy", "foo",
                            "--https-proxy", "bar",
                            "--url", "whatever"])
        self.assertEquals(os.environ["http_proxy"], "foo")
        self.assertEquals(os.environ["https_proxy"], "bar")

    def test_loading_without_http_proxies_does_not_touch_environment(self):
        os.environ["http_proxy"] = "heyo"
        os.environ["https_proxy"] = "baroo"

        configuration = BrokerConfiguration()
        configuration.load(["--url", "whatever"])
        self.assertEquals(os.environ["http_proxy"], "heyo")
        self.assertEquals(os.environ["https_proxy"], "baroo")

    def test_loading_resets_http_proxies(self):
        """
        User scenario:

        Runs landscape-config, fat-fingers a random character into the
        http_proxy field when he didn't mean to. runs it again, this time
        leaving it blank. The proxy should be reset to whatever
        environment-supplied proxy there was at startup.
        """
        os.environ["http_proxy"] = "original"
        os.environ["https_proxy"] = "originals"

        configuration = BrokerConfiguration()
        configuration.load(["--http-proxy", "x",
                            "--https-proxy", "y",
                            "--url", "whatever"])
        self.assertEquals(os.environ["http_proxy"], "x")
        self.assertEquals(os.environ["https_proxy"], "y")

        configuration.load(["--url", "whatever"])
        self.assertEquals(os.environ["http_proxy"], "original")
        self.assertEquals(os.environ["https_proxy"], "originals")

    def test_intervals_are_ints(self):
        filename = self.makeFile("[client]\n"
                                 "urgent_exchange_interval = 12\n"
                                 "exchange_interval = 34\n")

        configuration = BrokerConfiguration()
        configuration.load(["--config", filename, "--url", "whatever"])

        self.assertEquals(configuration.urgent_exchange_interval, 12)
        self.assertEquals(configuration.exchange_interval, 34)
