from landscape.upgraders import legacy, broker, monitor, package, player


UPGRADE_MANAGERS = {
    # these should not be hardcoded
    "legacy" : legacy.upgrade_manager,
    "broker" : broker.upgrade_manager,
    "monitor" : monitor.upgrade_manager,
    "package" : package.upgrade_manager,
    "player" : player.upgrade_manager,
    }
