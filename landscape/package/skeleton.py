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
    name, version, relation = relation
    relation_string = name
    if relation:
        relation_string += " %(relation)s %(version)s" % {
            "relation": relation,
            "version": version}
    return relation_string


def build_skeleton_apt(package, with_info=False, with_unicode=False):
    skeleton = PackageSkeleton(
        DEB_PACKAGE, package.name, package.candidate.version)
    relations = set()
    provides = apt_pkg.parse_depends(
        package.candidate.record.get("Provides", ""))
    if provides:
        for provide in provides:
            name = provide[0][0]
            relations.add((DEB_PROVIDES, name))
    relations.add((
        DEB_NAME_PROVIDES,
        "%s = %s" % (package.name, package.candidate.version)))
    pre_depends = apt_pkg.parse_depends(
        package.candidate.record.get("Pre-Depends", ""))
    for depend in pre_depends:
        depend_strings = [relation_to_string(relation) for relation in depend]
        skeleton_relation = DEB_REQUIRES
        if len(depend_strings) > 1:
            skeleton_relation = DEB_OR_REQUIRES
        depend_string = " | ".join(depend_strings)
        relations.add((skeleton_relation, depend_string))
    depends = apt_pkg.parse_depends(
        package.candidate.record.get("Depends", ""))
    for depend in depends:
        depend_strings = [relation_to_string(relation) for relation in depend]
        skeleton_relation = DEB_REQUIRES
        if len(depend_strings) > 1:
            skeleton_relation = DEB_OR_REQUIRES
        depend_string = " | ".join(depend_strings)
        relations.add((skeleton_relation, depend_string))

    relations.add((
        DEB_UPGRADES, "%s < %s" % (package.name, package.candidate.version)))

    conflicts = apt_pkg.parse_depends(
        package.candidate.record.get("Conflicts", ""))
    if conflicts:
        for conflict in conflicts:
            name, version, relation = conflict[0]
            conflict_string = name
            if relation:
                conflict_string += " %(relation)s %(version)s" % {
                    "relation": relation,
                    "version": version}
            relations.add((DEB_CONFLICTS, conflict_string))
    skeleton.relations = sorted(relations)

    if with_info:
        skeleton.section = package.candidate.section
        skeleton.summary = package.candidate.summary
        skeleton.description = package.candidate.description
        skeleton.size = package.candidate.size
        if package.candidate.installed_size > 0:
            skeleton.installed_size = package.candidate.installed_size
    return skeleton
