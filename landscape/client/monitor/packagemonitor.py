import logging
import os

from twisted.internet.utils import getProcessOutput

from landscape.lib.apt.package.store import PackageStore
from landscape.lib.encoding import encode_values
from landscape.client.package.reporter import find_reporter_command
from landscape.client.monitor.plugin import MonitorPlugin


class PackageMonitor(MonitorPlugin):

    run_interval = 1800
    scope = "package"

    _reporter_command = None

    def __init__(self, package_store_filename=None):
        super(PackageMonitor, self).__init__()
        if package_store_filename:
            self._package_store = PackageStore(package_store_filename)
        else:
            self._package_store = None

    def register(self, registry):
        self.config = registry.config
        self.run_interval = self.config.package_monitor_interval
        if self.config.clones and self.config.is_clone:
            # Run clones a bit more frequently in order to catch up
            self.run_interval = 60  # 300
        super(PackageMonitor, self).register(registry)

        if not self._package_store:
            filename = os.path.join(registry.config.data_path,
                                    "package/database")
            self._package_store = PackageStore(filename)

        registry.register_message("package-ids",
                                  self._enqueue_message_as_reporter_task)
        registry.reactor.call_on("server-uuid-changed",
                                 self._server_uuid_changed)
        self.call_on_accepted("packages", self.spawn_reporter)
        self.run()

    def _enqueue_message_as_reporter_task(self, message):
        self._package_store.add_task("reporter", message)
        self.spawn_reporter()

    def run(self):
        result = self.registry.broker.get_accepted_message_types()
        result.addCallback(self._got_message_types)
        return result

    def _got_message_types(self, message_types):
        if "packages" in message_types:
            self.spawn_reporter()

    def _run_fake_reporter(self, args):
        """Run a fake-reporter in-process."""

        class FakeFacade(object):
            """
            A fake facade to workaround the issue that the AptFacade
            essentially allows only once instance per process.
            """

            def get_arch(self):
                arch = os.uname()[-1]
                result = {"pentium": "i386",
                          "i86pc": "i386",
                          "x86_64": "amd64"}.get(arch)
                if result:
                    arch = result
                elif (arch[0] == "i" and arch.endswith("86")):
                    arch = "i386"
                return arch

        if getattr(self, "_fake_reporter", None) is None:

            from landscape.client.package.reporter import (
                FakeReporter, PackageReporterConfiguration)
            from landscape.lib.apt.package.store import FakePackageStore
            package_facade = FakeFacade()
            package_config = PackageReporterConfiguration()
            package_config.load(args + ["-d", self.config.data_path,
                                        "-l", self.config.log_dir])
            package_store = FakePackageStore(package_config.store_filename)
            self._fake_reporter = FakeReporter(package_store, package_facade,
                                               self.registry.broker,
                                               package_config)
            self._fake_reporter.global_store_filename = os.path.join(
                self.config.master_data_path, "package", "database")
            self._fake_reporter_running = False

        if self._fake_reporter_running:
            from twisted.internet.defer import succeed
            return succeed(None)

        self._fake_reporter_running = True
        result = self._fake_reporter.run()

        def done(passthrough):
            self._fake_reporter_running = False
            return passthrough

        return result.addBoth(done)

    def spawn_reporter(self):
        args = ["--quiet"]
        if self.config.config:
            args.extend(["-c", self.config.config])
        env = os.environ.copy()

        if self.config.clones > 0:
            if self.config.is_clone:
                return self._run_fake_reporter(args)
            else:
                env["FAKE_GLOBAL_PACKAGE_STORE"] = "1"

        if self._reporter_command is None:
            self._reporter_command = find_reporter_command(self.config)
        # path is set to None so that getProcessOutput does not
        # chdir to "." see bug #211373
        env = encode_values(env)
        result = getProcessOutput(self._reporter_command,
                                  args=args, env=env,
                                  errortoo=1,
                                  path=None)
        result.addCallback(self._got_reporter_output)
        return result

    def _got_reporter_output(self, output):
        if output:
            logging.warning("Package reporter output:\n%s" % output)

    def _reset(self):
        """
        Remove all tasks *except* the resynchronize task.  This is
        because if we clear all tasks, then add the resynchronize,
        it's possible that the reporter may be running a task at this
        time and when it finishes, it will unknowningly remove the
        resynchronize task because sqlite resets its serial primary
        keys when you delete an entire table.  This problem is avoided
        by adding the task first and removing them all *except* the
        resynchronize task and not causing sqlite to reset the serial
        key.
        """
        task = self._package_store.add_task("reporter",
                                            {"type": "resynchronize"})
        self._package_store.clear_tasks(except_tasks=(task,))

    def _server_uuid_changed(self, old_uuid, new_uuid):
        """Called when the broker sends a server-uuid-changed event.

        The package hash=>id map is server-specific, so when we change
        servers, we should reset this map.
        """
        # If the old_uuid is None, it means we're just starting to
        # communicate with a server that knows how to report its UUID,
        # so we don't clear our knowledge.
        if old_uuid is not None:
            self._package_store.clear_hash_ids()
