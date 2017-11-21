from landscape.client.tests.helpers import LandscapeTest, ManagerHelper

from landscape.client.manager.hardwareinfo import HardwareInfo


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

    def test_run_upgraded_system(self):
        """
        L{HardwareInfo} sends the output of its command when running on
        a system that has been upgraded to include this plugin, i.e.
        where the client already knows that it can send the
        hardware-info message.
        """
        deferred = self.info.run()

        def check(ignored):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": u"-xml -quiet\n", "type": "hardware-info"}])

        return deferred.addCallback(check)

    def test_only_on_register(self):
        """
        C{call_on_accepted} is only called at register time, to not accumulate
        callbacks to the "message-type-acceptance-changed" event.
        """
        calls = []
        self.info.call_on_accepted = lambda x, y: calls.append((x, y))

        deferred = self.info.run()

        def check(ignored):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [{"data": u"-xml -quiet\n", "type": "hardware-info"}])
            self.assertEqual([], calls)

        return deferred.addCallback(check)
