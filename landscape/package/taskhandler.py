import os
import logging

from twisted.internet.defer import Deferred, succeed

from landscape.lib.dbus_util import get_bus
from landscape.lib.lock import lock_path, LockError
from landscape.lib.log import log_failure
from landscape.lib.command import run_command, CommandError
from landscape.deployment import Configuration, init_logging
from landscape.package.store import PackageStore
from landscape.broker.remote import RemoteBroker


class PackageTaskHandler(object):

    queue_name = "default"

    def __init__(self, package_store, package_facade, remote_broker, config):
        self._store = package_store
        self._facade = package_facade
        self._broker = remote_broker
        self._config = config
        self._channels_reloaded = False
        self._server_uuid = None

    def ensure_channels_reloaded(self):
        if not self._channels_reloaded:
            self._channels_reloaded = True
            self._facade.reload_channels()

    def run(self):
        return self.handle_tasks()

    def handle_tasks(self):
        deferred = Deferred()
        self._handle_next_task(None, deferred)
        return deferred

    def _handle_next_task(self, result, deferred, last_task=None):
        if last_task is not None:
            # Last task succeeded.  We can safely kill it now.
            last_task.remove()

        task = self._store.get_next_task(self.queue_name)

        if task:
            # We have another task.  Let's handle it.
            result = self.handle_task(task)
            result.addCallback(self._handle_next_task, deferred, task)
            result.addErrback(deferred.errback)

        else:
            # No more tasks!  We're done!
            deferred.callback(None)

    def handle_task(self, task):
        return succeed(None)

    def use_hash_id_db(self):
        """
        Attach the appropriate pre-canned hash=>id database to our store.
        """
        def server_uuid_loaded(ignored):
            hash_id_db_filename = self._get_hash_id_db_filename()

            if not hash_id_db_filename:
                # Couldn't determine which hash=>id database to use,
                # just ignore the failure and go on
                return

            if not os.path.exists(hash_id_db_filename):
                # The appropriate database isn't ther, but nevermind
                # and just go on
                return

            self._store.add_hash_id_db(hash_id_db_filename)

        result = self._load_server_uuid()
        result.addCallback(server_uuid_loaded)
        return result

    def _load_server_uuid(self):
        if self._server_uuid:
            return succeed(self._server_uuid)

        def set_server_uuid(server_uuid):
            self._server_uuid = server_uuid
            return server_uuid

        result = self._broker.get_server_uuid()
        result.addCallback(set_server_uuid)
        return result

    def _get_package_directory(self):
        return os.path.join(self._config.data_path, "package")

    def _get_hash_id_db_directory(self):
        return os.path.join(self._get_package_directory(), "hash-id")

    def _get_hash_id_db_filename(self):
        try:
            # XXX we should add some methods to the Smart facade to get these
            codename = run_command("lsb_release -cs")
            arch = run_command("dpkg --print-architecture")
        except CommandError, error:
            logging.warning("Couldn't determine which hash=>id database "
                            "to use: %s" % str(error))
            return None

        return os.path.join(self._get_hash_id_db_directory(),
                            "%s_%s_%s" % (self._server_uuid,
                                          codename,
                                          arch))

def run_task_handler(cls, args, reactor=None):
    from twisted.internet.glib2reactor import install
    install()

    # please only pass reactor when you have totally mangled everything with
    # mocker. Otherwise bad things will happen.
    if reactor is None:
        from twisted.internet import reactor

    program_name = cls.queue_name

    config = Configuration()
    config.load(args)

    package_directory = os.path.join(config.data_path, "package")
    hash_id_directory = os.path.join(package_directory, "hash-id")
    for directory in [package_directory, hash_id_directory]:
        if not os.path.isdir(directory):
            os.mkdir(directory)

    lock_filename = os.path.join(package_directory, program_name + ".lock")
    try:
        lock_path(lock_filename)
    except LockError:
        if config.quiet:
            raise SystemExit()
        raise SystemExit("error: package %s is already running"
                         % program_name)


    init_logging(config, "package-" + program_name)

    store_filename = os.path.join(package_directory, "database")

    # Setup our umask for Smart to use, this needs to setup file permissions to
    # 0644 so...
    os.umask(022)

    # Delay importing of the facade so that we don't
    # import Smart unless we need to.
    from landscape.package.facade import SmartFacade

    package_store = PackageStore(store_filename)
    package_facade = SmartFacade()
    remote = RemoteBroker(get_bus(config.bus))

    handler = cls(package_store, package_facade, remote, config)

    def got_err(failure):
        log_failure(failure)

    result = handler.run()
    result.addErrback(got_err)
    result.addBoth(lambda ignored: reactor.callLater(0, reactor.stop))

    reactor.run()

    return result
