import apt

from landscape.lib.compat import _PY3
from landscape.lib.compat import unicode
from landscape.lib.hashlib import sha1


PACKAGE = 1 << 0
PROVIDES = 1 << 1
REQUIRES = 1 << 2
UPGRADES = 1 << 3
CONFLICTS = 1 << 4

DEB_PACKAGE = 1 << 16 | PACKAGE
DEB_PROVIDES = 2 << 16 | PROVIDES
DEB_NAME_PROVIDES = 3 << 16 | PROVIDES
DEB_REQUIRES = 4 << 16 | REQUIRES
DEB_OR_REQUIRES = 5 << 16 | REQUIRES
DEB_UPGRADES = 6 << 16 | UPGRADES
DEB_CONFLICTS = 7 << 16 | CONFLICTS


class PackageTypeError(Exception):
    """Raised when an unsupported package type is passed to build_skeleton."""


class PackageSkeleton:

    section = None
    summary = None
    description = None
    size = None
    installed_size = None
    _hash = None

    def __init__(self, type, name, version):
        self.type = type
        self.name = name
        self.version = version
        self.relations = []

    def add_relation(self, type, info):
        self.relations.append((type, info))

    def get_hash(self):
        """Calculate the package hash.

        If C{set_hash} has been used, that hash will be returned and the
        hash won't be the calculated value.
        """
        if self._hash is not None:
            return self._hash
        # We use ascii here as encoding  for backwards compatibility as it was
        # default encoding for conversion from unicode to bytes in Python 2.7.
        package_info = (f"[{self.type:d} {self.name} {self.version}]").encode(
            "ascii",
        )
        digest = sha1(package_info)
        self.relations.sort()
        for pair in self.relations:
            digest.update((f"[{pair[0]:d} {pair[1]}]").encode("ascii"))
        return digest.digest()

    def set_hash(self, package_hash):
        """Set the hash to an explicit value.

        This should be used when the hash is previously known and can't
        be calculated from the relations anymore.

        The only use case for this is package resurrection. We're
        planning on getting rid of package resurrection, and this code
        can be removed when that is done.
        """
        self._hash = package_hash


def relation_to_string(relation_tuple):
    """Convert an apt relation to a string representation.

    @param relation_tuple: A tuple, (name, version, relation). version
        and relation can be the empty string, if the relation is on a
        name only.

    Returns something like "name > 1.0"
    """
    name, version, relation_type = relation_tuple
    relation_string = name
    if relation_type:
        relation_string += f" {relation_type} {version}"
    return relation_string


def parse_record_dependencies(
    dependencies,
    relation_type,
    or_relation_type=None,
):
    """Parse an apt C{Dependency} list and return skeleton relations

    @param dependencies: list of dependencies returned by get_dependencies()
        this function also accepts the special case for version.provides which
        is a list of string
    @param relation_type: The deb relation that can be passed to
        C{skeleton.add_relation()}
    @param or_relation_type: The deb relation that should be used if
        there is more than one value in a relation.
    """

    # Prepare list of dependencies
    relations = set()
    for dependency in dependencies:

        # Process dependency
        depend = []
        if isinstance(dependency, apt.package.Dependency):
            for basedependency in dependency:
                depend.append(
                    (
                        basedependency.name,
                        basedependency.version,
                        basedependency.relation,
                    ),
                )
        else:
            depend.append((dependency, "", ""))

        # Process relations
        value_strings = [relation_to_string(relation) for relation in depend]
        value_relation_type = relation_type
        if len(value_strings) > 1:
            value_relation_type = or_relation_type
        relation_string = " | ".join(value_strings)
        relations.add((value_relation_type, relation_string))

    return relations


def build_skeleton_apt(version, with_info=False, with_unicode=False):
    """Build a package skeleton from an apt package.

    @param version: An instance of C{apt.package.Version}
    @param with_info: Whether to extract extra information about the
        package, like description, summary, size.
    @param with_unicode: Whether the C{name} and C{version} of the
        skeleton should be unicode strings.
    """
    name, version_string = version.package.name, version.version
    if with_unicode:
        name, version_string = unicode(name), unicode(version_string)
    skeleton = PackageSkeleton(DEB_PACKAGE, name, version_string)
    relations = set()

    relations.update(parse_record_dependencies(version.provides, DEB_PROVIDES))
    relations.add(
        (
            DEB_NAME_PROVIDES,
            f"{version.package.name} = {version.version}",
        ),
    )
    relations.update(
        parse_record_dependencies(
            version.get_dependencies("PreDepends"),
            DEB_REQUIRES,
            DEB_OR_REQUIRES,
        ),
    )
    relations.update(
        parse_record_dependencies(
            version.get_dependencies("Depends"),
            DEB_REQUIRES,
            DEB_OR_REQUIRES,
        ),
    )

    relations.add(
        (DEB_UPGRADES, f"{version.package.name} < {version.version}"),
    )

    relations.update(
        parse_record_dependencies(
            version.get_dependencies("Conflicts"),
            DEB_CONFLICTS,
        ),
    )
    relations.update(
        parse_record_dependencies(
            version.get_dependencies("Breaks"),
            DEB_CONFLICTS,
        ),
    )
    skeleton.relations = sorted(relations)

    if with_info:
        skeleton.section = version.section
        skeleton.summary = version.summary
        skeleton.description = version.description
        skeleton.size = version.size
        if version.installed_size > 0:
            skeleton.installed_size = version.installed_size
        if with_unicode and not _PY3:
            skeleton.section = skeleton.section.decode("utf-8")
            skeleton.summary = skeleton.summary.decode("utf-8")
            # Avoid double-decoding package descriptions in build_skeleton_apt,
            # which causes an error with newer python-apt (Xenial onwards)
            if not isinstance(skeleton.description, unicode):
                skeleton.description = skeleton.description.decode("utf-8")
    return skeleton
