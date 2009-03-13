import os
import logging

import pycurl

from twisted.internet.defer import Deferred, succeed

from landscape.lib.dbus_util import get_bus
from landscape.lib.lock import lock_path, LockError
from landscape.lib.log import log_failure
from landscape.deployment import Configuration, init_logging
from landscape.package.store import PackageStore
from landscape.broker.remote import RemoteBroker
from landscape.lib.fetch import HTTPCodeError


class PackageTaskHandler(object):

    queue_name = "default"

    def __init__(self, package_store, package_facade, remote_broker, config):
        self._store = package_store
        self._facade = package_facade
        self._broker = remote_broker
        self._channels_reloaded = False
        self._data_path = os.path.join(config.data_path, "package")
        self._lookaside_url = config.get("lookaside_url", None)

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

    def use_lookaside_db(self, codename=None, arch=None, fetch=None):
        """
        Try to attach a pre-canned lookaside database to our store.

        @param fetch: a function used to retrieve the appropriate lookaside
            database from the Landscape server
        """
        result = self._broker.get_server_uuid()

        if not codename:
            pipe = os.popen("lsb_release -cs")
            codename = pipe.readline().strip()

        if not arch:
            pipe = os.popen("dpkg --print-architecture")
            arch = pipe.readline().strip()

        def got_server_uuid(server_uuid):

            basename = "%s_%s_%s" % (server_uuid, codename, arch)
            directory = os.path.join(self._data_path, "lookaside")
            filename = os.path.join(directory, basename)

            if not os.path.exists(filename) and self._lookaside_url and fetch:
                url = str(self._lookaside_url.rstrip("/") + "/" + basename)
                error_message = None
                logging.info("Downloading lookaside database from %s" % url)
                try:
                    data = fetch(url)
                except pycurl.error, error:
                    error_message = error.args[1]
                except HTTPCodeError, error:
                    error_message = str(error)
                if error_message is not None:
                    logging.warning(
                        "Couldn't download lookaside database from %s: %s" %
                        (url, error_message))
                else:
                    if not os.path.isdir(directory):
                        os.makedirs(directory)
                    open(filename, "w").write(data)

            if os.path.exists(filename):
                self._store.add_lookaside_db(filename)

        result.addCallback(got_server_uuid)
        return result

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
    if not os.path.isdir(package_directory):
        os.mkdir(package_directory)

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
