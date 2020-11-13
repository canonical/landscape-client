try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse

import locale
import logging
import time
import os
import glob
import apt_pkg
import re

from twisted.internet.defer import (
    Deferred, succeed, inlineCallbacks, returnValue)

from landscape.lib import bpickle
from landscape.lib.apt.package.store import (
        UnknownHashIDRequest, FakePackageStore)
from landscape.lib.config import get_bindir
from landscape.lib.sequenceranges import sequence_to_ranges
from landscape.lib.twisted_util import gather_results, spawn_process
from landscape.lib.fetch import fetch_async
from landscape.lib.fs import touch_file, create_binary_file
from landscape.lib.lsb_release import parse_lsb_release, LSB_RELEASE_FILENAME
from landscape.client.package.taskhandler import (
    PackageTaskHandlerConfiguration, PackageTaskHandler, run_task_handler)


HASH_ID_REQUEST_TIMEOUT = 7200
MAX_UNKNOWN_HASHES_PER_REQUEST = 500
LOCK_RETRY_DELAYS = [0, 20, 40]
PYTHON_BIN = "/usr/bin/python3"
RELEASE_UPGRADER_PATTERN = "/tmp/ubuntu-release-upgrader-"
UID_ROOT = "0"


class PackageReporterConfiguration(PackageTaskHandlerConfiguration):
    """Specialized configuration for the Landscape package-reporter."""

    def make_parser(self):
        """
        Specialize L{Configuration.make_parser}, adding options
        reporter-specific options.
        """
        parser = super(PackageReporterConfiguration, self).make_parser()
        parser.add_option("--force-apt-update", default=False,
                          action="store_true",
                          help="Force running apt-update.")
        parser.add_option("--http-proxy", metavar="URL",
                          help="The URL of the HTTP proxy, if one is needed.")
        parser.add_option("--https-proxy", metavar="URL",
                          help="The URL of the HTTPS proxy, if one is needed.")
        return parser


class PackageReporter(PackageTaskHandler):
    """Report information about the system packages.

    @cvar queue_name: Name of the task queue to pick tasks from.
    """
    config_factory = PackageReporterConfiguration

    queue_name = "reporter"

    apt_update_filename = "/usr/lib/landscape/apt-update"
    sources_list_filename = "/etc/apt/sources.list"
    sources_list_directory = "/etc/apt/sources.list.d"
    _got_task = False

    def run(self):
        self._got_task = False

        result = Deferred()
        # Set us up to communicate properly
        result.addCallback(lambda x: self.get_session_id())

        result.addCallback(lambda x: self.run_apt_update())

        # If the appropriate hash=>id db is not there, fetch it
        result.addCallback(lambda x: self.fetch_hash_id_db())

        # Attach the hash=>id database if available
        result.addCallback(lambda x: self.use_hash_id_db())

        # Now, handle any queued tasks.
        result.addCallback(lambda x: self.handle_tasks())

        # Then, remove any expired hash=>id translation requests.
        result.addCallback(lambda x: self.remove_expired_hash_id_requests())

        # After that, check if we have any unknown hashes to request.
        result.addCallback(lambda x: self.request_unknown_hashes())

        # Finally, verify if we have anything new to report to the server.
        result.addCallback(lambda x: self.detect_changes())

        result.callback(None)
        return result

    def send_message(self, message):
        return self._broker.send_message(
            message, self._session_id, True)

    def fetch_hash_id_db(self):
        """
        Fetch the appropriate pre-canned database of hash=>id mappings
        from the server. If the database is already present, it won't
        be downloaded twice.

        The format of the database filename is <uuid>_<codename>_<arch>,
        and it will be downloaded from the HTTP directory set in
        config.package_hash_id_url, or config.url/hash-id-databases if
        the former is not set.

        Fetch failures are handled gracefully and logged as appropriate.
        """

        def fetch_it(hash_id_db_filename):

            if hash_id_db_filename is None:
                # Couldn't determine which hash=>id database to fetch,
                # just ignore the failure and go on
                return

            if os.path.exists(hash_id_db_filename):
                # We don't download twice
                return

            base_url = self._get_hash_id_db_base_url()
            if not base_url:
                logging.warning("Can't determine the hash=>id database url")
                return

            # Cast to str as pycurl doesn't like unicode
            url = str(base_url + os.path.basename(hash_id_db_filename))

            def fetch_ok(data):
                create_binary_file(hash_id_db_filename, data)
                logging.info("Downloaded hash=>id database from %s" % url)

            def fetch_error(failure):
                exception = failure.value
                logging.warning("Couldn't download hash=>id database: %s" %
                                str(exception))

            if url.startswith("https"):
                proxy = self._config.get("https_proxy")
            else:
                proxy = self._config.get("http_proxy")

            result = fetch_async(url,
                                 cainfo=self._config.get("ssl_public_key"),
                                 proxy=proxy)
            result.addCallback(fetch_ok)
            result.addErrback(fetch_error)

            return result

        result = self._determine_hash_id_db_filename()
        result.addCallback(fetch_it)
        return result

    def _get_hash_id_db_base_url(self):

        base_url = self._config.get("package_hash_id_url")

        if not base_url:

            if not self._config.get("url"):
                # We really have no idea where to download from
                return None

            # If config.url is http://host:123/path/to/message-system
            # then we'll use http://host:123/path/to/hash-id-databases
            base_url = urlparse.urljoin(self._config.url.rstrip("/"),
                                        "hash-id-databases")

        return base_url.rstrip("/") + "/"

    def _apt_sources_have_changed(self):
        """Return a boolean indicating if the APT sources were modified."""
        from landscape.client.monitor.packagemonitor import PackageMonitor

        filenames = []

        if os.path.exists(self.sources_list_filename):
            filenames.append(self.sources_list_filename)

        if os.path.exists(self.sources_list_directory):
            filenames.extend(
                [os.path.join(self.sources_list_directory, filename) for
                 filename in os.listdir(self.sources_list_directory)])

        for filename in filenames:
            seconds_since_last_change = (
                time.time() - os.path.getmtime(filename))
            if seconds_since_last_change < PackageMonitor.run_interval:
                return True

        return False

    def _apt_update_timeout_expired(self, interval):
        """Check if the apt-update timeout has passed."""
        if os.path.exists(self.update_notifier_stamp):
            stamp = self.update_notifier_stamp
        elif os.path.exists(self._config.update_stamp_filename):
            stamp = self._config.update_stamp_filename
        else:
            return True

        last_update = os.stat(stamp).st_mtime
        return (last_update + interval) < time.time()

    def _is_release_upgrader_running(self):
        """Detect whether ubuntu-release-upgrader is running.

        This is done by iterating the /proc tree (to avoid external
        dependencies) and checkign the cmdline and the uid of the process.
        The assumption is that ubuntu-release-upgrader is something that:
            * is run by a python interpreter
            * its first argument starts with '/tmp/ubuntu-release-upgrader-'
            * is executed by root (effective uid == 0)"""
        logging.debug("Checking if ubuntu-release-upgrader is running.")

        for cmdline in glob.glob("/proc/*/cmdline"):
            base = os.path.dirname(cmdline)
            try:
                with open(cmdline) as fd:
                    read = fd.read()

                pid = os.path.basename(os.path.dirname(cmdline))

                cmdline = [f for f in read.split("\x00") if f]
                if len(cmdline) <= 1:
                    continue

                with open(os.path.join(base, "status")) as fd:
                    read = fd.read()

                pattern = re.compile(r'^Uid\:(.*)$',
                                     re.VERBOSE | re.MULTILINE)

                for pattern in pattern.finditer(read):
                    uid = pattern.groups()[0].split("\t")[1]
            except IOError:
                continue

            (executable, args) = (cmdline[0], cmdline[1:])

            if (executable.startswith(PYTHON_BIN) and
                    any(x.startswith(RELEASE_UPGRADER_PATTERN)
                        for x in args) and
                    uid == UID_ROOT):
                logging.info("Found ubuntu-release-upgrader running (pid: %s)"
                             % (pid))
                return True
        return False

    @inlineCallbacks
    def run_apt_update(self):
        """
        Check if an L{_apt_update} call must be performed looping over specific
        delays so it can be retried.

        @return: a deferred returning (out, err, code)
        """
        if (self._config.force_apt_update or
            self._apt_sources_have_changed() or
            self._apt_update_timeout_expired(self._config.apt_update_interval)
            ) and \
           not self._is_release_upgrader_running():

            accepted_apt_errors = (
                "Problem renaming the file /var/cache/apt/srcpkgcache.bin",
                "Problem renaming the file /var/cache/apt/pkgcache.bin")

            for retry in range(len(LOCK_RETRY_DELAYS)):
                deferred = Deferred()
                self._reactor.call_later(
                    LOCK_RETRY_DELAYS[retry], self._apt_update, deferred)
                out, err, code = yield deferred
                out = out.decode("utf-8")
                err = err.decode("utf-8")

                timestamp = self._reactor.time()

                touch_file(self._config.update_stamp_filename)
                logging.debug(
                    "'%s' exited with status %d (out='%s', err='%s')" % (
                        self.apt_update_filename, code, out, err))

                if code != 0:
                    if code == 100:
                        if retry < len(LOCK_RETRY_DELAYS) - 1:
                            logging.warning(
                                "Could not acquire the apt lock. Retrying in"
                                " %s seconds." % LOCK_RETRY_DELAYS[retry + 1])
                            continue

                    logging.warning("'%s' exited with status %d (%s)" % (
                        self.apt_update_filename, code, err))

                    # Errors caused by missing cache files are acceptable,
                    # as they are not an issue for the lists update
                    # process.
                    # These errors can happen if an 'apt-get clean' is run
                    # while 'apt-get update' is running.
                    for message in accepted_apt_errors:
                        if message in err:
                            out, err, code = "", "", 0
                            break

                elif not self._facade.get_channels():
                    code = 1
                    err = ("There are no APT sources configured in %s or %s." %
                           (self.sources_list_filename,
                            self.sources_list_directory))

                yield self._broker.call_if_accepted(
                    "package-reporter-result", self.send_result, timestamp,
                    code, err)
                yield returnValue((out, err, code))
        else:
            logging.debug("'%s' didn't run, conditions not met" %
                          self.apt_update_filename)
            yield returnValue(("", "", 0))

    def _apt_update(self, deferred):
        """
        Run apt-update using the passed in deferred, which allows for callers
        to inspect the result code.
        """
        env = {}
        if self._config.http_proxy:
            env["http_proxy"] = self._config.http_proxy
        if self._config.https_proxy:
            env["https_proxy"] = self._config.https_proxy
        result = spawn_process(self.apt_update_filename, env=env)

        def callback(args, deferred):
            return deferred.callback(args)

        return result.addCallback(callback, deferred)

    def send_result(self, timestamp, code, err):
        """
        Report the package reporter result to the server in a message.
        """
        message = {
            "type": "package-reporter-result",
            "report-timestamp": timestamp,
            "code": code,
            "err": err}
        return self.send_message(message)

    def handle_task(self, task):
        message = task.data
        message_type = message["type"]

        if message_type == "package-ids":
            self._got_task = True
            return self._handle_package_ids(message)
        if message_type == "resynchronize":
            self._got_task = True
            return self._handle_resynchronize()

        # Skip and continue.
        logging.warning("Unknown task message type: {!r}".format(message_type))
        return succeed(None)

    def _handle_package_ids(self, message):
        unknown_hashes = []

        try:
            request = self._store.get_hash_id_request(message["request-id"])
        except UnknownHashIDRequest:
            # We've lost this request somehow.  It will be re-requested later.
            return succeed(None)

        hash_ids = {}

        for hash, id in zip(request.hashes, message["ids"]):
            if id is None:
                unknown_hashes.append(hash)
            else:
                hash_ids[hash] = id

        self._store.set_hash_ids(hash_ids)

        logging.info("Received %d package hash => id translations, %d hashes "
                     "are unknown." % (len(hash_ids), len(unknown_hashes)))

        if unknown_hashes:
            result = self._handle_unknown_packages(unknown_hashes)
        else:
            result = succeed(None)

        # Remove the request if everything goes well.
        result.addCallback(lambda x: request.remove())

        return result

    @inlineCallbacks
    def _handle_resynchronize(self):
        self._store.clear_hash_ids()
        yield self._remove_hash_id_db()
        self._store.clear_available()
        self._store.clear_available_upgrades()
        self._store.clear_installed()
        self._store.clear_locked()
        self._store.clear_hash_id_requests()
        self._store.clear_autoremovable()

    def _handle_unknown_packages(self, hashes):

        self._facade.ensure_channels_reloaded()

        hashes = set(hashes)
        added_hashes = []
        packages = []
        for package in self._facade.get_packages():
            hash = self._facade.get_package_hash(package)
            if hash in hashes:
                added_hashes.append(hash)
                skeleton = self._facade.get_package_skeleton(package)
                packages.append({"type": skeleton.type,
                                 "name": skeleton.name,
                                 "version": skeleton.version,
                                 "section": skeleton.section,
                                 "summary": skeleton.summary,
                                 "description": skeleton.description,
                                 "size": skeleton.size,
                                 "installed-size": skeleton.installed_size,
                                 "relations": skeleton.relations})

        if packages:
            logging.info("Queuing messages with data for %d packages to "
                         "exchange urgently." % len(packages))

            message = {"type": "add-packages", "packages": packages}

            result = self._send_message_with_hash_id_request(message,
                                                             added_hashes)
        else:
            result = succeed(None)

        return result

    def _remove_hash_id_db(self):

        def _remove_it(hash_id_db_filename):
            if hash_id_db_filename and os.path.exists(hash_id_db_filename):
                logging.warning(
                    "Removing cached hash=>id database %s",
                    hash_id_db_filename)
                os.remove(hash_id_db_filename)
        result = self._determine_hash_id_db_filename()
        result.addCallback(_remove_it)
        return result

    def remove_expired_hash_id_requests(self):
        now = time.time()
        timeout = now - HASH_ID_REQUEST_TIMEOUT

        def update_or_remove(is_pending, request):
            if is_pending:
                # Request is still in the queue.  Update the timestamp.
                request.timestamp = now
            elif request.timestamp < timeout:
                # Request was delivered, and is older than the threshold.
                request.remove()

        results = []
        for request in self._store.iter_hash_id_requests():
            if request.message_id is None:
                # May happen in some rare cases, when a send_message() is
                # interrupted abruptly.  If it just fails normally, the
                # request is removed and so we don't get here.
                request.remove()
            else:
                result = self._broker.is_message_pending(request.message_id)
                result.addCallback(update_or_remove, request)
                results.append(result)

        return gather_results(results)

    def request_unknown_hashes(self):
        """Detect available packages for which we have no hash=>id mappings.

        This method will verify if there are packages that APT knows
        about but for which we don't have an id yet (no hash => id
        translation), and deliver a message (unknown-package-hashes)
        to request them.

        Hashes previously requested won't be requested again, unless they
        have already expired and removed from the database.
        """
        self._facade.ensure_channels_reloaded()

        unknown_hashes = set()

        for package in self._facade.get_packages():
            hash = self._facade.get_package_hash(package)
            if self._store.get_hash_id(hash) is None:
                unknown_hashes.add(self._facade.get_package_hash(package))

        # Discard unknown hashes in existent requests.
        for request in self._store.iter_hash_id_requests():
            unknown_hashes -= set(request.hashes)

        if not unknown_hashes:
            result = succeed(None)
        else:
            unknown_hashes = sorted(unknown_hashes)
            unknown_hashes = unknown_hashes[:MAX_UNKNOWN_HASHES_PER_REQUEST]

            logging.info("Queuing request for package hash => id "
                         "translation on %d hash(es)." % len(unknown_hashes))

            message = {"type": "unknown-package-hashes",
                       "hashes": unknown_hashes}

            result = self._send_message_with_hash_id_request(message,
                                                             unknown_hashes)

        return result

    def _send_message_with_hash_id_request(self, message, unknown_hashes):
        """Create a hash_id_request and send message with "request-id"."""
        request = self._store.add_hash_id_request(unknown_hashes)
        message["request-id"] = request.id
        result = self.send_message(message)

        def set_message_id(message_id):
            request.message_id = message_id

        def send_message_failed(failure):
            request.remove()
            return failure

        return result.addCallbacks(set_message_id, send_message_failed)

    def detect_changes(self):
        """Detect all changes concerning packages.

        If some changes were detected with respect to our last run, then an
        event of type 'package-data-changed' will be fired in the broker
        reactor.
        """

        def changes_detected(result):
            if result:
                # Something has changed, notify the broker.
                return self._broker.fire_event("package-data-changed")

        deferred = self.detect_packages_changes()
        return deferred.addCallback(changes_detected)

    def detect_packages_changes(self):
        """
        Check if any information regarding packages have changed, and if so
        compute the changes and send a signal.
        """
        if self._got_task or self._package_state_has_changed():
            return self._compute_packages_changes()
        else:
            return succeed(None)

    def _package_state_has_changed(self):
        """
        Detect changes in the universe of known packages.

        This uses the state of packages in /var/lib/dpkg/state and other files
        and simply checks whether they have changed using their "last changed"
        timestamp on the filesystem.

        @return True if the status changed, False otherwise.
        """
        stamp_file = self._config.detect_package_changes_stamp
        if not os.path.exists(stamp_file):
            return True

        status_file = apt_pkg.config.find_file("dir::state::status")
        lists_dir = apt_pkg.config.find_dir("dir::state::lists")
        files = [status_file, lists_dir]
        files.extend(glob.glob("%s/*Packages" % lists_dir))

        last_checked = os.stat(stamp_file).st_mtime
        for f in files:
            last_changed = os.stat(f).st_mtime
            if last_changed >= last_checked:
                return True
        return False

    def _compute_packages_changes(self):
        """Analyse changes in the universe of known packages.

        This method will verify if there are packages that:

        - are now installed, and were not;
        - are now available, and were not;
        - are now locked, and were not;
        - were previously available but are not anymore;
        - were previously installed but are not anymore;
        - were previously locked but are not anymore;

        Additionally it will report package locks that:

        - are now set, and were not;
        - were previously set but are not anymore;

        Also, packages coming from the security pocket will be
        reported as such.

        In all cases, the server is notified of the new situation
        with a "packages" message.

        @return: A deferred resulting in C{True} if package changes were
            detected with respect to the previous run, or C{False} otherwise.
        """
        self._facade.ensure_channels_reloaded()

        old_installed = set(self._store.get_installed())
        old_available = set(self._store.get_available())
        old_upgrades = set(self._store.get_available_upgrades())
        old_locked = set(self._store.get_locked())
        old_autoremovable = set(self._store.get_autoremovable())
        old_security = set(self._store.get_security())

        current_installed = set()
        current_available = set()
        current_upgrades = set()
        current_locked = set()
        current_autoremovable = set()
        current_security = set()
        lsb = parse_lsb_release(LSB_RELEASE_FILENAME)
        backports_archive = "{}-backports".format(lsb["code-name"])
        security_archive = "{}-security".format(lsb["code-name"])

        for package in self._facade.get_packages():
            # Don't include package versions from the official backports
            # archive. The backports archive is enabled by default since
            # xenial with a pinning policy of 100. Ideally we would
            # support pinning, but we don't yet. In the mean time, we
            # ignore backports, so that packages don't get automatically
            # upgraded to the backports version.
            backport_origins = [
                origin for origin in package.origins
                if origin.archive == backports_archive]
            if backport_origins and (
                    len(backport_origins) == len(package.origins)):
                # Ignore the version if it's only in the official
                # backports archive. If it's somewhere else as well,
                # e.g. a PPA, we assume it was added manually and the
                # user wants to get updates from it.
                continue
            hash = self._facade.get_package_hash(package)
            id = self._store.get_hash_id(hash)
            if id is not None:
                if self._facade.is_package_installed(package):
                    current_installed.add(id)
                    if self._facade.is_package_available(package):
                        current_available.add(id)
                    if self._facade.is_package_autoremovable(package):
                        current_autoremovable.add(id)
                else:
                    current_available.add(id)

                # Are there any packages that this package is an upgrade for?
                if self._facade.is_package_upgrade(package):
                    current_upgrades.add(id)

                # Is this package present in the security pocket?
                security_origins = any(
                    origin for origin in package.origins
                    if origin.archive == security_archive)
                if security_origins:
                    current_security.add(id)

        for package in self._facade.get_locked_packages():
            hash = self._facade.get_package_hash(package)
            id = self._store.get_hash_id(hash)
            if id is not None:
                current_locked.add(id)

        new_installed = current_installed - old_installed
        new_available = current_available - old_available
        new_upgrades = current_upgrades - old_upgrades
        new_locked = current_locked - old_locked
        new_autoremovable = current_autoremovable - old_autoremovable
        new_security = current_security - old_security

        not_installed = old_installed - current_installed
        not_available = old_available - current_available
        not_upgrades = old_upgrades - current_upgrades
        not_locked = old_locked - current_locked
        not_autoremovable = old_autoremovable - current_autoremovable
        not_security = old_security - current_security

        message = {}
        if new_installed:
            message["installed"] = \
                list(sequence_to_ranges(sorted(new_installed)))
        if new_available:
            message["available"] = \
                list(sequence_to_ranges(sorted(new_available)))
        if new_upgrades:
            message["available-upgrades"] = \
                list(sequence_to_ranges(sorted(new_upgrades)))
        if new_locked:
            message["locked"] = \
                list(sequence_to_ranges(sorted(new_locked)))

        if new_autoremovable:
            message["autoremovable"] = list(
                sequence_to_ranges(sorted(new_autoremovable)))
        if not_autoremovable:
            message["not-autoremovable"] = list(
                sequence_to_ranges(sorted(not_autoremovable)))

        if new_security:
            message["security"] = list(
                sequence_to_ranges(sorted(new_security)))
        if not_security:
            message["not-security"] = list(
                sequence_to_ranges(sorted(not_security)))

        if not_installed:
            message["not-installed"] = \
                list(sequence_to_ranges(sorted(not_installed)))
        if not_available:
            message["not-available"] = \
                list(sequence_to_ranges(sorted(not_available)))
        if not_upgrades:
            message["not-available-upgrades"] = \
                list(sequence_to_ranges(sorted(not_upgrades)))
        if not_locked:
            message["not-locked"] = \
                list(sequence_to_ranges(sorted(not_locked)))

        if not message:
            return succeed(False)

        message["type"] = "packages"
        result = self.send_message(message)

        logging.info(
            "Queuing message with changes in known packages: "
            "%(installed)d installed, %(available)d available, "
            "%(upgrades)d available upgrades, %(locked)d locked, "
            "%(auto)d autoremovable, %(security)d security, "
            "%(not_installed)d not installed, "
            "%(not_available)d not available, "
            "%(not_upgrades)d not available upgrades, "
            "%(not_locked)d not locked, "
            "%(not_auto)d not autoremovable, "
            "%(not_security)d not security.",
            dict(
                installed=len(new_installed), available=len(new_available),
                upgrades=len(new_upgrades), locked=len(new_locked),
                auto=len(new_autoremovable), not_installed=len(not_installed),
                not_available=len(not_available),
                not_upgrades=len(not_upgrades), not_locked=len(not_locked),
                not_auto=len(not_autoremovable), security=len(new_security),
                not_security=len(not_security)))

        def update_currently_known(result):
            if new_installed:
                self._store.add_installed(new_installed)
            if not_installed:
                self._store.remove_installed(not_installed)
            if new_available:
                self._store.add_available(new_available)
            if new_locked:
                self._store.add_locked(new_locked)
            if new_autoremovable:
                self._store.add_autoremovable(new_autoremovable)
            if not_available:
                self._store.remove_available(not_available)
            if new_upgrades:
                self._store.add_available_upgrades(new_upgrades)
            if not_upgrades:
                self._store.remove_available_upgrades(not_upgrades)
            if not_locked:
                self._store.remove_locked(not_locked)
            if not_autoremovable:
                self._store.remove_autoremovable(not_autoremovable)
            if new_security:
                self._store.add_security(new_security)
            if not_security:
                self._store.remove_security(not_security)
            # Something has changed wrt the former run, let's update the
            # timestamp and return True.
            stamp_file = self._config.detect_package_changes_stamp
            touch_file(stamp_file)
            return True

        result.addCallback(update_currently_known)

        return result


class FakeGlobalReporter(PackageReporter):
    """
    A standard reporter, which additionally stores messages sent into its
    package store.
    """

    package_store_class = FakePackageStore

    def send_message(self, message):
        self._store.save_message(message)
        return super(FakeGlobalReporter, self).send_message(message)


class FakeReporter(PackageReporter):
    """
    A fake reporter which only sends messages previously stored by a
    L{FakeGlobalReporter}.
    """

    package_store_class = FakePackageStore
    global_store_filename = None

    def run(self):
        result = succeed(None)

        result.addCallback(lambda x: self.get_session_id())

        # If the appropriate hash=>id db is not there, fetch it
        result.addCallback(lambda x: self.fetch_hash_id_db())

        result.addCallback(lambda x: self._store.clear_tasks())

        # Finally, verify if we have anything new to send to the server.
        result.addCallback(lambda x: self.send_pending_messages())

        return result

    def send_pending_messages(self):
        """
        As the last callback of L{PackageReporter}, sends messages stored.
        """
        if self.global_store_filename is None:
            self.global_store_filename = os.environ["FAKE_PACKAGE_STORE"]
        if not os.path.exists(self.global_store_filename):
            return succeed(None)
        message_sent = set(self._store.get_message_ids())
        global_store = FakePackageStore(self.global_store_filename)
        all_message_ids = set(global_store.get_message_ids())
        not_sent = all_message_ids - message_sent
        deferred = succeed(None)
        got_type = set()
        if not_sent:
            messages = global_store.get_messages_by_ids(not_sent)
            sent = []
            for message_id, message in messages:
                message = bpickle.loads(message)
                if message["type"] not in got_type:
                    got_type.add(message["type"])
                    sent.append(message_id)
                    deferred.addCallback(
                        lambda x, message=message: self.send_message(message))
            self._store.save_message_ids(sent)
        return deferred


def main(args):
    # Force UTF-8 encoding only for the reporter, thus allowing libapt-pkg to
    # return unmangled descriptions.
    locale.setlocale(locale.LC_CTYPE, ("C", "UTF-8"))

    if "FAKE_GLOBAL_PACKAGE_STORE" in os.environ:
        return run_task_handler(FakeGlobalReporter, args)
    elif "FAKE_PACKAGE_STORE" in os.environ:
        return run_task_handler(FakeReporter, args)
    else:
        return run_task_handler(PackageReporter, args)


def find_reporter_command(config=None):
    bindir = get_bindir(config)
    return os.path.join(bindir, "landscape-package-reporter")
