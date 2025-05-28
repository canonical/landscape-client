import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Container
from io import StringIO
from operator import attrgetter

import apt
import apt_inst
import apt_pkg
from apt.progress.base import InstallProgress
from apt.progress.text import AcquireProgress
from aptsources.sourceslist import SourcesList

from .skeleton import build_skeleton_apt
from landscape.lib.fs import append_text_file
from landscape.lib.fs import create_text_file
from landscape.lib.fs import read_binary_file
from landscape.lib.fs import read_text_file
from landscape.lib.fs import touch_file


class TransactionError(Exception):
    """Raised when the transaction fails to run."""


class DependencyError(Exception):
    """Raised when a needed dependency wasn't explicitly marked."""

    def __init__(self, packages):
        self.packages = packages

    def __str__(self):
        return "Missing dependencies: {}".format(
            ", ".join(
                [str(package) for package in self.packages],
            ),
        )


class ChannelError(Exception):
    """Raised when channels fail to load."""


class LandscapeAcquireProgress(AcquireProgress):
    def _winch(self, *dummy):
        """Override trying to get the column count of the buffer.

        We always send the output to a file, not to a terminal, so the
        default width (80 columns) is fine for us.

        Overriding this method means that we don't have to care about
        fcntl.ioctl API differences for different Python versions.
        """

    def pulse(self, owner):
        """Override updating the acquire progress, which needs a tty.

        Under Python3, StringIO.fileno() raises UnsupportedOperation instead
        of an AttributeError. This would be uncaught by apt, thus we force a
        NOOP here.
        """
        return True


class LandscapeInstallProgress(InstallProgress):

    dpkg_exited = None
    old_excepthook = None

    def wait_child(self):
        """Override to find out whether dpkg exited or not.

        The C{run()} method returns os.WEXITSTATUS(res) without checking
        os.WIFEXITED(res) first, so it can signal that everything is ok,
        even though something causes dpkg not to exit cleanly.

        Save whether dpkg exited cleanly into the C{dpkg_exited}
        attribute. If dpkg exited cleanly the exit code can be used to
        determine whether there were any errors. If dpkg didn't exit
        cleanly it should mean that something went wrong.
        """
        res = super().wait_child()
        self.dpkg_exited = os.WIFEXITED(res)
        return res

    def fork(self):
        """Fork and override the excepthook in the child process."""
        pid = super().fork()
        if pid == 0:
            # No need to clean up after ourselves, since the child
            # process will die after dpkg has been run.
            self.old_excepthook = sys.excepthook
            sys.excepthook = self._prevent_dpkg_apport_error
        return pid

    def _prevent_dpkg_apport_error(self, exc_type, exc_obj, exc_tb):
        """Prevent dpkg errors from generating Apport crash reports.

        When dpkg reports an error, a SystemError is raised and cleaned
        up in C code. However, it seems like the Apport except hook is
        called before the C code clears the error, generating crash
        reports even though nothing crashed.

        This exception hook doesn't call the Apport hook for
        SystemErrors, but it calls it for all other errors.
        """
        if exc_type is SystemError:
            sys.__excepthook__(exc_type, exc_obj, exc_tb)
            return
        self.old_excepthook(exc_type, exc_obj, exc_tb)


class AptFacade:
    """Wrapper for tasks using Apt.

    This object wraps Apt features, in a way that makes using and testing
    these features slightly more comfortable.

    :param root: The root dir of the Apt configuration files.
    :param ignore_sources: Sources with URIs in this container are reloaded and
        their packages are not considered during reporting.
    :ivar refetch_package_index: Whether to refetch the package indexes
        when reloading the channels, or reuse the existing local
        database.
    """

    max_dpkg_retries = 12  # number of dpkg retries before we give up
    dpkg_retry_sleep = 5
    _dpkg_status = "/var/lib/dpkg/status"

    def __init__(
        self,
        root: str | None = None,
        ignore_sources: Container = {},
        alt_sourceparts: str = "",
    ) -> None:
        self._root = root
        self._dpkg_args = []
        if self._root is not None:
            self._ensure_dir_structure()
            self._dpkg_args.extend(["--root", self._root])
        # don't use memonly=True here because of a python-apt bug on Natty when
        # sources.list contains invalid lines (LP: #886208)
        self._cache = apt.cache.Cache(rootdir=root)
        self._channels_loaded = False
        self._pkg2hash = {}
        self._hash2pkg = {}
        self._version_installs = []
        self._package_installs = set()
        self._global_upgrade = False
        self._version_removals = []
        self._version_hold_creations = []
        self._version_hold_removals = []
        self.refetch_package_index = False

        if ignore_sources and alt_sourceparts:
            self._configure_apt_cache(ignore_sources, alt_sourceparts)

    def _configure_apt_cache(
        self,
        ignore_sources: Container,
        alt_sourceparts,
    ) -> None:
        """Configures the cache to only use sources not in `ignore_sources`.

        This is done by configuring apt to use a different directory for the
        "sourceparts" config rather than the usual "/etc/apt/sources.list.d".

        See apt.cache.Cache.update for an example of how this works.
        """
        if os.path.exists(alt_sourceparts):
            try:
                shutil.rmtree(alt_sourceparts)
            except NotADirectoryError:
                os.remove(alt_sourceparts)

        os.makedirs(alt_sourceparts, exist_ok=True)

        sourceparts = apt_pkg.config.find_dir("Dir::Etc::sourceparts")

        for sourcepart in os.scandir(sourceparts):
            name = sourcepart.name
            if name not in ignore_sources:
                logging.debug("Copying source %s to %s", name, alt_sourceparts)
                shutil.copy(sourcepart, alt_sourceparts)
            else:
                logging.debug("Ignoring source %s", name)

        apt_pkg.config.set("Dir::Etc::sourceparts", alt_sourceparts)

        self._cache = apt.cache.Cache(rootdir=self._root)

    def _ensure_dir_structure(self):
        apt_dir = self._ensure_sub_dir("etc/apt")
        self._ensure_sub_dir("etc/apt/sources.list.d")
        self._ensure_sub_dir("etc/apt/preferences.d")
        self._ensure_sub_dir("var/cache/apt/archives/partial")
        self._ensure_sub_dir("var/lib/apt/lists/partial")
        dpkg_dir = self._ensure_sub_dir("var/lib/dpkg")
        self._ensure_sub_dir("var/lib/dpkg/info")
        self._ensure_sub_dir("var/lib/dpkg/updates")
        self._ensure_sub_dir("var/lib/dpkg/triggers")
        create_text_file(os.path.join(dpkg_dir, "available"), "")
        self._dpkg_status = os.path.join(dpkg_dir, "status")
        if not os.path.exists(self._dpkg_status):
            create_text_file(self._dpkg_status, "")
        # Apt will fail if it does not have a keyring. It does not care if
        # the keyring is empty. (Do not create one if dir exists LP: #1973202)
        if not os.path.isdir(os.path.join(apt_dir, "trusted.gpg.d")):
            touch_file(os.path.join(apt_dir, "trusted.gpg"))

    def _ensure_sub_dir(self, sub_dir):
        """Ensure that a dir in the Apt root exists."""
        full_path = os.path.join(self._root, sub_dir)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
        return full_path

    def get_packages(self):
        """Get all the packages available in the channels."""
        return self._hash2pkg.values()

    def get_locked_packages(self):
        """Get all packages in the channels that are locked.

        For Apt, it means all packages that are held.
        """
        return [
            version
            for version in self.get_packages()
            if (
                self.is_package_installed(version)
                and self._is_package_held(version.package)
            )
        ]

    def get_package_holds(self):
        """Return the name of all the packages that are on hold."""
        return sorted(
            [version.package.name for version in self.get_locked_packages()],
        )

    def _set_dpkg_selections(self, selection):
        """Set the dpkg selection.

        It basically does "echo $selection | dpkg --set-selections".
        """
        process = subprocess.Popen(
            ["dpkg", "--set-selections"] + self._dpkg_args,
            stdin=subprocess.PIPE,
        )
        # We need bytes here to communicate with the process.
        process.communicate(selection.encode("utf-8"))

    def set_package_hold(self, version):
        """Add a dpkg hold for a package.

        @param version: The version of the package to hold.
        """
        self._set_dpkg_selections(version.package.name + " hold")

    def remove_package_hold(self, version):
        """Removes a dpkg hold for a package.

        @param version: The version of the package to unhold.
        """
        if not self.is_package_installed(version) or not self._is_package_held(
            version.package,
        ):
            return
        self._set_dpkg_selections(version.package.name + " install")

    def reload_channels(self, force_reload_binaries=False):
        """Reload the channels and update the cache.

        @param force_reload_binaries: Whether to always reload
            information about the binaries packages that are in the facade's
            internal repo.
        """
        self._cache.open(None)
        internal_sources_list = self._get_internal_sources_list()
        if self.refetch_package_index or (
            force_reload_binaries and os.path.exists(internal_sources_list)
        ):

            # Try to update only the internal repos, if the python-apt
            # version is new enough to accept a sources_list parameter.
            new_apt_args = {}
            if force_reload_binaries and not self.refetch_package_index:
                new_apt_args["sources_list"] = internal_sources_list
            try:
                try:
                    self._cache.update(**new_apt_args)
                except TypeError:
                    self._cache.update()
            except apt.cache.FetchFailedException:
                channels = self.get_channels()
                msg = f"Apt failed to reload channels ({channels!r})"
                raise ChannelError(msg)
            self._cache.open(None)

        self._pkg2hash.clear()
        self._hash2pkg.clear()
        for package in self._cache:
            if not self._is_main_architecture(package):
                continue
            for version in package.versions:
                skeleton_hash = self.get_package_skeleton(
                    version,
                    with_info=False,
                ).get_hash()
                # Use a tuple including the package, since the Version
                # objects of two different packages can have the same
                # hash.
                self._pkg2hash[(package, version)] = skeleton_hash
                self._hash2pkg[skeleton_hash] = version
        self._channels_loaded = True

    def ensure_channels_reloaded(self):
        """Reload the channels if they haven't been reloaded yet."""
        if self._channels_loaded:
            return
        self.reload_channels()

    @property
    def _sourceparts_directory(self):
        return apt_pkg.config.find_dir("Dir::Etc::sourceparts")

    def _get_internal_sources_list(self):
        """Return the path to the source.list file for the facade channels."""
        return os.path.join(
            self._sourceparts_directory,
            "_landscape-internal-facade.list",
        )

    def add_channel_apt_deb(
        self,
        url,
        codename,
        components=None,
        trusted=None,
    ):
        """Add a deb URL which points to a repository.

        @param url: The base URL of the repository.
        @param codename: The dist in the repository.
        @param components: The components to be included.
        @param trusted: Whether validation should be skipped (if local).
        """
        sources_file_path = self._get_internal_sources_list()
        source_options = ""
        if trusted is not None and url.startswith("file:"):
            trusted_val = "yes" if trusted else "no"
            source_options = f"[ trusted={trusted_val} ] "
        sources_line = f"deb {source_options}{url} {codename}"
        if components:
            sources_line += " {}".format(" ".join(components))
        if os.path.exists(sources_file_path):
            current_content = read_text_file(sources_file_path).split("\n")
            if sources_line in current_content:
                return
        sources_line += "\n"
        append_text_file(sources_file_path, sources_line)

    def add_channel_deb_dir(self, path):
        """Add a directory with packages as a channel.

        @param path: The path to the directory containing the packages.

        A Packages file is created in the directory with information
        about the deb files.
        """
        self._create_packages_file(path)
        # yakkety+ validate even file repository by default. deb dirs don't
        # have a signed Release file but are local so they should be trusted.
        self.add_channel_apt_deb(f"file://{path}", "./", None, trusted=True)

    def clear_channels(self):
        """Clear the channels that have been added through the facade.

        Channels that weren't added through the facade (i.e.
        /etc/apt/sources.list and /etc/apt/sources.list.d) won't be
        removed.
        """
        sources_file_path = self._get_internal_sources_list()
        if os.path.exists(sources_file_path):
            os.remove(sources_file_path)

    def _create_packages_file(self, deb_dir):
        """Create a Packages file in a directory with debs."""
        packages = sorted(os.listdir(deb_dir))
        with open(os.path.join(deb_dir, "Packages"), "wb", 0) as dest:
            for i, filename in enumerate(packages):
                if i > 0:
                    dest.write(b"\n")
                deb_file = os.path.join(deb_dir, filename)
                self.write_package_stanza(deb_file, dest)

    def get_channels(self):
        """Return a list of channels configured.

        A channel is a deb line in sources.list or sources.list.d. It's
        represented by a dict with baseurl, distribution, components,
        and type keys.
        """
        sources_list = SourcesList()
        if hasattr(sources_list, "deb822"):
            sources_list.deb822 = True
            sources_list.refresh()

        return [
            {
                "baseurl": entry.uri,
                "distribution": entry.dist,
                "components": " ".join(entry.comps),
                "type": entry.type,
            }
            for entry in sources_list
            if not entry.disabled
        ]

    def reset_channels(self):
        """Remove all the configured channels."""
        sources_list = SourcesList()
        if hasattr(sources_list, "deb822"):
            sources_list.deb822 = True
            sources_list.refresh()

        for entry in sources_list:
            entry.set_enabled(False)
        sources_list.save()

    def write_package_stanza(self, deb_path, dest):
        """Write a stanza for the package to a Packages file.

        @param deb_path: The path to the deb package.
        @param dest: A writable package file.
        """
        deb_file = open(deb_path)
        deb = apt_inst.DebFile(deb_file)
        control = deb.control.extractdata("control")
        deb_file.close()
        filename = os.path.basename(deb_path)
        size = os.path.getsize(deb_path)
        contents = read_binary_file(deb_path)
        md5 = hashlib.md5(contents).hexdigest()
        sha1 = hashlib.sha1(contents).hexdigest()
        sha256 = hashlib.sha256(contents).hexdigest()
        tag_section = apt_pkg.TagSection(control)
        new_tags = [
            ("Filename", filename),
            ("Size", str(size)),
            ("MD5sum", md5),
            ("SHA1", sha1),
            ("SHA256", sha256),
        ]
        try:
            tag_section.write(
                dest,
                apt_pkg.REWRITE_PACKAGE_ORDER,
                [apt_pkg.TagRewrite(k, v) for k, v in new_tags],
            )
        except AttributeError:
            # support for python-apt < 1.9
            section = apt_pkg.rewrite_section(
                tag_section,
                apt_pkg.REWRITE_PACKAGE_ORDER,
                new_tags,
            )
            dest.write(section.encode("utf-8"))

    def get_arch(self):
        """Return the architecture APT is configured to use."""
        return apt_pkg.config.get("APT::Architecture")

    def set_arch(self, architecture):
        """Set the architecture that APT should use.

        Setting multiple architectures isn't supported.
        """
        if architecture is None:
            architecture = ""
        # From oneiric and onwards Architectures is used to set which
        # architectures can be installed, in case multiple architectures
        # are supported. We force it to be single architecture, until we
        # have a plan for supporting multiple architectures.
        apt_pkg.config.clear("APT::Architectures")
        apt_pkg.config.set("APT::Architectures::", architecture)
        result = apt_pkg.config.set("APT::Architecture", architecture)
        # Reload the cache, otherwise architecture change isn't reflected in
        # package list
        self._cache.open(None)
        return result

    def get_package_skeleton(self, pkg, with_info=True):
        """Return a skeleton for the provided package.

        The skeleton represents the basic structure of the package.

        @param pkg: Package to build skeleton from.
        @param with_info: If True, the skeleton will include information
            useful for sending data to the server.  Such information isn't
            necessary if the skeleton will be used to build a hash.

        @return: a L{PackageSkeleton} object.
        """
        return build_skeleton_apt(pkg, with_info=with_info, with_unicode=True)

    def get_package_hash(self, version):
        """Return a hash from the given package.

        @param version: an L{apt.package.Version} object.
        """
        return self._pkg2hash.get((version.package, version))

    def get_package_hashes(self):
        """Get the hashes of all the packages available in the channels."""
        return self._pkg2hash.values()

    def get_package_by_hash(self, hash):
        """Get the package having the provided hash.

        @param hash: The hash the package should have.

        @return: The L{apt.package.Package} that has the given hash.
        """
        return self._hash2pkg.get(hash)

    def is_package_installed(self, version):
        """Is the package version installed?"""
        return version == version.package.installed

    def is_package_available(self, version):
        """Is the package available for installation?"""
        return version.downloadable

    def is_package_upgrade(self, version):
        """Is the package an upgrade for another installed package?"""
        if not version.package.is_upgradable or not version.package.installed:
            return False
        return version > version.package.installed

    def is_package_autoremovable(self, version):
        """Was the package auto-installed, but isn't required anymore?"""
        return version.package.is_auto_removable

    def _is_main_architecture(self, package):
        """Is the package for the facade's main architecture?"""
        # package.name includes the architecture, if it's for a foreign
        # architectures. package.shortname never includes the
        # architecture. package.shortname doesn't exist on releases that
        # don't support multi-arch, though.
        if not hasattr(package, "shortname"):
            return True
        return package.name == package.shortname

    def _is_package_held(self, package):
        """Is the package marked as held?"""
        return package._pkg.selected_state == apt_pkg.SELSTATE_HOLD

    def get_packages_by_name(self, name):
        """Get all available packages matching the provided name.

        @param name: The name the returned packages should have.
        """
        return [
            version
            for version in self.get_packages()
            if version.package.name == name
        ]

    def _is_package_broken(self, package):
        """Is the package broken?

        It's considered broken if it's one that we marked for install,
        but it's not marked for install, upgrade or downgrade
        anymore.

        Before Trusty, checking is_inst_broken was enough, but
        in Trusty the behaviour changed, so the package simply gets
        unmarked for installation.
        """
        if package.is_inst_broken:
            return True
        if (
            not package.marked_install
            and not package.marked_upgrade
            and not package.marked_downgrade
        ):
            return package in self._package_installs
        return False

    def _get_broken_packages(self):
        """Return the packages that are in a broken state."""
        return {
            version.package
            for version in self.get_packages()
            if self._is_package_broken(version.package)
        }

    def _get_changed_versions(self, package):
        """Return the versions that will be changed for the package.

        Apt gives us that a package is going to be changed and have
        variables set on the package to indicate what will change. We
        need to convert that into a list of versions that will be either
        installed or removed, which is what the server expects to get.
        """
        if package.marked_install:
            return [package.candidate]
        if package.marked_upgrade or package.marked_downgrade:
            return [package.installed, package.candidate]
        if package.marked_delete:
            return [package.installed]
        return None

    def _check_changes(self, requested_changes):
        """Check that the changes Apt will do have all been requested.

        @raises DependencyError: If some change hasn't been explicitly
            requested.
        @return: C{True} if all the changes that Apt will perform have
            been requested.
        """
        # Build tuples of (package, version) so that we can do
        # comparison checks. Same versions of different packages compare
        # as being the same, so we need to include the package as well.
        all_changes = [
            (version.package, version) for version in requested_changes
        ]
        versions_to_be_changed = set()
        for package in self._cache.get_changes():
            if not self._is_main_architecture(package):
                continue
            versions = self._get_changed_versions(package)
            versions_to_be_changed.update(
                (package, version) for version in versions
            )
        dependencies = versions_to_be_changed.difference(all_changes)
        if dependencies:
            raise DependencyError(
                [version for package, version in dependencies],
            )
        return len(versions_to_be_changed) > 0

    def _get_unmet_relation_info(self, dep_relation):
        """Return a string representation of a specific dependency relation."""
        info = dep_relation.target_pkg.name
        if dep_relation.target_ver:
            info += " ({} {})".format(
                dep_relation.comp_type,
                dep_relation.target_ver,
            )
        reason = " but is not installable"
        if dep_relation.target_pkg.name in self._cache:
            dep_package = self._cache[dep_relation.target_pkg.name]
            if dep_package.installed or dep_package.marked_install:
                version = dep_package.candidate.version
                if dep_package not in self._cache.get_changes():
                    version = dep_package.installed.version
                reason = f" but {version} is to be installed"
        info += reason
        return info

    def _is_dependency_satisfied(self, dependency, dep_type):
        """Return whether a dependency is satisfied.

        For positive dependencies (Pre-Depends, Depends) it means that
        one of its targets is going to be installed. For negative
        dependencies (Conflicts, Breaks), it means that none of its
        targets are going to be installed.
        """
        is_positive = dep_type not in ["Breaks", "Conflicts"]
        depcache = self._cache._depcache
        for or_dep in dependency:
            for target in or_dep.all_targets():
                package = target.parent_pkg
                if (
                    package.current_state == apt_pkg.CURSTATE_INSTALLED
                    or depcache.marked_install(package)
                ) and not depcache.marked_delete(package):

                    return is_positive
        return not is_positive

    def _get_unmet_dependency_info(self):
        """Get information about unmet dependencies in the cache state.

        Go through all the broken packages and say which dependencies
        haven't been satisfied.

        @return: A string with dependency information like what you get
            from apt-get.
        """

        broken_packages = self._get_broken_packages()
        if not broken_packages:
            return ""
        all_info = ["The following packages have unmet dependencies:"]
        for package in sorted(broken_packages, key=attrgetter("name")):
            found_dependency_error = False
            # Fetch candidate version from our install list because
            # apt-2.1.5 resets broken packages candidate.
            candidate = next(
                v._cand for v in self._version_installs if v.package == package
            )
            for dep_type in ["PreDepends", "Depends", "Conflicts", "Breaks"]:
                dependencies = candidate.depends_list.get(dep_type, [])
                for dependency in dependencies:
                    if self._is_dependency_satisfied(dependency, dep_type):
                        continue
                    relation_infos = []
                    for dep_relation in dependency:
                        relation_infos.append(
                            self._get_unmet_relation_info(dep_relation),
                        )
                    info = f"  {package.name}: {dep_type}: "
                    or_divider = " or\n" + " " * len(info)
                    all_info.append(info + or_divider.join(relation_infos))
                    found_dependency_error = True
            if not found_dependency_error:
                all_info.append(
                    "  {}: {}".format(
                        package.name,
                        "Unknown dependency error",
                    ),
                )
        return "\n".join(all_info)

    def _set_frontend_noninteractive(self):
        """
        Set the environment to avoid attempts by apt to interact with a user.
        """
        os.environ["DEBIAN_FRONTEND"] = "noninteractive"
        os.environ["APT_LISTCHANGES_FRONTEND"] = "none"
        os.environ["APT_LISTBUGS_FRONTEND"] = "none"

    def _setup_dpkg_for_changes(self):
        """
        Setup environment and apt options for successful package operations.
        """
        self._set_frontend_noninteractive()
        apt_pkg.config.clear("DPkg::options")
        apt_pkg.config.set("DPkg::options::", "--force-confold")

    def _perform_hold_changes(self):
        """
        Perform pending hold operations on packages.
        """
        hold_changes = (
            len(self._version_hold_creations) > 0
            or len(self._version_hold_removals) > 0
        )
        if not hold_changes:
            return None
        not_installed = [
            version
            for version in self._version_hold_creations
            if not self.is_package_installed(version)
        ]
        if not_installed:
            raise TransactionError(
                "Cannot perform the changes, since the following "
                + "packages are not installed: {}".format(
                    ", ".join(
                        [
                            version.package.name
                            for version in sorted(not_installed)
                        ],
                    ),
                ),
            )

        for version in self._version_hold_creations:
            self.set_package_hold(version)

        for version in self._version_hold_removals:
            self.remove_package_hold(version)

        return "Package holds successfully changed."

    def _commit_package_changes(self):
        """
        Commit cached APT operations and give feedback on the results as a
        string.
        """
        # XXX we cannot use io.StringIO() here with Python 2 as there is a
        # string literal written in apt.progress.text.TextProgress._write()
        # which is not recognized as unicode by io.StringIO() with Python 2.
        fetch_output = StringIO()
        # Redirect stdout and stderr to a file. We need to work with the
        # file descriptors, rather than sys.stdout/stderr, since dpkg is
        # run in a subprocess.
        fd, install_output_path = tempfile.mkstemp()
        old_stdout = os.dup(1)
        old_stderr = os.dup(2)
        os.dup2(fd, 1)
        os.dup2(fd, 2)
        install_progress = LandscapeInstallProgress()
        try:
            # Since others (charms) might be installing packages on this system
            # We need to retry a bit in case dpkg is locked in progress
            dpkg_tries = 0
            while dpkg_tries <= self.max_dpkg_retries:
                error = None
                if dpkg_tries > 0:
                    # Yeah, sleeping isn't kosher according to Twisted, but
                    # this code is run in the package-changer, which doesn't
                    # have any concurrency going on.
                    time.sleep(self.dpkg_retry_sleep)
                    logging.warning(
                        "dpkg process might be in use. "
                        "Retrying package changes. "
                        f"{self.max_dpkg_retries - dpkg_tries:d} "
                        "retries remaining.",
                    )
                dpkg_tries += 1
                try:
                    self._cache.commit(
                        fetch_progress=LandscapeAcquireProgress(fetch_output),
                        install_progress=install_progress,
                    )
                    if not install_progress.dpkg_exited:
                        raise SystemError("dpkg didn't exit cleanly.")
                except SystemError as exc:
                    result_text = fetch_output.getvalue() + read_text_file(
                        install_output_path,
                    )
                    error = TransactionError(
                        exc.args[0]
                        + "\n\nPackage operation log:\n"
                        + result_text,
                    )
                    # No need to retry SystemError, since it's most
                    # likely a permanent error.
                    break
                except apt.cache.LockFailedException as exception:
                    result_text = fetch_output.getvalue() + read_text_file(
                        install_output_path,
                    )
                    error = TransactionError(
                        exception.args[0]
                        + "\n\nPackage operation log:\n"
                        + result_text,
                    )
                else:
                    result_text = fetch_output.getvalue() + read_text_file(
                        install_output_path,
                    )
                    break
            if error is not None:
                raise error
        finally:
            # Restore stdout and stderr.
            os.dup2(old_stdout, 1)
            os.dup2(old_stderr, 2)
            os.remove(install_output_path)

        return result_text

    def _preprocess_installs(self, fixer):
        for version in self._version_installs:
            if version == version.package.installed:
                # No point in marking it for installation if the
                # requested version is already installed.
                continue
            # Set the candidate version, so that the version we want to
            # install actually is the one getting installed.
            version.package.candidate = version

            # Flag the package as manual if it's a new install, otherwise
            # preserve the auto flag. This should preserve explicitly
            # installed packages from auto-removal, while allowing upgrades
            # of auto-removable packages.
            is_manual = (
                not version.package.installed
                or not version.package.is_auto_installed
            )

            # Set auto_fix=False to avoid removing the package we asked to
            # install when we need to resolve dependencies.
            version.package.mark_install(auto_fix=False, from_user=is_manual)
            self._package_installs.add(version.package)
            fixer.clear(version.package._pkg)
            fixer.protect(version.package._pkg)

    def _preprocess_removes(self, fixer):
        held_package_names = set()

        package_installs = {
            version.package for version in self._version_installs
        }

        package_upgrades = {
            version.package
            for version in self._version_removals
            if version.package in package_installs
        }

        for version in self._version_removals:
            if self._is_package_held(version.package):
                held_package_names.add(version.package.name)
            if version.package in package_upgrades:
                # The server requests the old version to be removed for
                # upgrades, since Smart worked that way. For Apt we have
                # to take care not to mark upgraded packages for  removal.
                continue
            version.package.mark_delete(auto_fix=False)
            # Configure the resolver in the same way
            # mark_delete(auto_fix=True) would have done.
            fixer.clear(version.package._pkg)
            fixer.protect(version.package._pkg)
            fixer.remove(version.package._pkg)
            try:
                # obsoleted in python-apt 1.9
                fixer.install_protect()
            except AttributeError:
                pass

        if held_package_names:
            raise TransactionError(
                "Can't perform the changes, since the following packages "
                "are held: {}".format(", ".join(sorted(held_package_names))),
            )

    def _preprocess_global_upgrade(self):
        if self._global_upgrade:
            self._cache.upgrade(dist_upgrade=True)

    def _resolve_broken_packages(self, fixer, already_broken_packages):
        """
        Attempt to automatically resolve problems with broken packages.
        """
        now_broken_packages = self._get_broken_packages()
        if now_broken_packages != already_broken_packages:
            try:
                fixer.resolve(True)
            except SystemError as error:
                raise TransactionError(
                    error.args[0] + "\n" + self._get_unmet_dependency_info(),
                )
            else:
                now_broken_packages = self._get_broken_packages()
                if now_broken_packages != already_broken_packages:
                    raise TransactionError(self._get_unmet_dependency_info())

    def _preprocess_package_changes(self):
        version_changes = self._version_installs[:]
        version_changes.extend(self._version_removals)
        if not version_changes and not self._global_upgrade:
            return []
        already_broken_packages = self._get_broken_packages()
        fixer = apt_pkg.ProblemResolver(self._cache._depcache)
        self._preprocess_installs(fixer)
        self._preprocess_global_upgrade()
        self._preprocess_removes(fixer)
        self._resolve_broken_packages(fixer, already_broken_packages)
        return version_changes

    def _perform_package_changes(self):
        """
        Perform pending install/remove/upgrade operations.
        """
        version_changes = self._preprocess_package_changes()
        if not self._check_changes(version_changes):
            return None
        return self._commit_package_changes()

    def perform_changes(self):
        """
        Perform the pending package operations.
        """
        self._setup_dpkg_for_changes()
        hold_result_text = self._perform_hold_changes()
        package_result_text = self._perform_package_changes()
        results = []
        if package_result_text is not None:
            results.append(package_result_text)
        if hold_result_text is not None:
            results.append(hold_result_text)
        if len(results) > 0:
            return " ".join(results)

    def reset_marks(self):
        """Clear the pending package operations."""
        del self._version_installs[:]
        self._package_installs.clear()
        del self._version_removals[:]
        del self._version_hold_removals[:]
        del self._version_hold_creations[:]
        self._global_upgrade = False
        self._cache.clear()

    def mark_install(self, version):
        """Mark the package for installation."""
        self._version_installs.append(version)

    def mark_global_upgrade(self):
        """Upgrade all installed packages."""
        self._global_upgrade = True

    def mark_remove(self, version):
        """Mark the package for removal."""
        self._version_removals.append(version)

    def mark_hold(self, version):
        """Mark the package to be held."""
        self._version_hold_creations.append(version)

    def mark_remove_hold(self, version):
        """Mark the package to have its hold removed."""
        self._version_hold_removals.append(version)
