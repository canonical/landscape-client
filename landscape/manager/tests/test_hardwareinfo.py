from landscape.tests.helpers import LandscapeTest, ManagerHelper

from landscape.manager.hardwareinfo import HardwareInfo


class HardwareInfoTests(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super(HardwareInfoTests, self).setUp()
        self.info = HardwareInfo()
        self.info.command = "/bin/echo"
        self.manager.add(self.info)

        service = self.broker_service
        service.message_store.set_accepted_types(["hardware-info"])

    def test_message(self):
        """
        L{HardwareInfo} sends the output of its command when running.
        """
        deferred = self.info.send_message()

        def check(ignored):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": u"-xml -quiet\n", "type": "hardware-info"}])

        return deferred.addCallback(check)
