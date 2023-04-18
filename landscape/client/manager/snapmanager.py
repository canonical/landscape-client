import logging

from twisted.internet import defer
from twisted.internet import task

from landscape.client.manager.plugin import FAILED
from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.manager.plugin import SUCCEEDED
from landscape.client.snap.http import COMPLETE_STATUSES
from landscape.client.snap.http import INCOMPLETE_STATUSES
from landscape.client.snap.http import SnapdHttpException
from landscape.client.snap.http import SnapHttp


class SnapManager(ManagerPlugin):
    """
    Plugin that updates the state of snaps on this machine, installing,
    removing, refreshing, enabling, and disabling them in response to messages.

    Changes trigger SnapMonitor to send an updated state message immediately.
    """

    def register(self, registry):
        super().register(registry)
        self.config = registry.config

        registry.register_message("install-snaps", self._handle_install_snaps)
        registry.register_message("remove-snaps", self._handle_remove_snaps)

    def _handle_install_snaps(self, message):
        """
        Installs the snaps indicated in `message` using the snap interface.
        """
        snaps = message["snaps"]
        opid = message["operation-id"]
        snap_http = SnapHttp()
        errors = {}
        installing = []

        logging.info("Installing snaps: %s", snaps)

        # Naively doing this synchronously because each is an HTTP call to the
        # snap REST API that returns basically immediately. We poll for their
        # completion statuses once they've all been kicked off.
        for snap in snaps:
            name = snap["name"]
            revision = snap.get("revision") or None
            channel = snap.get("tracking-channel") or None

            try:
                response = snap_http.install_snap(
                    name,
                    revision=revision,
                    channel=channel,
                )

                if "change" not in response:
                    logging.error(
                        "Error installing snap '%s': %s",
                        name,
                        response["result"]["message"],
                    )
                    errors[(name, revision, channel)] = str(response)

                installing.append((response["change"], name))
            except SnapdHttpException as e:
                result = e.json["result"]
                logging.error("Error installing snap '%s': %s", name, result)
                errors[(name, revision, channel)] = result

        return self._check_statuses(installing, opid, errors)

    def _handle_remove_snaps(self, message):
        """
        Removes the snaps indicated in `message` using the snap interface.
        """
        snaps = message["snaps"]
        opid = message["operation-id"]
        snap_http = SnapHttp()
        errors = {}
        removing = []

        logging.info("Removing snaps: %s", snaps)

        # See comment in `_handle_install_snaps` for reasoning behind this sync
        # approach.
        for snap in snaps:
            name = snap["name"]

            try:
                response = snap_http.remove_snap(name)

                if "change" not in response:
                    logging.error(
                        "Error removing snap '%s': %s",
                        name,
                        response["result"]["message"],
                    )
                    errors[name] = str(response)

                removing.append((response["change"], name))
            except SnapdHttpException as e:
                result = e.json["result"]
                logging.error("Error removing snap '%s':%s", name, result)
                errors[name] = result

        return self._check_statuses(removing, opid, errors)

    def _check_statuses(self, change_ids, opid, errors):
        """
        Repeatedly polls for the status of each change in `change_ids`
        until all are done.

        Because there might be multiple changes kicked off at once, we use
        `gatherResults` to wait until all of them are completed (successfully
        or otherwise).
        """
        deferred_results = defer.gatherResults(
            [self._get_status(cid, name) for cid, name in change_ids],
            consumeErrors=True,
        )

        deferred_results.addCallback(
            lambda results: self._respond(results, opid, errors),
        )

        return deferred_results

    def _get_status(self, change_id, snap_name):
        """
        Uses the snap interface to retrieve the status of a snap change.
        Polls every `interval` seconds a maximum of `attempts` times, as
        configured in the registry.
        """
        counter = 0
        attempts = getattr(self.registry.config, "snapd_poll_attempts", 5)
        interval = getattr(self.registry.config, "snapd_poll_interval", 15)
        snap_http = SnapHttp()

        def get_status():
            """
            Looping function that stashes results in loop.result. Exits when a
            non-incomplete snap change status is found, or upon an error.
            """
            nonlocal counter
            counter += 1

            logging.debug("Polling snapd for status of change %s", change_id)

            if counter >= attempts:
                loop.stop()
                loop.result = (change_id, f"{snap_name}: Timeout")
                return

            try:
                response = snap_http.check_change(change_id)
            except SnapdHttpException as e:
                logging.error(
                    "Error checking status of snap change %s: %s",
                    change_id,
                    e,
                )
                loop.stop()
                loop.result = (change_id, f"{snap_name}: {e}")
                return

            status = response.get("result", {}).get("status")

            logging.debug("Got status %s for change %s", status, change_id)

            if status and status in INCOMPLETE_STATUSES:
                logging.debug("Incomplete status, waiting...")
                loop.result = None
                return

            loop.stop()

            if status:
                logging.debug("Complete status, finishing...")
                loop.result = change_id, status
                return

            loop.result = (change_id, f"{snap_name}: SnapdError")
            return

        loop = task.LoopingCall(get_status)
        loopDeferred = loop.start(interval)
        return loopDeferred.addCallback(lambda done_loop: done_loop.result)

    def _respond(self, snap_results, opid, errors):
        """
        Queues a response to Landscape Server based on the contents of
        `results`.

        `completed` and `errored` are lists of snapd change ids.
        Text error messages are stored in `errors`.
        """
        logging.debug("Preparing snap-install-done response: %s", snap_results)

        results = {
            "completed": [],
            "errored": [],
            "errors": errors,
        }

        for cid, status in snap_results:
            if status in COMPLETE_STATUSES:
                results["completed"].append(cid)
            else:
                results["errored"].append(cid)
                results["errors"][cid] = status

        message = {
            "type": "operation-result",
            "status": FAILED if results["errored"] or errors else SUCCEEDED,
            "result-text": str(results),
            "operation-id": opid,
        }

        logging.debug("Sending snap-install-done response")

        return self.registry.broker.send_message(
            message,
            self._session_id,
            True,
        )
