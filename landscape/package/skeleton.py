from landscape.lib.hashlib import sha1

import apt_pkg


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

    def __init__(self, type, name, version):
        self.type = type
        self.name = name
        self.version = version
        self.relations = []

    def add_relation(self, type, info):
        self.relations.append((type, info))

    def get_hash(self):
        digest = sha1("[%d %s %s]" % (self.type, self.name, self.version))
        self.relations.sort()
        for pair in self.relations:
            digest.update("[%d %s]" % pair)
        return digest.digest()


def build_skeleton(pkg, with_info=False, with_unicode=False):
    if not build_skeleton.inited:
        build_skeleton.inited = True
        global DebPackage, DebNameProvides, DebOrDepends

        # Importing from backends depends on smart.init().
        from smart.backends.deb.base import (
            DebPackage, DebNameProvides, DebOrDepends)

    if not isinstance(pkg, DebPackage):
        raise PackageTypeError()

    if with_unicode:
        skeleton = PackageSkeleton(DEB_PACKAGE, unicode(pkg.name),
                                   unicode(pkg.version))
    else:
        skeleton = PackageSkeleton(DEB_PACKAGE, pkg.name, pkg.version)
    relations = set()
    for relation in pkg.provides:
        if isinstance(relation, DebNameProvides):
            relations.add((DEB_NAME_PROVIDES, str(relation)))
        else:
            relations.add((DEB_PROVIDES, str(relation)))
    for relation in pkg.requires:
        if isinstance(relation, DebOrDepends):
            relations.add((DEB_OR_REQUIRES, str(relation)))
        else:
            relations.add((DEB_REQUIRES, str(relation)))
    for relation in pkg.upgrades:
        relations.add((DEB_UPGRADES, str(relation)))
    for relation in pkg.conflicts:
        relations.add((DEB_CONFLICTS, str(relation)))

    skeleton.relations = sorted(relations)

    if with_info:
        info = pkg.loaders.keys()[0].getInfo(pkg)
        skeleton.section = info.getGroup()
        skeleton.summary = info.getSummary()
        skeleton.description = info.getDescription()
        skeleton.size = sum(info.getSize(url) for url in info.getURLs())
        skeleton.installed_size = info.getInstalledSize()

    return skeleton

build_skeleton.inited = False


def relation_to_string(relation):
    """Convert an apt relation to a string representation.

    @param relation: A tuple, (name, version, relation). version and
        relation can be the empty string, if the relation is on a name only.

    Returns something like "name > 1.0"
    """
    name, version, relation = relation
    relation_string = name
    if relation:
        relation_string += " %(relation)s %(version)s" % {
            "relation": relation,
            "version": version}
    return relation_string


def parse_record_field(record, record_field, skeleton_relation,
                       or_skeleton_relation=None):
    """Parse an apt C{Record} field and return skeleton relations

    @param record: An C{apt.package.Record} instance with package information.
    @param record_field: The name of the record field to parse.
    @param skeleton_relation: The deb relation that can be passed to
        C{skeleton.add_relation()}
    @param skeleton_or_relation: The deb relation that should be used if
        there are more than one value in a relation.
    """
    relations = set()
    values = apt_pkg.parse_depends(record.get(record_field, ""))
    for value in values:
        value_strings = [relation_to_string(relation) for relation in value]
        if len(value_strings) > 1:
            skeleton_relation = or_skeleton_relation
        relation_string = " | ".join(value_strings)
        relations.add((skeleton_relation, relation_string))
    return relations


def build_skeleton_apt(package, with_info=False, with_unicode=False):
    """Build a package skeleton from an apt package.

    @param package: An instance of C{apt.package.Package}
    @param with_info: Whether to extract extra information about the
        package, like description, summary, size.
    @param with_unicode: Whether the C{name} and C{version} of the
        skeleton should be unicode strings.
    """
    candidate = package.candidate
    name, version = package.name, candidate.version
    if with_unicode:
        name, version = unicode(name), unicode(version)
    skeleton = PackageSkeleton(DEB_PACKAGE, name, version)
    relations = set()
    relations.update(parse_record_field(
        candidate.record, "Provides", DEB_PROVIDES))
    relations.add((
        DEB_NAME_PROVIDES,
        "%s = %s" % (package.name, candidate.version)))
    relations.update(parse_record_field(
        candidate.record, "Pre-Depends", DEB_REQUIRES, DEB_OR_REQUIRES))
    relations.update(parse_record_field(
        candidate.record, "Depends", DEB_REQUIRES, DEB_OR_REQUIRES))

    relations.add((
        DEB_UPGRADES, "%s < %s" % (package.name, candidate.version)))

    relations.update(parse_record_field(
        candidate.record, "Conflicts", DEB_CONFLICTS))
    skeleton.relations = sorted(relations)

    if with_info:
        skeleton.section = candidate.section
        skeleton.summary = candidate.summary
        skeleton.description = candidate.description
        skeleton.size = candidate.size
        if candidate.installed_size > 0:
            skeleton.installed_size = candidate.installed_size
    return skeleton
