import urlparse
import logging
import time
import sys
import os

from twisted.internet.defer import Deferred, succeed
from twisted.internet.utils import getProcessOutputAndValue

from landscape.lib.sequenceranges import sequence_to_ranges
from landscape.lib.twisted_util import gather_results
from landscape.lib.fetch import fetch_async

from landscape.package.taskhandler import PackageTaskHandler, run_task_handler
from landscape.package.store import UnknownHashIDRequest


HASH_ID_REQUEST_TIMEOUT = 7200
MAX_UNKNOWN_HASHES_PER_REQUEST = 500


class PackageReporter(PackageTaskHandler):
    """Report information about the system packages.

    @cvar queue_name: Name of the task queue to pick tasks from.
    @cvar smart_update_interval: Time interval in minutes to pass to
        the C{--after} command line option of C{smart-update}.
    """
    queue_name = "reporter"
    smart_update_interval = 60
    smart_update_filename = "/usr/lib/smart/smart-update"

    def run(self):
        result = Deferred()

        # If the appropriate hash=>id db is not there, fetch it
        result.addCallback(lambda x: self.fetch_hash_id_db())

        # Attach the hash=>id database if available
        result.addCallback(lambda x: self.use_hash_id_db())

        # Run smart-update
        result.addCallback(lambda x: self.run_smart_update())

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

            if not hash_id_db_filename:
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
                logging.info("Downloaded hash=>id database from %s" % url)
                hash_id_db_fd = open(hash_id_db_filename, "w")
                hash_id_db_fd.write(data)
                hash_id_db_fd.close()

            def fetch_error(failure):
                exception = failure.value
                logging.warning("Couldn't download hash=>id database: %s" %
                                str(exception))

            result = fetch_async(url)
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

    def run_smart_update(self):
        """Run smart-update and log a warning in case of non-zero exit code.

        @return: a deferred returning (out, err, code)
        """
        result = getProcessOutputAndValue(self.smart_update_filename,
                                          args=("--after", "%d" %
                                                self.smart_update_interval))

        def callback((out, err, code)):
            if code != 0:
                logging.warning("'%s' exited with status %d (%s)" % (
                    self.smart_update_filename, code, out))
            return (out, err, code)

        result.addCallback(callback)
        return result

    def handle_task(self, task):
        message = task.data
        if message["type"] == "package-ids":
            return self._handle_package_ids(message)
        if message["type"] == "resynchronize":
            return self._handle_resynchronize()

    def _handle_package_ids(self, message):
        unknown_hashes = []
        request_id = message["request-id"]

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

    def _handle_resynchronize(self):
        self._store.clear_available()
        self._store.clear_available_upgrades()
        self._store.clear_installed()
        self._store.clear_hash_id_requests()
        return succeed(None)

    def _handle_unknown_packages(self, hashes):

        self.ensure_channels_reloaded()

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

        This method will verify if there are packages that Smart knows
        about but for which we don't have an id yet (no hash => id
        translation), and deliver a message (unknown-package-hashes)
        to request them.

        Hashes previously requested won't be requested again, unless they
        have already expired and removed from the database.
        """
        self.ensure_channels_reloaded()

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
        result = self._broker.send_message(message, True)
        def set_message_id(message_id):
            request.message_id = message_id
        def send_message_failed(failure):
            request.remove()
            return failure
        return result.addCallbacks(set_message_id, send_message_failed)

    def detect_changes(self):
        """Detect changes in the universe of known packages.

        This method will verify if there are packages that:

        - are now installed, and were not;
        - are now available, and were not;
        - were previously available but are not anymore;
        - were previously installed but are not anymore;

        In all cases, the server is notified of the new situation
        with a "packages" message.
        """
        self.ensure_channels_reloaded()

        old_installed = set(self._store.get_installed())
        old_available = set(self._store.get_available())
        old_upgrades = set(self._store.get_available_upgrades())

        current_installed = set()
        current_available = set()
        current_upgrades = set()

        for package in self._facade.get_packages():
            hash = self._facade.get_package_hash(package)
            id = self._store.get_hash_id(hash)
            if id is not None:
                if package.installed:
                    current_installed.add(id)
                    for loader in package.loaders:
                        # Is the package also in a non-installed
                        # loader?  IOW, "available".
                        if not loader.getInstalled():
                            current_available.add(id)
                            break
                else:
                    current_available.add(id)

                # Are there any packages that this package is an upgrade for?
                for upgrade in package.upgrades:
                    for provides in upgrade.providedby:
                        for provides_package in provides.packages:
                            if provides_package.installed:
                                current_upgrades.add(id)
                                break
                        else:
                            continue
                        break
                    else:
                        continue
                    break

        new_installed = current_installed - old_installed
        new_available = current_available - old_available
        new_upgrades = current_upgrades - old_upgrades

        not_installed = old_installed - current_installed
        not_available = old_available - current_available
        not_upgrades = old_upgrades - current_upgrades

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

        if not_installed:
            message["not-installed"] = \
                list(sequence_to_ranges(sorted(not_installed)))
        if not_available:
            message["not-available"] = \
                list(sequence_to_ranges(sorted(not_available)))
        if not_upgrades:
            message["not-available-upgrades"] = \
                list(sequence_to_ranges(sorted(not_upgrades)))

        if not message:
            result = succeed(None)
        else:
            message["type"] = "packages"

            result = self._broker.send_message(message, True)

            logging.info("Queuing message with changes in known packages: "
                         "%d installed, %d available, %d available upgrades, "
                         "%d not installed, %d not available, %d not "
                         "available upgrades."
                         % (len(new_installed), len(new_available),
                            len(new_upgrades), len(not_installed),
                            len(not_available), len(not_upgrades)))

        def update_currently_known(result):
            if new_installed:
                self._store.add_installed(new_installed)
            if not_installed:
                self._store.remove_installed(not_installed)
            if new_available:
                self._store.add_available(new_available)
            if not_available:
                self._store.remove_available(not_available)
            if new_upgrades:
                self._store.add_available_upgrades(new_upgrades)
            if not_upgrades:
                self._store.remove_available_upgrades(not_upgrades)

        result.addCallback(update_currently_known)

        return result


def main(args):
    return run_task_handler(PackageReporter, args)


def find_reporter_command():
    dirname = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(dirname, "landscape-package-reporter")
