import os
import re
import logging

from twisted.internet.defer import succeed, Deferred, maybeDeferred

from landscape.lib.apt.package.store import PackageStore, InvalidHashIdDb
from landscape.lib.lock import lock_path, LockError
from landscape.lib.log import log_failure
from landscape.lib.lsb_release import LSB_RELEASE_FILENAME, parse_lsb_release
from landscape.client.reactor import LandscapeReactor
from landscape.client.deployment import Configuration, init_logging
from landscape.client.broker.amp import RemoteBrokerConnector


class PackageTaskError(Exception):
    """Raised when a task hasn't been successfully completed."""


class PackageTaskHandlerConfiguration(Configuration):
    """Specialized configuration for L{PackageTaskHandler}s."""

    @property
    def package_directory(self):
        """Get the path to the package directory."""
        return os.path.join(self.data_path, "package")

    @property
    def store_filename(self):
        """Get the path to the SQlite file for the L{PackageStore}."""
        return os.path.join(self.package_directory, "database")

    @property
    def hash_id_directory(self):
        """Get the path to the directory holding the stock hash-id stores."""
        return os.path.join(self.package_directory, "hash-id")

    @property
    def update_stamp_filename(self):
        """Get the path to the update-stamp file."""
        return os.path.join(self.package_directory, "update-stamp")

    @property
    def detect_package_changes_stamp(self):
        """Get the path to the stamp marking when the last time we checked for
        changes in the packages was."""
        return os.path.join(self.data_path, "detect_package_changes_timestamp")


class LazyRemoteBroker(object):
    """Wrapper class around L{RemoteBroker} providing lazy initialization.

    This class is a wrapper around a regular L{RemoteBroker}. It connects to
    the remote broker object only when one of its attributes is first accessed.

    @param connector: The L{RemoteBrokerConnector} which will be used
        to connect to the broker.

    @note: This behaviour is needed in particular by the ReleaseUpgrader and
        the PackageChanger, because if the they connect early and the
        landscape-client package gets upgraded while they run, they will lose
        the connection and will not be able to reconnect for a potentially long
        window of time (till the new landscape-client package version is fully
        configured and the service is started again).
    """

    def __init__(self, connector):
        self._connector = connector
        self._remote = None

    def __getattr__(self, method):

        if self._remote:
            return getattr(self._remote, method)

        def wrapper(*args, **kwargs):

            def got_connection(remote):
                self._remote = remote
                return getattr(self._remote, method)(*args, **kwargs)

            result = self._connector.connect()
            return result.addCallback(got_connection)

        return wrapper


class PackageTaskHandler(object):

    config_factory = PackageTaskHandlerConfiguration

    queue_name = "default"
    lsb_release_filename = LSB_RELEASE_FILENAME
    package_store_class = PackageStore

    # This file is touched after every succesful 'apt-get update' run if the
    # update-notifier-common package is installed.
    update_notifier_stamp = "/var/lib/apt/periodic/update-success-stamp"

    def __init__(self, package_store, package_facade, remote_broker, config,
                 reactor):
        self._store = package_store
        self._facade = package_facade
        self._broker = remote_broker
        self._config = config
        self._count = 0
        self._session_id = None
        self._reactor = reactor

    def run(self):
        return self.handle_tasks()

    def handle_tasks(self):
        """Handle the tasks in the queue.

        The tasks will be handed over one by one to L{handle_task} until the
        queue is empty or a task fails.

        @see: L{handle_tasks}
        """
        return self._handle_next_task(None)

    def _handle_next_task(self, result, last_task=None):
        """Pick the next task from the queue and pass it to C{handle_task}."""

        if last_task is not None:
            # Last task succeeded.  We can safely kill it now.
            last_task.remove()
            self._count += 1

        task = self._store.get_next_task(self.queue_name)

        if task:
            self._decode_task_type(task)
            # We have another task.  Let's handle it.
            result = maybeDeferred(self.handle_task, task)
            result.addCallback(self._handle_next_task, last_task=task)
            result.addErrback(self._handle_task_failure)
            return result

        else:
            # No more tasks!  We're done!
            return succeed(None)

    def _handle_task_failure(self, failure):
        """Gracefully handle a L{PackageTaskError} and stop handling tasks."""
        failure.trap(PackageTaskError)

    def handle_task(self, task):
        """Handle a single task.

        Sub-classes must override this method in order to trigger task-specific
        actions.

        This method must return a L{Deferred} firing the task result. If the
        deferred is successful the task will be removed from the queue and the
        next one will be picked. If the task can't be completed, this method
        must raise a L{PackageTaskError}, in this case the handler will stop
        processing tasks and the failed task won't be removed from the queue.
        """
        return succeed(None)

    @property
    def handled_tasks_count(self):
        """
        Return the number of tasks that have been successfully handled so far.
        """
        return self._count

    def use_hash_id_db(self):
        """
        Attach the appropriate pre-canned hash=>id database to our store.
        """

        def use_it(hash_id_db_filename):

            if hash_id_db_filename is None:
                # Couldn't determine which hash=>id database to use,
                # just ignore the failure and go on
                return

            if not os.path.exists(hash_id_db_filename):
                # The appropriate database isn't there, but nevermind
                # and just go on
                return

            try:
                self._store.add_hash_id_db(hash_id_db_filename)
            except InvalidHashIdDb:
                # The appropriate database is there but broken,
                # let's remove it and go on
                logging.warning("Invalid hash=>id database %s" %
                                hash_id_db_filename)
                os.remove(hash_id_db_filename)
                return

        result = self._determine_hash_id_db_filename()
        result.addCallback(use_it)
        return result

    def _determine_hash_id_db_filename(self):
        """Build up the filename of the hash=>id database to use.

        @return: a deferred resulting in the filename to use or C{None}
            in case of errors.
        """

        def got_server_uuid(server_uuid):

            warning = "Couldn't determine which hash=>id database to use: %s"

            if server_uuid is None:
                logging.warning(warning % "server UUID not available")
                return None

            try:
                lsb_release_info = parse_lsb_release(self.lsb_release_filename)
            except IOError as error:
                logging.warning(warning % str(error))
                return None
            try:
                codename = lsb_release_info["code-name"]
            except KeyError:
                logging.warning(warning % "missing code-name key in %s" %
                                self.lsb_release_filename)
                return None

            arch = self._facade.get_arch()
            if not arch:
                # The Apt code should always return a non-empty string,
                # so this branch shouldn't get executed at all. However
                # this check is kept as an extra paranoia sanity check.
                logging.warning(warning % "unknown dpkg architecture")
                return None

            return os.path.join(self._config.hash_id_directory,
                                "%s_%s_%s" % (server_uuid, codename, arch))

        result = self._broker.get_server_uuid()
        result.addCallback(got_server_uuid)
        return result

    def get_session_id(self):

        def got_session_id(session_id):
            self._session_id = session_id
            return session_id

        result = self._broker.get_session_id()
        result.addCallback(got_session_id)
        return result

    def _decode_task_type(self, task):
        """Decode message_type for tasks created pre-py3."""
        try:
            message_type = task.data["type"]
        except (TypeError, KeyError):
            return
        try:
            task.data["type"] = message_type.decode("ascii")
        except AttributeError:
            pass


def run_task_handler(cls, args, reactor=None):
    if reactor is None:
        reactor = LandscapeReactor()

    config = cls.config_factory()
    config.load(args)

    for directory in [config.package_directory, config.hash_id_directory]:
        if not os.path.isdir(directory):
            os.mkdir(directory)

    program_name = cls.queue_name
    lock_filename = os.path.join(config.package_directory,
                                 program_name + ".lock")
    try:
        lock_path(lock_filename)
    except LockError:
        if config.quiet:
            raise SystemExit()
        raise SystemExit("error: package %s is already running"
                         % program_name)

    words = re.findall("[A-Z][a-z]+", cls.__name__)
    init_logging(config, "-".join(word.lower() for word in words))

    # Setup our umask for Apt to use, this needs to setup file permissions to
    # 0o644 so...
    os.umask(0o022)

    package_store = cls.package_store_class(config.store_filename)
    # Delay importing of the facades so that we don't
    # import Apt unless we need to.
    from landscape.lib.apt.package.facade import AptFacade
    package_facade = AptFacade()

    def finish():
        connector.disconnect()
        reactor.call_later(0, reactor.stop)

    def got_error(failure):
        log_failure(failure)
        finish()

    connector = RemoteBrokerConnector(reactor, config, retry_on_reconnect=True)
    remote = LazyRemoteBroker(connector)
    handler = cls(package_store, package_facade, remote, config, reactor)
    result = Deferred()
    result.addCallback(lambda x: handler.run())
    result.addCallback(lambda x: finish())
    result.addErrback(got_error)
    reactor.call_when_running(lambda: result.callback(None))
    reactor.run()

    return result
