import logging
import time
import sys
import os
import pwd

from twisted.internet.defer import succeed, fail

from landscape.package.reporter import find_reporter_command
from landscape.package.taskhandler import PackageTaskHandler, run_task_handler


SUCCESS_RESULT = 1
ERROR_RESULT = 100
DEPENDENCY_ERROR_RESULT = 101


# The amount of time to wait while we have unknown package data before
# reporting an error to the server in response to an operation.
# The two common cases of this are:
# 1.  The server requested an operation that we've decided requires some
# dependencies, but we don't know the package ID of those dependencies.  It
# should only take a bit more than 10 minutes for that to be resolved by the
# package reporter.
# 2.  We lost some package data, for example by a deb archive becoming
# inaccessible for a while.  The earliest we can reasonably assume that to be
# resolved is in 60 minutes, when the smart cronjob runs again.

# So we'll give the problem one chance to resolve itself, by only waiting for
# one run of smart update.
UNKNOWN_PACKAGE_DATA_TIMEOUT = 70 * 60


class UnknownPackageData(Exception):
    """Raised when an ID or a hash isn't known."""


class PackageChanger(PackageTaskHandler):

    queue_name = "changer"

    def run(self):
        task1 = self._store.get_next_task(self.queue_name)
        result = super(PackageChanger, self).run()
        def finished(result):
            task2 = self._store.get_next_task(self.queue_name)
            if task1 and task1.id != (task2 and task2.id):
                if os.getuid() == 0:
                    os.setuid(pwd.getpwnam("landscape").pw_uid)
                os.system(find_reporter_command())
        return result.addCallback(finished)

    def handle_tasks(self):
        result = super(PackageChanger, self).handle_tasks()
        return result.addErrback(self._warn_about_unknown_data)

    def handle_task(self, task):
        message = task.data
        if message["type"] == "change-packages":
            result = self._handle_change_packages(message)
            return result.addErrback(self._check_expired_unknown_data, task)

    def _warn_about_unknown_data(self, failure):
        failure.trap(UnknownPackageData)
        logging.warning("Package data not yet synchronized with server (%r)" %
                        failure.value.args[0])

    def _check_expired_unknown_data(self, failure, task):
        failure.trap(UnknownPackageData)
        if task.timestamp < time.time() - UNKNOWN_PACKAGE_DATA_TIMEOUT:
            self._warn_about_unknown_data(failure)
            message = {"type": "change-packages-result",
                       "operation-id": task.data["operation-id"],
                       "result-code": ERROR_RESULT,
                       "result-text": "Package data has changed. "
                                      "Please retry the operation."}
            return self._broker.send_message(message)
        else:
            return failure

    def _handle_change_packages(self, message):
        self.ensure_channels_reloaded()

        self._facade.reset_marks()

        if message.get("upgrade-all"):
            for package in self._facade.get_packages():
                if package.installed:
                    self._facade.mark_upgrade(package)

        for field, mark_func in [("install", self._facade.mark_install),
                                 ("remove", self._facade.mark_remove)]:
            for id in message.get(field, ()):
                hash = self._store.get_id_hash(id)
                if hash is None:
                    return fail(UnknownPackageData(id))
                package = self._facade.get_package_by_hash(hash)
                if package is None:
                    return fail(UnknownPackageData(hash))
                mark_func(package)

        message = {"type": "change-packages-result",
                   "operation-id": message.get("operation-id")}

        # Delay importing these so that we don't import Smart unless
        # we really need to.
        from landscape.package.facade import (
            DependencyError, TransactionError, SmartError)

        result = None
        try:
            result = self._facade.perform_changes()
        except (TransactionError, SmartError), exception:
            result_code = ERROR_RESULT
            result = exception.args[0]
        except DependencyError, exception:
            result_code = DEPENDENCY_ERROR_RESULT
            installs = []
            removals = []
            for package in exception.packages:
                hash = self._facade.get_package_hash(package)
                id = self._store.get_hash_id(hash)
                if id is None:
                    # Will have to wait until the server lets us know about
                    # this id.
                    return fail(UnknownPackageData(hash))
                if package.installed:
                    # Package currently installed. Must remove it.
                    removals.append(id)
                else:
                    # Package currently available. Must install it.
                    installs.append(id)
            if installs:
                installs.sort()
                message["must-install"] = installs
            if removals:
                removals.sort()
                message["must-remove"] = removals
        else:
            result_code = SUCCESS_RESULT

        message["result-code"] = result_code
        if result is not None:
            message["result-text"] = result

        logging.info("Queuing message with change package results to "
                     "exchange urgently.")
        return self._broker.send_message(message, True)


def main(args):
    if os.getpgrp() != os.getpid():
        os.setsid()
    return run_task_handler(PackageChanger, args)


def find_changer_command():
    dirname = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(dirname, "landscape-package-changer")
