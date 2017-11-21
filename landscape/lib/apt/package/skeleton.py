from landscape.lib.hashlib import sha1

import apt_pkg

from twisted.python.compat import unicode, _PY3


PACKAGE   = 1 << 0
PROVIDES  = 1 << 1
REQUIRES  = 1 << 2
UPGRADES  = 1 << 3
CONFLICTS = 1 << 4

DEB_PACKAGE       = 1 << 16 | PACKAGE
DEB_PROVIDES      = 2 << 16 | PROVIDES
DEB_NAME_PROVIDES = 3 << 16 | PROVIDES
DEB_REQUIRES      = 4 << 16 | REQUIRES
DEB_OR_REQUIRES   = 5 << 16 | REQUIRES
DEB_UPGRADES      = 6 << 16 | UPGRADES
DEB_CONFLICTS     = 7 << 16 | CONFLICTS


class PackageTypeError(Exception):
    """Raised when an unsupported package type is passed to build_skeleton."""


class PackageSkeleton(object):

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
        package_info = ("[%d %s %s]" % (self.type, self.name, self.version)
                        ).encode("ascii")
        digest = sha1(package_info)
        self.relations.sort()
        for pair in self.relations:
            digest.update(("[%d %s]" % (pair[0], pair[1])
                           ).encode("ascii"))
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
        relation_string += " %s %s" % (relation_type, version)
    return relation_string


def parse_record_field(record, record_field, relation_type,
                       or_relation_type=None):
    """Parse an apt C{Record} field and return skeleton relations

    @param record: An C{apt.package.Record} instance with package information.
    @param record_field: The name of the record field to parse.
    @param relation_type: The deb relation that can be passed to
        C{skeleton.add_relation()}
    @param or_relation_type: The deb relation that should be used if
        there is more than one value in a relation.
    """
    relations = set()
    values = apt_pkg.parse_depends(record.get(record_field, ""))
    for value in values:
        value_strings = [relation_to_string(relation) for relation in value]
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
    relations.update(parse_record_field(
        version.record, "Provides", DEB_PROVIDES))
    relations.add((
        DEB_NAME_PROVIDES,
        "%s = %s" % (version.package.name, version.version)))
    relations.update(parse_record_field(
        version.record, "Pre-Depends", DEB_REQUIRES, DEB_OR_REQUIRES))
    relations.update(parse_record_field(
        version.record, "Depends", DEB_REQUIRES, DEB_OR_REQUIRES))

    relations.add((
        DEB_UPGRADES, "%s < %s" % (version.package.name, version.version)))

    relations.update(parse_record_field(
        version.record, "Conflicts", DEB_CONFLICTS))
    relations.update(parse_record_field(
        version.record, "Breaks", DEB_CONFLICTS))
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
