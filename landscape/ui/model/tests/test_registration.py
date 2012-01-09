from landscape.configuration import register
from landscape.reactor import TwistedReactor
from landscape.sysvconfig import SysVConfig
from landscape.tests.helpers import LandscapeTest, BrokerServiceHelper
from landscape.tests.mocker import ANY
from landscape.ui.model.registration import ObservableRegistration
from landscape.ui.model.configuration import LandscapeSettingsConfiguration


class RegistrationTest(LandscapeTest):

    helpers = [BrokerServiceHelper]

    def setUp(self):
        super(RegistrationTest, self).setUp()

    def test_register(self):
        observable_registration = ObservableRegistration()
        service = self.broker_service
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        register_mock = self.mocker.replace(register, passthrough=False)
        self.mocker.order()
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        register_mock(ANY, ANY, ANY)
        self.mocker.replay()
        observable_registration.register(service.config)
