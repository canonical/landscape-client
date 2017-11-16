from landscape.client.manager.plugin import SUCCEEDED

from landscape.client.manager.fakepackagemanager import FakePackageManager
from landscape.client.tests.helpers import LandscapeTest, ManagerHelper


class FakePackageManagerTest(LandscapeTest):
    """Tests for the fake package manager plugin."""

    helpers = [ManagerHelper]

    def setUp(self):
        super(FakePackageManagerTest, self).setUp()
        self.package_manager = FakePackageManager()
        self.package_manager.randint = lambda x, y: 0

    def test_handle_change_packages(self):
        """
        L{FakePackageManager} is able to handle a C{change-packages} message,
        creating a C{change-packages-result} in response.
        """
        self.manager.add(self.package_manager)
        service = self.broker_service
        service.message_store.set_accepted_types(["change-packages-result"])
        message = {"type": "change-packages", "operation-id": 1}
        self.manager.dispatch_message(message)
        self.manager.reactor.advance(1)

        self.assertMessages(service.message_store.get_pending_messages(),
                            [{"type": "change-packages-result",
                              "result-text": "OK done.",
                              "result-code": 1, "operation-id": 1}])

    def test_handle_change_package_locks(self):
        """
        L{FakePackageManager} is able to handle a C{change-package-locks}
        message, creating a C{operation-result} in response.
        """
        self.manager.add(self.package_manager)
        service = self.broker_service
        service.message_store.set_accepted_types(["operation-result"])
        message = {"type": "change-package-locks", "operation-id": 1}
        self.manager.dispatch_message(message)
        self.manager.reactor.advance(1)

        self.assertMessages(service.message_store.get_pending_messages(),
                            [{"type": "operation-result",
                              "result-text":
                                  "Package locks successfully changed.",
                              "result-code": 0, "status": SUCCEEDED,
                              "operation-id": 1}])

    def test_handle_release_upgrade(self):
        """
        L{FakePackageManager} is able to handle a C{release-upgrade} message,
        creating a C{operation-result} in response.
        """
        self.manager.add(self.package_manager)
        service = self.broker_service
        service.message_store.set_accepted_types(["operation-result"])
        message = {"type": "release-upgrade", "operation-id": 1}
        self.manager.dispatch_message(message)
        self.manager.reactor.advance(1)

        self.assertMessages(service.message_store.get_pending_messages(),
                            [{"type": "operation-result",
                              "result-text":
                                  "Successful release upgrade.",
                              "result-code": 0, "status": SUCCEEDED,
                              "operation-id": 1}])
