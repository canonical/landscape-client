import os
import re
import logging

from twisted.internet.defer import Deferred, succeed

from landscape.lib.dbus_util import get_bus
from landscape.lib.lock import lock_path, LockError
from landscape.lib.log import log_failure
from landscape.lib.lsb_release import LSB_RELEASE_FILENAME, parse_lsb_release
from landscape.deployment import Configuration, init_logging
from landscape.package.store import PackageStore, InvalidHashIdDb
from landscape.broker.remote import RemoteBroker


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


class PackageTaskHandler(object):

    config_factory = PackageTaskHandlerConfiguration

    queue_name = "default"
    lsb_release_filename = LSB_RELEASE_FILENAME

    def __init__(self, package_store, package_facade, remote_broker, config):
        self._store = package_store
        self._facade = package_facade
        self._broker = remote_broker
        self._config = config
        self._channels_reloaded = False

    def ensure_channels_reloaded(self):
        if not self._channels_reloaded:
            self._channels_reloaded = True
            self._facade.reload_channels()

    def run(self):
        return self.handle_tasks()

    def handle_tasks(self):
        return self._handle_next_task(None)

    def _handle_next_task(self, result, last_task=None):
        if last_task is not None:
            # Last task succeeded.  We can safely kill it now.
            last_task.remove()

        task = self._store.get_next_task(self.queue_name)

        if task:
            # We have another task.  Let's handle it.
            result = self.handle_task(task)
            result.addCallback(self._handle_next_task, task)
            return result

        else:
            # No more tasks!  We're done!
            return succeed(None)

    def handle_task(self, task):
        return succeed(None)

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
            except IOError, error:
                logging.warning(warning % str(error))
                return None
            try:
                codename = lsb_release_info["code-name"]
            except KeyError:
                logging.warning(warning % "missing code-name key in %s" %
                                self.lsb_release_filename)
                return None

            arch = self._facade.get_arch()
            if arch is None:
                # The Smart code should always return a proper string, so this
                # branch shouldn't get executed at all. However this check is
                # kept as an extra paranoia sanity check.
                logging.warning(warning % "unknown dpkg architecture")
                return None

            return os.path.join(self._config.hash_id_directory,
                                "%s_%s_%s" % (server_uuid, codename, arch))

        result = self._broker.get_server_uuid()
        result.addCallback(got_server_uuid)
        return result


def run_task_handler(cls, args, reactor=None):
    from twisted.internet.glib2reactor import install
    install()

    # please only pass reactor when you have totally mangled everything with
    # mocker. Otherwise bad things will happen.
    if reactor is None:
        from twisted.internet import reactor

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

    # Setup our umask for Smart to use, this needs to setup file permissions to
    # 0644 so...
    os.umask(022)

    # Delay importing of the facade so that we don't
    # import Smart unless we need to.
    from landscape.package.facade import SmartFacade

    package_store = PackageStore(config.store_filename)
    package_facade = SmartFacade()
    remote = RemoteBroker(get_bus(config.bus))

    handler = cls(package_store, package_facade, remote, config)

    def got_err(failure):
        log_failure(failure)

    result = Deferred()
    result.addCallback(lambda ignored: handler.run())
    result.addErrback(got_err)
    result.addBoth(lambda ignored: reactor.callLater(0, reactor.stop))
    reactor.callWhenRunning(lambda: result.callback(None))

    reactor.run()

    return result
