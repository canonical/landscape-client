from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.snap.http import SnapdHttpException, SnapHttp


class SnapManager(ManagerPlugin):
    """
    Plugin that updates the state of snaps on this machine, installing,
    removing, refreshing, enabling, and disabling them in response to messages.

    Changes trigger SnapMonitor to send an updated state message immediately.
    """
    def register(self, registry):
        super(SnapManager, self).register(registry)
        self.config = registry.config

        registry.register_message("install-snaps", self.handle_install_snaps)

    def handle_install_snaps(self, message):
        snaps = message["snaps"]
        snap_http = SnapHttp()
        errors = {}

        # Naively doing this synchronously because each is an HTTP call to the
        # snap REST API that returns basically immediately.
        for snap in snaps:
            name = snap["name"]
            revision = snap.get("revision") or None
            channel = snap.get("tracking-channel") or None

            try:
                snap_http.install_snap(
                    snap["name"],
                    revision=revision,
                    channel=channel,
                )
            except SnapdHttpException as e:
                errors[(name, revision, channel)] = str(e)

        if errors:
            ...  # UH-OH
