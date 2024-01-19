import json
import logging
from collections import deque

from twisted.internet import task

from landscape.client import snap_http
from landscape.client.manager.plugin import FAILED
from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.manager.plugin import SUCCEEDED
from landscape.client.snap_http import INCOMPLETE_STATUSES
from landscape.client.snap_http import SnapdHttpException
from landscape.client.snap_http import SUCCESS_STATUSES


class SnapManager(ManagerPlugin):
    """
    Plugin that updates the state of snaps on this machine, installing,
    removing, refreshing, enabling, and disabling them in response to messages.

    Changes trigger SnapMonitor to send an updated state message immediately.
    """

    def __init__(self):
        super().__init__()

        self.SNAP_METHODS = {
            "install-snaps": snap_http.install,
            "install-snaps-batch": snap_http.install_all,
            "remove-snaps": snap_http.remove,
            "remove-snaps-batch": snap_http.remove_all,
            "refresh-snaps": snap_http.refresh,
            "refresh-snaps-batch": snap_http.refresh_all,
            "hold-snaps": snap_http.hold,
            "hold-snaps-batch": snap_http.hold_all,
            "unhold-snaps": snap_http.unhold,
            "unhold-snaps-batch": snap_http.unhold_all,
            "set-snap-config": snap_http.set_conf,
        }

    def register(self, registry):
        super().register(registry)
        self.config = registry.config

        registry.register_message("install-snaps", self._handle_snap_task)
        registry.register_message("remove-snaps", self._handle_snap_task)
        registry.register_message("refresh-snaps", self._handle_snap_task)
        registry.register_message("hold-snaps", self._handle_snap_task)
        registry.register_message("unhold-snaps", self._handle_snap_task)
        registry.register_message("set-snap-config", self._handle_snap_task)

    def _handle_snap_task(self, message):
        """
        If there are no per-snap arguments for the targeted
        snaps, often the task can be done with a single snapd call, if
        we have a handler for the action type, which we call via a kind
        of dynamic dispatch.
        """
        snaps = message["snaps"]

        if snaps and any(len(s) > 1 for s in snaps):
            # "name" key only means no per-snap args.
            return self._handle_multiple_snap_tasks(message)

        if f"{message['type']}-batch" not in self.SNAP_METHODS:
            return self._handle_multiple_snap_tasks(message)

        return self._handle_batch_snap_task(message)

    def _handle_batch_snap_task(self, message):
        logging.debug(
            f"Handling message {message} as a single batch snap task",
        )
        message_type = message["type"]
        snaps = [s["name"] for s in message["snaps"]]
        snap_args = message.get("args", {})
        opid = message["operation-id"]
        errors = {}
        queue = deque()

        logging.info(f"Performing {message_type} action for snaps {snaps}")

        try:
            response = self._start_snap_task(
                message_type + "-batch",
                snaps,
                **snap_args,
            )
            queue.append((response["change"], "BATCH"))
        except SnapdHttpException as e:
            result = json.loads(e.args[0])["result"]
            logging.error(
                f"Error in {message_type}: {message}",
            )
            errors["BATCH"] = result

        deferred = self._check_statuses(queue)
        deferred.addCallback(self._respond, opid, errors)

        return deferred

    def _handle_multiple_snap_tasks(self, message):
        """
        Performs a generic task, `snap_method`, on a group of snaps
        where each task must be performed independently per-snap.

        This is required when we want to provide metadata for refreshes
        or installs and also specify the channel, revision, or other
        arguments per-snap.
        """
        logging.debug(f"Handling message {message} as multiple snap tasks")
        message_type = message["type"]
        snaps = message["snaps"]
        opid = message["operation-id"]
        errors = {}
        queue = deque()

        logging.info(f"Performing {message_type} action for snaps {snaps}")

        # Naively doing this synchronously because each is an HTTP call to the
        # snap REST API that returns basically immediately. We poll for their
        # completion statuses once they've all been kicked off.
        for snap in snaps:
            name = snap["name"]
            snap_args = snap.get("args", {})

            try:
                response = self._start_snap_task(
                    message_type,
                    name,
                    **snap_args,
                )
                queue.append((response["change"], name))
            except SnapdHttpException as e:
                result = json.loads(e.args[0])["result"]
                logging.error(
                    f"Error in {message_type} for '{name}': {message}",
                )
                errors[name] = result

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
                result = snap_http.check_changes().get("result", [])
                result_dict = {c["id"]: c for c in result}
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
                # to know if that happens, hence this check.
                if cid not in result_dict:
                    completed_changes.append((name, "Unknown"))
                    continue

                status = result_dict[cid]["status"]
                if status in INCOMPLETE_STATUSES:
                    logging.info(
                        f"Incomplete status for {name}, waiting...",
                    )
                    change_queue.append((cid, name))
                else:
                    logging.info(f"Complete status for {name}")
                    completed_changes.append((name, status))

        loop = task.LoopingCall(get_status)
        loopDeferred = loop.start(interval)

        return loopDeferred.addCallback(lambda _: completed_changes)

    def _start_snap_task(self, action, *args, **kwargs):
        """
        Kicks off the appropriate SNAP_METHOD for `action`.

        raises a `SnapdHttpException` in the event of issues.
        """
        snap_method = self.SNAP_METHODS[action]

        response = snap_method(*args, **kwargs)

        if "change" not in response:
            raise SnapdHttpException(response)

        return response

    def _respond(self, snap_results, opid, errors):
        """
        Queues a response to Landscape Server based on the contents of
        `results`.

        `completed` and `errored` are lists of snapd change ids.
        Text error messages are stored in `errors`.
        """
        logging.debug(f"Preparing snap change done response: {snap_results}")

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

        logging.debug("Sending snap-action-done response")

        # Kick off an immediate SnapMonitor message as well.
        self._send_installed_snap_update()
        return self.registry.broker.send_message(
            message,
            self._session_id,
            True,
        )

    def _send_installed_snap_update(self):
        try:
            installed_snaps = snap_http.list().result
        except SnapdHttpException as e:
            logging.error(
                f"Unable to list installed snaps after snap change: {e}",
            )
            return

        if installed_snaps:
            return self.registry.broker.send_message(
                {
                    "type": "snaps",
                    "snaps": installed_snaps,
                },
                self._session_id,
                True,
            )
