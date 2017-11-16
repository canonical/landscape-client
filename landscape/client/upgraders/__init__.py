from landscape.client.upgraders import broker, monitor, package


UPGRADE_MANAGERS = {
    # these should not be hardcoded
    "broker": broker.upgrade_manager,
    "monitor": monitor.upgrade_manager,
    "package": package.upgrade_manager}
