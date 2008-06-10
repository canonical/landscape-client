from twisted.internet.defer import fail, succeed

from landscape.lib import bpickle_dbus
from landscape.monitor.hardwareinventory import HardwareInventory
from landscape.tests.test_hal import MockHALManager, MockRealHALDevice
from landscape.tests.helpers import LandscapeTest, MonitorHelper
from landscape.tests.mocker import ANY
from landscape.message_schemas import HARDWARE_INVENTORY


class HardwareInventoryTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super(HardwareInventoryTest, self).setUp()
        self.mstore.set_accepted_types(["hardware-inventory"])
        devices = [MockRealHALDevice({u"info.udi": u"wubble",
                                      u"info.product": u"Wubble",}),
                   MockRealHALDevice({u"info.udi": u"ooga",
                                      u"info.product": u"Ooga",})]
        self.hal_manager = MockHALManager(devices)
        self.plugin = HardwareInventory(hal_manager=self.hal_manager)
        self.monitor.add(self.plugin)

    def assertSchema(self, devices):
        full_message = {"type": "hardware-inventory", "devices": devices}
        self.assertEquals(HARDWARE_INVENTORY.coerce(full_message), full_message)

    def test_hal_devices(self):
        """
        The first time the plugin runs it should report information
        about all HAL devices found on the system.  Every UDI provided
        by HAL should be present in the devices list as is from HAL.
        """
        message = self.plugin.create_message()
        actual_udis = [part[1][u"info.udi"] for part in message]
        expected_udis = [device.udi for device
                         in self.hal_manager.get_devices()]
        self.assertEquals(set(actual_udis), set(expected_udis))

    def test_first_message(self):
        """
        The first time the plugin runs it should report information
        about all HAL devices found on the system.  All new devices
        will be reported with 'create' actions.
        """
        message = self.plugin.create_message()
        actions = [part[0] for part in message]
        self.assertEquals(set(actions), set(["create"]))
        self.assertSchema(message)

    def test_no_changes(self):
        """
        Messages should not be created if hardware information is
        unchanged since the last server exchange.
        """
        self.plugin.exchange()
        self.assertNotEquals(len(self.mstore.get_pending_messages()), 0)

        messages = self.mstore.get_pending_messages()
        self.plugin.exchange()
        self.assertEquals(self.mstore.get_pending_messages(), messages)

    def test_update(self):
        """
        If a change is detected for a device that was previously
        reported to the server, the changed device should be reported
        with an 'update' action.  Property changes are reported at a
        key/value pair level.
        """
        self.hal_manager.devices = [
            MockRealHALDevice({u"info.udi": u"wubble",
                               u"info.product": u"Wubble",}),]

        message = self.plugin.create_message()
        self.plugin.persist_data(None)
        self.assertEquals(message, [("create", {u"info.udi": u"wubble",
                                                u"info.product": u"Wubble"}),])

        self.hal_manager.devices[0] = MockRealHALDevice(
            {u"info.udi": u"wubble", u"info.product": u"Ooga",})
        message = self.plugin.create_message()
        self.plugin.persist_data(None)
        self.assertEquals(message, [("update", u"wubble",
                                     {}, {u"info.product": u"Ooga"}, {}),])
        self.assertSchema(message)
        self.assertEquals(self.plugin.create_message(), [])

    def test_update_list(self):
        """
        An update should be sent to the server when a strlist device
        property changes.  No updates should be sent if a device is
        unchanged.
        """
        self.hal_manager.devices = [
            MockRealHALDevice({u"info.udi": u"wubble",
                               u"info.product": u"Wubble",
                               u"info.capabilities": [u"foo", u"bar"]}),]

        message = self.plugin.create_message()
        self.plugin.persist_data(None)
        self.assertEquals(message, [("create",
                                     {u"info.udi": u"wubble",
                                      u"info.product": u"Wubble",
                                      u"info.capabilities": [u"foo", u"bar"]}),
                                    ])

        self.assertSchema(message)

        self.hal_manager.devices[0] = MockRealHALDevice(
            {u"info.udi": u"wubble", u"info.product": u"Wubble",
             u"info.capabilities": [u"foo"]})
        message = self.plugin.create_message()
        self.plugin.persist_data(None)
        self.assertEquals(message, [("update", u"wubble",
                                     {}, {u"info.capabilities": [u"foo"]}, {}),
                                    ])
        self.assertSchema(message)

        self.assertEquals(self.plugin.create_message(), [])

    def test_update_complex(self):
        """
        The 'update' action reports property create, update and
        delete changes.
        """
        self.hal_manager.devices = [
            MockRealHALDevice({u"info.udi": u"wubble",
                               u"info.product": u"Wubble",
                               u"linux.acpi_type": 11}),]

        message = self.plugin.create_message()
        self.plugin.persist_data(None)
        self.assertEquals(message, [("create", {u"info.udi": u"wubble",
                                                u"info.product": u"Wubble",
                                                u"linux.acpi_type": 11}),])

        self.hal_manager.devices[0] = MockRealHALDevice(
            {u"info.udi": u"wubble", u"info.product": u"Ooga",
             u"info.category": u"unittest"})
        message = self.plugin.create_message()
        self.plugin.persist_data(None)
        self.assertEquals(message, [("update", u"wubble",
                                     {u"info.category": u"unittest"},
                                     {u"info.product": u"Ooga"},
                                     {u"linux.acpi_type": 11}),])
        self.assertSchema(message)

        self.assertEquals(self.plugin.create_message(), [])

    def test_delete(self):
        """
        If a device that was previously reported is no longer present
        in a system a device entry should be created with a 'delete'
        action.
        """
        self.hal_manager.devices = [
            MockRealHALDevice({u"info.udi": u"wubble",
                               u"info.product": u"Wubble",}),
            MockRealHALDevice({u"info.udi": u"ooga",
                               u"info.product": u"Ooga",})]

        message = self.plugin.create_message()
        self.plugin.persist_data(None)
        self.assertEquals(message, [("create", {u"info.udi": u"wubble",
                                                u"info.product": u"Wubble"}),
                                    ("create", {u"info.udi": u"ooga",
                                                u"info.product": u"Ooga"}),])
        self.assertSchema(message)

        self.hal_manager.devices.pop(1)
        message = self.plugin.create_message()
        self.plugin.persist_data(None)
        self.assertEquals(message, [("delete", u"ooga"),])
        self.assertSchema(message)
        self.assertEquals(self.plugin.create_message(), [])

    def test_minimal_delete(self):
        self.hal_manager.devices = [
            MockRealHALDevice({u"info.udi": u"wubble",
                               u"block.device": u"/dev/scd",
                               u"storage.removable": True}),
            MockRealHALDevice({u"info.udi": u"wubble0",
                               u"block.device": u"/dev/scd0",
                               u"info.parent": u"wubble"}),
            MockRealHALDevice({u"info.udi": u"wubble1",
                               u"block.device": u"/dev/scd1",
                               u"info.parent": u"wubble"}),
            MockRealHALDevice({u"info.udi": u"wubble2",
                               u"block.device": u"/dev/scd1",
                               u"info.parent": u"wubble0"}),
            MockRealHALDevice({u"info.udi": u"wubble3",
                               u"block.device": u"/dev/scd1",
                               u"info.parent": u"wubble2"}),]

        message = self.plugin.create_message()
        self.plugin.persist_data(None)

        del self.hal_manager.devices[:]

        message = self.plugin.create_message()
        self.plugin.persist_data(None)

        self.assertEquals(message, [("delete", u"wubble"),])
        self.assertEquals(self.plugin.create_message(), [])

    def test_resynchronize(self):
        """
        If a 'resynchronize' reactor event is fired, the plugin should
        send a message that contains all data as if the server has
        none.
        """
        self.plugin.exchange()
        self.reactor.fire("resynchronize")
        self.plugin.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 2)
        self.assertEquals(messages[0]["devices"], messages[1]["devices"])

    def test_call_on_accepted(self):
        remote_broker_mock = self.mocker.replace(self.remote)
        remote_broker_mock.send_message(ANY, urgent=True)
        self.mocker.result(succeed(None))
        self.mocker.replay()

        self.reactor.fire(("message-type-acceptance-changed",
                           "hardware-inventory"),
                          True)

    def test_no_message_if_not_accepted(self):
        """
        Don't add any messages at all if the broker isn't currently
        accepting their type.
        """
        self.mstore.set_accepted_types([])
        self.reactor.advance(self.monitor.step_size * 2)
        self.monitor.exchange()

        self.mstore.set_accepted_types(["hardware-inventory"])
        self.assertMessages(list(self.mstore.get_pending_messages()), [])

    def test_do_not_persist_changes_when_send_message_fails(self):
        """
        When the plugin is run it persists data that it uses on
        subsequent checks to calculate the delta to send.  It should
        only persist data when the broker confirms that the message
        sent by the plugin has been sent.
        """
        class MyException(Exception): pass
        self.log_helper.ignore_errors(MyException)

        broker_mock = self.mocker.replace(self.monitor.broker)
        broker_mock.send_message(ANY, urgent=ANY)
        self.mocker.result(fail(MyException()))
        self.mocker.replay()

        message = self.plugin.create_message()

        def assert_message(message_id):
            self.assertEquals(message, self.plugin.create_message())

        result = self.plugin.exchange()
        result.addCallback(assert_message)
        return result
