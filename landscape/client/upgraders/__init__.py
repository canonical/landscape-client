from landscape.client.upgraders import broker
from landscape.client.upgraders import monitor
from landscape.client.upgraders import package


UPGRADE_MANAGERS = {
    # these should not be hardcoded
    "broker": broker.upgrade_manager,
    "monitor": monitor.upgrade_manager,
    "package": package.upgrade_manager,
}
