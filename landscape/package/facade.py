from smart.transaction import Transaction, PolicyInstall, PolicyUpgrade, Failed
from smart.const import INSTALL, REMOVE, UPGRADE

import smart

from landscape.package.skeleton import build_skeleton


class TransactionError(Exception):
    """Raised when the transaction fails to run."""

class DependencyError(Exception):
    """Raised when a needed dependency wasn't explicitly marked."""

    def __init__(self, packages):
        self.packages = packages

    def __str__(self):
        return ("Missing dependencies: %s" %
                ", ".join([str(package) for package in self.packages]))

class SmartError(Exception):
    """Raised when Smart fails in an undefined way."""


class SmartFacade(object):
    """Wrapper for tasks using Smart.

    This object wraps Smart features, in a way that makes using and testing
    these features slightly more comfortable.
    """

    _deb_package_type = None

    def __init__(self, smart_init_kwargs={}):
        self._smart_init_kwargs = smart_init_kwargs.copy()
        self._smart_init_kwargs.setdefault("interface", "landscape")
        self._reset()

    def _reset(self):
        # This attribute is initialized lazily in the _get_ctrl() method.
        self._ctrl = None

        self._pkg2hash = {}
        self._hash2pkg = {}

        self._marks = {}

        self._arch = None

    def deinit(self):
        """Deinitialize the Facade and the Smart library."""
        if self._ctrl:
            smart.deinit()
        self._reset()

    def _get_ctrl(self):
        if self._ctrl is None:
            if self._smart_init_kwargs.get("interface") == "landscape":
                from landscape.package.interface import (
                    install_landscape_interface)
                install_landscape_interface()
            self._ctrl = smart.init(**self._smart_init_kwargs)
            smart.sysconf.set("pm-iface-output", True, soft=True)
            smart.sysconf.set("deb-non-interactive", True, soft=True)

            # We can't import it before hand because reaching .deb.* depends
            # on initialization (yeah, sucky).
            from smart.backends.deb.base import DebPackage
            self._deb_package_type = DebPackage

            if self._arch is not None:
                smart.sysconf.set("deb-arch", self._arch)

            self.smart_initialized()
        return self._ctrl

    def smart_initialized(self):
        """Hook called when the Smart library is initialized."""

    def reload_channels(self):
        """Reload Smart channels, getting all the cache (packages) in memory.
        """
        ctrl = self._get_ctrl()
        ctrl.reloadChannels()

        self._hash2pkg.clear()
        self._pkg2hash.clear()

        for pkg in self.get_packages():
            hash = self.get_package_skeleton(pkg, False).get_hash()
            self._hash2pkg[hash] = pkg
            self._pkg2hash[pkg] = hash

        self.channels_reloaded()

    def channels_reloaded(self):
        """Hook called after Smart channels are reloaded."""

    def get_package_skeleton(self, pkg, with_info=True):
        """Return a skeleton for the provided package.

        The skeleton represents the basic structure of the package.

        @param pkg: Package to build skeleton from.
        @param with_info: If True, the skeleton will include information
            useful for sending data to the server.  Such information isn't
            necessary if the skeleton will be used to build a hash.
        """
        return build_skeleton(pkg, with_info)

    def get_package_hash(self, pkg):
        """Return a hash from the given package."""
        return self._pkg2hash.get(pkg)

    def get_packages(self):
        return [pkg for pkg in self._get_ctrl().getCache().getPackages()
                if isinstance(pkg, self._deb_package_type)]

    def get_packages_by_name(self, name):
        """Return a list with all known (available) packages."""
        return [pkg for pkg in self._get_ctrl().getCache().getPackages(name)
                if isinstance(pkg, self._deb_package_type)]

    def get_package_by_hash(self, hash):
        return self._hash2pkg.get(hash)

    def mark_install(self, pkg):
        self._marks[pkg] = INSTALL

    def mark_remove(self, pkg):
        self._marks[pkg] = REMOVE

    def mark_upgrade(self, pkg):
        self._marks[pkg] = UPGRADE

    def reset_marks(self):
        self._marks.clear()

    def perform_changes(self):
        ctrl = self._get_ctrl()
        cache = ctrl.getCache()

        transaction = Transaction(cache)

        policy = PolicyInstall

        for pkg, oper in self._marks.items():
            if oper == UPGRADE:
                policy = PolicyUpgrade
            transaction.enqueue(pkg, oper)

        transaction.setPolicy(policy)

        try:
            transaction.run()
        except Failed, e:
            raise TransactionError(e.args[0])
        changeset = transaction.getChangeSet()

        if not changeset:
            return None # Nothing to do.

        missing = []
        for pkg, op in changeset.items():
            if self._marks.get(pkg) != op:
                missing.append(pkg)
        if missing:
            raise DependencyError(missing)

        self._ctrl.commitChangeSet(changeset)

        output = smart.iface.get_output_for_landscape()
        failed = smart.iface.has_failed_for_landscape()

        smart.iface.reset_for_landscape()

        if failed:
            raise SmartError(output)
        return output

    def reload_cache(self):
        cache = self._get_ctrl().getCache()
        cache.reset()
        cache.load()

    def set_arch(self, arch):
        """
        Set the host architecture.

        To take effect it must be called before L{reaload_channels}.

        @param arch: the dpkg architecture to use (e.g. C{"i386"})
        """
        self._arch = arch
