#!/usr/bin/python


NAME = "landscape-lib",
DESCRIPTION = "Common code used by Landscape applications"
PACKAGES = [
        "landscape.lib",
        "landscape.lib.apt",
        "landscape.lib.apt.package",
        "landscape.message_schemas",
        ]
MODULES = [
        "landscape.__init__",
        "landscape.constants",
        ]
SCRIPTS = []

# Dependencies

DEB_REQUIRES = [
        "lsb-base",
        "lsb-release",
        "lshw",
        ]
REQUIRES = [
        "twisted",
        "configobj",
        #apt (from python3-apt)
        ]


if __name__ == "__main__":
    from setup import setup_landscape
    setup_landscape(
        name=NAME,
        description=DESCRIPTION,
        packages=PACKAGES,
        modules=MODULES,
        scripts=SCRIPTS,
        )
