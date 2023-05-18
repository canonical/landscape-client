import logging
from collections import deque

from twisted.internet import task

from landscape.client.manager.plugin import FAILED
from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.manager.plugin import SUCCEEDED
from landscape.client.monitor.snapmonitor import get_installed_snaps
from landscape.client.snap.http import INCOMPLETE_STATUSES
from landscape.client.snap.http import SnapdHttpException
from landscape.client.snap.http import SnapHttp
from landscape.client.snap.http import SUCCESS_STATUSES


class SnapManager(ManagerPlugin):
    """
    Plugin that updates the state of snaps on this machine, installing,
    removing, refreshing, enabling, and disabling them in response to messages.

    Changes trigger SnapMonitor to send an updated state message immediately.
    """

    def register(self, registry):
        super().register(registry)
        self.config = registry.config
        self._snap_http = SnapHttp()

        self.SNAP_METHODS = {
            "install-snaps": self._snap_http.install_snap,
            "remove-snaps": self._snap_http.remove_snap,
        }

        registry.register_message("install-snaps", self._handle_snap_task)
        registry.register_message("remove-snaps", self._handle_snap_task)

    def _handle_snap_task(self, message):
        """
        Performs a generic task, `snap_method`, on a group of snaps.
        """
        message_type = message["type"]
        snaps = message["snaps"]
        opid = message["operation-id"]
        snap_method = self.SNAP_METHODS[message_type]
        errors = {}
        queue = deque()

        logging.info(f"Performing {message_type} action for snaps {snaps}")

        # Naively doing this synchronously because each is an HTTP call to the
        # snap REST API that returns basically immediately. We poll for their
        # completion statuses once they've all been kicked off.
        for snap in snaps:
            name = snap["name"]
            revision = snap.get("revision") or None
            channel = snap.get("tracking-channel") or None

            try:
                response = snap_method(
                    name,
                    revision=revision,
                    channel=channel,
                )

                if "change" not in response:
                    message = response["result"]["message"]
                    logging.error(
                        f"Error in {message_type} for '{name}': {message}",
                    )
                    errors[(name, revision, channel)] = str(response)

                queue.append((response["change"], name))
            except SnapdHttpException as e:
                result = e.json["result"]
                logging.error(
                    f"Error in {message_type} for '{name}': {result}",
                )
                errors[(name, revision, channel)] = result

        deferred = self._check_statuses(queue)
        deferred.addCallback(self._respond, opid, errors)

        return deferred

    def _check_statuses(self, change_queue):
        """
        Repeatedly polls for the status of each change in `change_queue`
        until all are no longer in-progress.
        """
        completed_changes = []
        interval = getattr(self.registry.config, "snapd_poll_interval", 15)

        def get_status():
            """
            Looping function that polls snapd for the status of
            changes, moving them from the queue when they are done.
            """
            if not change_queue:
                loop.stop()
                return

            logging.info("Polling snapd for status of pending snap changes")

            try:
                result = self._snap_http.check_changes().get("result", [])
            except SnapdHttpException as e:
                logging.error(f"Error checking status of snap changes: {e}")
                completed_changes.extend(
                    [(name, str(e)) for _, name in change_queue],
                )
                loop.stop()
                return

            for _ in range(len(change_queue)):
                cid, name = change_queue.popleft()

                # It's possible (though unlikely) that a change is not in the
                # list - snapd could have dropped it for some reason. We need
                # to know if that happens, hence the extra `found` check.
                found = False
                for change in result:
                    if change["id"] != cid:
                        continue

                    found = True
                    status = change["status"]
                    if status in INCOMPLETE_STATUSES:
                        logging.info(
                            f"Incomplete status for {name}, waiting...",
                        )
                        change_queue.append((cid, name))
                    else:
                        logging.info(f"Complete status for {name}")
                        completed_changes.append((name, status))

                    break

                if not found:
                    completed_changes.append((name, "Unknown"))

        loop = task.LoopingCall(get_status)
        loopDeferred = loop.start(interval)

        return loopDeferred.addCallback(lambda _: completed_changes)

    def _respond(self, snap_results, opid, errors):
        """
        Queues a response to Landscape Server based on the contents of
        `results`.

        `completed` and `errored` are lists of snapd change ids.
        Text error messages are stored in `errors`.
        """
        logging.debug(f"Preparing snap-install-done response: {snap_results}")

        results = {
            "completed": [],
            "errored": [],
            "errors": errors,
        }

        for name, status in snap_results:
            if status not in SUCCESS_STATUSES:
                results["errored"].append(name)
                results["errors"][name] = status
            else:
                results["completed"].append(name)

        message = {
            "type": "operation-result",
            "status": FAILED if results["errored"] or errors else SUCCEEDED,
            "result-text": str(results),
            "operation-id": opid,
        }

        logging.debug("Sending snap-install-done response")

        # Kick off an immediate SnapMonitor message as well.
        self._send_installed_snap_update()

        return self.registry.broker.send_message(
            message,
            self._session_id,
            True,
        )

    def _send_installed_snap_update(self):
        installed_snaps = get_installed_snaps(self._snap_http)
        if installed_snaps:
            self.registry.broker.send_message(
                {
                    "type": "snaps",
                    "snaps": installed_snaps,
                },
                self._session_id,
                True,
            )
