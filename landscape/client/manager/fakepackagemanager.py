import random

from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.manager.manager import SUCCEEDED


class FakePackageManager(ManagerPlugin):

    run_interval = 1800
    randint = random.randint

    def register(self, registry):
        super(FakePackageManager, self).register(registry)
        self.config = registry.config

        registry.register_message("change-packages",
                                  self.handle_change_packages)
        registry.register_message("change-package-locks",
                                  self.handle_change_package_locks)
        registry.register_message("release-upgrade",
                                  self.handle_release_upgrade)

    def _handle(self, response):
        delay = self.randint(30, 300)
        self.registry.reactor.call_later(
            delay, self.manager.broker.send_message, response,
            self._session_id, urgent=True)

    def handle_change_packages(self, message):
        response = {"type": "change-packages-result",
                    "operation-id": message.get("operation-id"),
                    "result-code": 1,
                    "result-text": "OK done."}
        return self._handle(response)

    def handle_change_package_locks(self, message):
        response = {"type": "operation-result",
                    "operation-id": message.get("operation-id"),
                    "status": SUCCEEDED,
                    "result-text": "Package locks successfully changed.",
                    "result-code": 0}
        return self._handle(response)

    def handle_release_upgrade(self, message):
        response = {"type": "operation-result",
                    "operation-id": message.get("operation-id"),
                    "status": SUCCEEDED,
                    "result-text": "Successful release upgrade.",
                    "result-code": 0}
        return self._handle(response)
