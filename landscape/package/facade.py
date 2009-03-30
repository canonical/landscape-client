from smart.transaction import Transaction, PolicyInstall, PolicyUpgrade, Failed
from smart.const import INSTALL, REMOVE, UPGRADE, ALWAYS, NEVER

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

class ChannelError(Exception):
    """Raised when channels fail to load."""


class SmartFacade(object):
    """Wrapper for tasks using Smart.

    This object wraps Smart features, in a way that makes using and testing
    these features slightly more comfortable.
    """

    _deb_package_type = None

    def __init__(self, smart_init_kwargs={}):
        """
        @param smart_init_kwargs: A dictionary that can be used to pass
            specific keyword parameters to to L{smart.init}.
        """
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
        self._channels = {}

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

            if self._channels:
                smart.sysconf.set("channels", self._channels)

            self.smart_initialized()
        return self._ctrl

    def smart_initialized(self):
        """Hook called when the Smart library is initialized."""

    def reload_channels(self):
        """
        Reload Smart channels, getting all the cache (packages) in memory.

        @raise: L{ChannelError} if Smart fails to reload the channels.
        """
        ctrl = self._get_ctrl()

        if self.get_channels():
            # This tells smart to download the APT package lists
            caching = NEVER
        else:
            caching = ALWAYS
        reload_result = ctrl.reloadChannels(caching=caching)

        if reload_result == False and caching == NEVER:
            # Raise an error only if we are using some custom channels
            # set with add_channel()
            raise ChannelError("Smart failed to reload channels (%s)"
                               % smart.sysconf.get("channels"))

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

        @return: a L{PackageSkeleton} object.
        """
        return build_skeleton(pkg, with_info)

    def get_package_hash(self, pkg):
        """Return a hash from the given package.

        @param pkg: a L{smart.backends.deb.base.DebPackage} objects
        """
        return self._pkg2hash.get(pkg)

    def get_packages(self):
        """
        Get all packages available in the channels.

        @return: a C{list} of L{smart.backends.deb.base.DebPackage} objects
        """
        return [pkg for pkg in self._get_ctrl().getCache().getPackages()
                if isinstance(pkg, self._deb_package_type)]

    def get_packages_by_name(self, name):
        """
        Get all available packages matching the provided name.

        @return: a C{list} of L{smart.backends.deb.base.DebPackage} objects
        """
        return [pkg for pkg in self._get_ctrl().getCache().getPackages(name)
                if isinstance(pkg, self._deb_package_type)]

    def get_package_by_hash(self, hash):
        """
        Get all available packages matching the provided hash.

        @return: a C{list} of L{smart.backends.deb.base.DebPackage} objects
        """
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

    def add_apt_deb_channel(self, baseurl, distribution, components):
        """Build a Smart C{apt-deb} channel and pass it to L{add_channel}."""

        alias = "alias%d" % len(self._channels)
        channel = {"baseurl": baseurl,
                   "distribution": distribution,
                   "components": " ".join(components),
                   'type': 'apt-deb'}
        self.add_channel(alias, channel)

    def add_channel(self, alias, channel):
        """
        Add a Smart channel.

        This method can be called more than once to set multiple channels.
        To take effect it must be called before L{reaload_channels}.

        @param alias: A string indentifying the channel to be added.
        @param channel: A C{dict} meeting the format defined by the Smart API.
        """
        self._channels.update({alias : channel})

    def get_channels(self):
        """
        @type: C{dict}
        @return: The alias/channel associations set with L{add_channel}.
        """
        return self._channels
