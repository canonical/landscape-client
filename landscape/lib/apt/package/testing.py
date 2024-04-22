import os
import time

import apt_inst
import apt_pkg

from landscape.lib import base64
from landscape.lib.apt.package.facade import AptFacade
from landscape.lib.fs import append_binary_file
from landscape.lib.fs import create_binary_file


class AptFacadeHelper:
    """Helper that sets up an AptFacade with a tempdir as its root."""

    def set_up(self, test_case):
        test_case.apt_root = test_case.makeDir()
        os.makedirs(os.path.join(test_case.apt_root, "etc/apt/preferences.d"))
        self.dpkg_status = os.path.join(
            test_case.apt_root,
            "var",
            "lib",
            "dpkg",
            "status",
        )
        test_case.Facade = AptFacade
        test_case.facade = AptFacade(root=test_case.apt_root)
        test_case.facade.refetch_package_index = True
        # Since some tests intentionally induces errors, there's no need for
        # the facade to wait to see if they go away.
        test_case.facade.dpkg_retry_sleep = 0
        test_case._add_system_package = self._add_system_package
        test_case._install_deb_file = self._install_deb_file
        test_case._add_package_to_deb_dir = self._add_package_to_deb_dir
        test_case._touch_packages_file = self._touch_packages_file
        test_case._hash_packages_by_name = self._hash_packages_by_name

    def _add_package(
        self,
        packages_file,
        name,
        architecture="all",
        version="1.0",
        description="description",
        control_fields=None,
    ):
        if control_fields is None:
            control_fields = {}
        package_stanza = {
            "Package": name,
            "Priority": "optional",
            "Section": "misc",
            "Installed-Size": "1234",
            "Maintainer": "Someone",
            "Architecture": architecture,
            "Source": "source",
            "Version": version,
            "Description": "short description\n " + description,
        }
        package_stanza.update(control_fields)

        try:
            with open(packages_file, "rb") as src:
                packages = src.read().split(b"\n\n")
        except OSError:
            packages = []
        if b"" in packages:
            packages.remove(b"")

        new_package = "\n".join(
            [
                "{}: {}".format(key, package_stanza[key])
                for key in apt_pkg.REWRITE_PACKAGE_ORDER
                if key in package_stanza
            ],
        ).encode("utf-8")
        packages.append(new_package)

        with open(packages_file, "wb", 0) as dest:
            # keep Pacakges sorted to avoid odd behaviours like changing IDs.
            dest.write(b"\n\n".join(sorted(packages)))
            dest.write(b"\n")

    def _add_system_package(
        self,
        name,
        architecture="all",
        version="1.0",
        control_fields=None,
    ):
        """Add a package to the dpkg status file."""
        system_control_fields = {"Status": "install ok installed"}
        if control_fields is not None:
            system_control_fields.update(control_fields)
        self._add_package(
            self.dpkg_status,
            name,
            architecture=architecture,
            version=version,
            control_fields=system_control_fields,
        )

    def _install_deb_file(self, path):
        """Fake the the given deb file is installed in the system."""
        deb_file = open(path)
        deb = apt_inst.DebFile(deb_file)
        control = deb.control.extractdata("control")
        deb_file.close()
        lines = control.splitlines()
        lines.insert(1, b"Status: install ok installed")
        status = b"\n".join(lines)
        append_binary_file(self.dpkg_status, status + b"\n\n")

    def _add_package_to_deb_dir(
        self,
        path,
        name,
        architecture="all",
        version="1.0",
        description="description",
        control_fields=None,
    ):
        """Add fake package information to a directory.

        There will only be basic information about the package
        available, so that get_packages() have something to return.
        There won't be an actual package in the dir.
        """
        if control_fields is None:
            control_fields = {}
        self._add_package(
            os.path.join(path, "Packages"),
            name,
            architecture=architecture,
            version=version,
            description=description,
            control_fields=control_fields,
        )

    def _touch_packages_file(self, deb_dir):
        """Make sure the Packages file gets a newer mtime value.

        If we rely on simply writing to the file to update the mtime, we
        might end up with the same as before, since the resolution is
        seconds, which causes apt to not reload the file.
        """
        packages_path = os.path.join(deb_dir, "Packages")
        mtime = int(time.time() + 1)
        os.utime(packages_path, (mtime, mtime))

    def _hash_packages_by_name(self, facade, store, package_name):
        """
        Ensure the named L{Package} is correctly recorded in the store so that
        we can really test the functions of the facade that depend on it.
        """
        hash_ids = {}
        for version in facade.get_packages_by_name(package_name):
            skeleton = facade.get_package_skeleton(version, with_info=False)
            hash = skeleton.get_hash()
            facade._pkg2hash[(version.package, version)] = hash
            hash_ids[hash] = version.package.id
        store.set_hash_ids(hash_ids)


class SimpleRepositoryHelper:
    """Helper for adding a simple repository to the facade.

    This helper requires that C{test_case.facade} has already been set
    up.
    """

    def set_up(self, test_case):
        test_case.repository_dir = test_case.makeDir()
        create_simple_repository(test_case.repository_dir)
        test_case.facade.add_channel_deb_dir(test_case.repository_dir)


PKGNAME1 = "name1_version1-release1_all.deb"
PKGNAME2 = "name2_version2-release2_all.deb"
PKGNAME3 = "name3_version3-release3_all.deb"
PKGNAME4 = "name3_version3-release4_all.deb"
PKGNAME_MINIMAL = "minimal_1.0_all.deb"
PKGNAME_SIMPLE_RELATIONS = "simple-relations_1.0_all.deb"
PKGNAME_VERSION_RELATIONS = "version-relations_1.0_all.deb"
PKGNAME_MULTIPLE_RELATIONS = "multiple-relations_1.0_all.deb"
PKGNAME_OR_RELATIONS = "or-relations_1.0_all.deb"
PKGNAME_BROKEN_DESCRIPTION = "brokendescription_1.0_all.deb"

PKGDEB1 = (
    b"ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTE2NjExNDQ5MyAgMCAgICAgMCAgICAgMT"
    b"AwNjQ0ICA0ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDExNjYxMTQ0OTMg"
    b"IDAgICAgIDAgICAgIDEwMDY0NCAgNDUyICAgICAgIGAKH4sIAAAAAAAAA+3UQW+bMB"
    b"QHcM58Ch+7QwCbEJpomzat0rTDpmiRenfNC7EGNnuGSOmnnwMlyVK1O6VT1feTkJ+e"
    b"/wRh40RxcHGJl2dZP3rnY1/zJJsmIs9Fvs/5UQQsC15A51qJjAVobftc7l/zr1QU10"
    b"XmutpdeP9n0+mT+8+5+Hv/fSOdBiyh/b84MYM1n2fz7G4t0+u5SvMkhbTgs3wu+CwB"
    b"xjqHsdtIhLiwKjayBh6rjTQlVLaMbuBOSxOV92FAXuX5V9a0aKv/eP5zkZyf/1TQ+X"
    b"8RS6l+yRIWrD/Y4S2g09Ys2HYo+AShAun81ApU2099Rds1PFyitqjb3YLZZj8hq/Az"
    b"qo1ufa5D/4uyqnwIJjfQgCncgjUICL87jdA/jF19OGmND3wXHvLn4UfJn6BsXY/hsT"
    b"7Jj63jLauuLMG1/gb3UB3iY+MY/mLNutJqn1ZjeYgfOsf8Eu1WF9C/6lANq/rN+I+s"
    b"qqCYrPS9XxlxHX6X2rT+AvQLuv8Gt5b90FDDDpC9L4fOJ/PQiQy0H/3COIW6GXZh1d"
    b"W1xB0P2Umb078wIYQQQgghhBBCCCGEEEIIIYS8UX8AYydx2gAoAABkYXRhLnRhci5n"
    b"eiAgICAgMTE2NjExNDQ5MyAgMCAgICAgMCAgICAgMTAwNjQ0ICAzOTQgICAgICAgYA"
    b"ofiwgAAAAAAAAD09NnoDkwAAJzU1MwDQToNJhtaGBqYmBkbm5kDlIHpI0YFEwZ6ABK"
    b"i0sSixQUGIry80vwqSMkP0SBnn5pcZH+YIp/EwYDIMd4NP7pGP/FGYlFqfqDJ/4NzY"
    b"xNRuOf3vGfkp+sPzji38jEwHA0/gci/vMSc1MN9Qc6/o2B7NH4H7j4T85IzEtPzclP"
    b"13NJTcpMzNNLr6Iw/s1MTHDGv5GxOSz+zUxNjYDxbw7kMSgYjMY/zYF8NwdHVm2jKx"
    b"Mzepwz6J7y5jpkIOH6sDKssF1rmUqYzBX2piZj9zyFad5RHv8dLoXsqua2spF3v+PQ"
    b"ffXIlN8aYepsu3x2u0202VX+QFC10st6vvMfDdacgtdzKtpe5G5tuFYx5elcpXm27O"
    b"d8LH7Oj3mqP7VgD8P6dTmJ33dsPnpuBnPO3SvLDNlu6ay9It6yZon0BIZRMApGwSgY"
    b"BaNgFIyCUTAKRsEoGAWjYBSMglEwCkbBKBgFo2AUjIJRMApGAUkAADhX8vgAKAAA "
)

PKGDEB2 = (
    b"ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTE2NjExNDUyMiAgMCAgICAgMCAgICAgMT"
    b"AwNjQ0ICA0ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDExNjYxMTQ1MjIg"
    b"IDAgICAgIDAgICAgIDEwMDY0NCAgNDUyICAgICAgIGAKH4sIAAAAAAAAA+3UTY/TMB"
    b"AG4JzzK3yEQ/Phxk1aAQKxEuIAqrYSd+NMU4vEDuOkUvfX4yabthQBpy5aMY9UZTR+"
    b"06ieuFEc3Fzi5UIMV+/6OtRpIrKE5/l8zn0/z9MsYCJ4Ar3rJDIWoLXdn3J/W3+mor"
    b"gphesbd+P5L7Lst/NPU/7z/H2DLwKW0PxvrixSlYkiAVGIxZJnaSHFdilUDplabnnG"
    b"WO8wdjuJEJdWxUY2wGO1k6aC2lbRHXzV0kTVQxiQZ3n+lTUd2vofnv+cJ9fnf57S+X"
    b"8Sa6m+yQpWbDjY4RdAp61Zsf1Y8BlCDdL5pQ2oblj6gLZvebhGbVF3hxWz7XFB1uE7"
    b"VDvd+VyP/htlXfsQzO6gBVO6FWsREL73GmF4GHvx+qI1PfBleMpfh39J3oOyTTOFp/"
    b"oiP7XOt2z6qgLX+RvcY3WKT41z+L0121qrY1pN5Sl+6pzza7R7XcLwU8dq3NWPxr9k"
    b"dQ3lbKMf/M7wIvwkten8B9Bv6PEd3Fv2WUMDB0D2qho7b81jJzLQvfEb4xTqdpzCpm"
    b"8aiQcesos2p39hQgghhBBCCCGEEEIIIYQQQgj5T/0AyM2cyQAoAABkYXRhLnRhci5n"
    b"eiAgICAgMTE2NjExNDUyMiAgMCAgICAgMCAgICAgMTAwNjQ0ICAzOTMgICAgICAgYA"
    b"ofiwgAAAAAAAAD09NnoDkwAAJzU1MwDQToNJhtaGBqYmBkbm5sbAgUNzc3NGZQMGWg"
    b"AygtLkksUlBgKMrPL8GnjpD8EAV6+qXFRfqDLP6BHCOT0finX/wXZyQWpeoPnvg3ND"
    b"MyG41/esd/Sn6y/uCIfyNj89Hyf0DiPy8xN9VIf6Dj39jY3HQ0/gcu/pMzEvPSU3Py"
    b"0/VcUpMyE/P00qsojH8zExOc8Q/M7Yj4Bxb8BobmBsDkomAwGv80B/LdHBzX6hpdmZ"
    b"jR45xB99RGrkMGEq4Pbf0L3UWDL4XIRIk6Hjx7Urzj6SSxS/YTzKbu28sqe/64oPmF"
    b"JGPj3lqR1cLMdz12u04rLHp/gM2y0mv3HOc/GqxvCl7PqWh7kbux6VrFk69zlefZsu"
    b"v5WPycH/NUv7VgF8N6vfeBcgXp3NlnBFNDw5eZsd1as/aK+JzyvZ0TGEbBKBgFo2AU"
    b"jIJRMApGwSgYBaNgFIyCUTAKRsEoGAWjYBSMglEwCkbBKBgFJAEAu4OlKQAoAAAK"
)

PKGDEB3 = (
    b"ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTE2OTE0ODIwMyAgMCAgICAgMCAgICAgMT"
    b"AwNjQ0ICA0ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDExNjkxNDgyMDMg"
    b"IDAgICAgIDAgICAgIDEwMDY0NCAgNDUxICAgICAgIGAKH4sIAAAAAAAAA+3UwY7TMB"
    b"AG4JzzFD7CoUkax7iqYAViJcQBVFGJu3GmqbWJHcZJpe7T4yabtnS1cOqiFfNJVUbj"
    b"P43qiZuk0dVlgRRiuAaX16GeZ0JwWRSF4KEvZc4jJqJn0PtOIWMROtf9Kfe39RcqSZ"
    b"tS+L7xV57/m6J4cv7zef77/EODi4hlNP+r4yIrc1mUUs43C1VmhcxLEAKkFouCbzRj"
    b"vcfUbxVCWjqdWtUAT/VW2QpqVyW38MMom1T3cURe5PnXznbo6n94/mWeXZ5/ntP5fx"
    b"Yrpe9UBUs2HOz4O6A3zi7Zbiz4DKEG5cPSGnQ3LH1C17c8XqFxaLr9krn2sKDq+APq"
    b"relCrsfwjaquQwhmt9CCLf2StQgIP3uDMDyMvXp31poe+Do+5i/Dj5LfQLummcJTfZ"
    b"afWqdb1n1Vge/CDf6hOsanxin80dlNbfQhrafyGD92TvkVup0pYfipYzXu6mcbXrK6"
    b"hnK2NvdhZ/JF/EUZ24UPYNjQwzu4c+yrgQb2gOxtNXbe24dOYqG7CRvjNZp2nMK6bx"
    b"qFex6zszanf2FCCCGEEEIIIYQQQgghhBBCCPlP/QK+dA1dACgAAApkYXRhLnRhci5n"
    b"eiAgICAgMTE2OTE0ODIwMyAgMCAgICAgMCAgICAgMTAwNjQ0ICAzOTkgICAgICAgYA"
    b"ofiwgAAAAAAAAD09NnoDkwAAJzU1MwDQToNJhtaGBqamxuYmJiagQUNzc3MmJQMGWg"
    b"AygtLkksUlBgKMrPL8GnjpD8EAV6+qXFRfqDKf4NGQyAHOPR+Kdj/BdnJBal6g+e+D"
    b"c0MzYZjX96x39KfrL+4Ih/IxMDw9H4H4j4z0vMTTXWH8j4B9b/hsYmBqaj8T9w8Z+c"
    b"kZiXnpqTn67nkpqUmZinl15FYfybmZjgjH8jY3NE/JuYAePfHKieQcFgNP5pDuS7OT"
    b"jUTq53ZWJGj3MG3VPeXIcMJFwfVoYVtmstW+Imc4W9qcnYPU9hmneUx3+HSyG7qrmt"
    b"bOTd7zh0Xz0y5bdGmDrbLp/dbhNtdpU/EFSt9LKe7/xHgzWn4PWcirYXuVsbrlVMeT"
    b"pXaZ4t+zkfi5/zY57qTy3Yw7B+XU7g+8L07rmG7Fe2bVxmyHZLZ+0V8Sl2Xj8mMIyC"
    b"UTAKRsEoGAWjYBSMglEwCkbBKBgFo2AUjIJRMApGwSgYBaNgFIyCUTAKSAIAY/FOKA"
    b"AoAAAK"
)

PKGDEB4 = (
    b"ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTI3NjUxMTU3OC41MCAgICAgMCAgICAgNj"
    b"Q0ICAgICA0\nICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEyNzY1MTE1Nz"
    b"guNTAgICAgIDAgICAgIDY0\nNCAgICAgMjk1ICAgICAgIGAKH4sIAFoFFkwC/+3TwU"
    b"6EMBAGYM48RV9goS0dqnszMSbeTEy8F6iE\nCJS04MGnt2GzBzHqiVWT/7u0yVCm8G"
    b"eyPNkdjzTRukbbdd0LoTgpLqmQCRdCckoYJRewhNn4eBXv\n3Pzdcz/Vtx/3T2R57c"
    b"bZu37n/EulvsxfqnKTvyyFTBhH/rt7MPWLae2RjWawIn2yPnRuPLLX00Zk\n4uBtb0"
    b"2Ixfsx/qu+t83hsXuLRwRPb22ofTfN65kbFsww9ZYtU+tNY9l0ennK7pxnsw1zN7bn"
    b"YsjS\nD72LT72Lc2eVJrDb/A8NhWUIvzj/nMR2/kkKzP8lNERFJZWOGWiqiF89ayVt"
    b"qbWhSlfimrEsD26w\nGEEAAAAAAAAAAAAAAAAAAIC/6x1piYqhACgAAApkYXRhLnRh"
    b"ci5neiAgICAgMTI3NjUxMTU3OC41\nMCAgICAgMCAgICAgNjQ0ICAgICAxNDUgICAg"
    b"ICAgYAofiwgAWgUWTAL/7dFBCsMgEEDRWfcUniCZ\nsU57kJ5ASJdFSOz9K9kULLQr"
    b"C4H/NiPqQvnTLMNpc3XfZ9PPfW2W1JOae9s3i5okuPzBc6t5bU9Z\nS6nf7v067z93"
    b"ENO8lcd9fP/LZ/d3f4td/6h+lqD0H+7W6ocl13wSAAAAAAAAAAAAAAAAAAfzAqr5\n"
    b"GFYAKAAACg==\n"
)

PKGDEB_MINIMAL = (
    b"ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTMxNzg5MDQ3OSAgMCAgICAgMCAgICAgMTAwNj"
    b"Q0ICA0 ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEzMTc4OTA0NzkgIDAgICA"
    b"gIDAgICAgIDEw MDY0NCAgMjU4ICAgICAgIGAKH4sIAAAAAAACA+3Rz0rEMBAG8Jz7FPME"
    b"3aT/FoqIC54EwZP3mB1s 1jQp0yz6+HaVBRFcTxWE7wfJQDKZHL5yo1anF9u2PVWzbfXXe"
    b"qaM6Zq66pqurZQ2uqorRa36A8c5 WyFST4ck8ULfb/f/VLlxKWZJYeX8u6b5Mf+qbr7lb7"
    b"rliDTyX92DdS/2mXsaffSjDcUjy+xT7MmU utiJG3xml4+ytNgQinvrY14WS093aYh0dVj"
    b"2G36z4xS4dGm8Lm55duKn/DFmd55M0+dX9OrzQDHR nieOe47O80xJKOWBhYSDPb2cy0IB"
    b"AAAAAAAAAAAAAAAAAAAAAMBF70s1/foAKAAAZGF0YS50YXIu Z3ogICAgIDEzMTc4OTA0N"
    b"zkgIDAgICAgIDAgICAgIDEwMDY0NCAgMTA3ICAgICAgIGAKH4sIAAAA AAACA+3KsQ3CQB"
    b"AEwCvlK4D/N4frMSGBkQz0jwmQiHCEo5lkpd09HOPv6mrMfGcbs37nR7R2Pg01"
    b"ew5r32rvNUrGDp73x7SUEpfrbZl//LZ2AAAAAAAAAAAA2NELx33R7wAoAAAK"
)

PKGDEB_SIMPLE_RELATIONS = (
    b"ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTMxODUxNjMyMiAgMCAgICAgMCAgICAgMTAwNj"
    b"Q0ICA0 ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEzMTg1MTYzMjIgIDAgICA"
    b"gIDAgICAgIDEw MDY0NCAgMzQ0ICAgICAgIGAKH4sIAAAAAAACA+3R3UrDMBQH8F7nKc4L"
    b"rGu2tYMi4tQrQRkI3mdp tNnSpKTZ0Lc37TYVQb2aIvx/0Ob09DQfPek4Obksmud5P/J5n"
    b"n0cjxLOi1mez6ecT5KMZ5NJkVCe /IJtF4QnSlZr5+03dT+9/6fSsXQ2eGdO3P9iNvuy/3"
    b"mWf+o/L6Y8oQz9P7mlkBvxpErqdNMaNfLK iKCd7diD8l0MSuJpxu6VDMNDozvJll47r8N"
    b"LSa7t08KwhZe1DrFq6+NkwphYpEbXqlW26kpqvaqG mLO33DFx5eyj0TLElDyEnF16JTYx"
    b"s+pHHidzO12pYaYh4uxWaBvipXxJN662dLaO9wv1LPqDpNI1 53GtTnrd7re+iJu3uhGG2"
    b"v2hKdQiUC26w+Hp/fAU3Tna7f8BCa+OC1ekbfzwQ3HKEgAAAAAAAAAA AAAAAAAAAACAv/"
    b"EKgcHt1gAoAABkYXRhLnRhci5neiAgICAgMTMxODUxNjMyMiAgMCAgICAgMCAg ICAgMTA"
    b"wNjQ0ICAxMDcgICAgICAgYAofiwgAAAAAAAID7cqxDcJQEETBK8UVwH2b+64HQgIjGegf "
    b"CJCIIMLRTPKC3d0+/i6f5qpX21z52bdorR+m7Fl9imw5jhVDxQbu19txHYY4nS/r8uX3aw"
    b"cAAAAA AAAAAIANPQALnD6FACgAAAo="
)


PKGDEB_VERSION_RELATIONS = (
    b"ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTMxODUxNjQ5OCAgMCAgICAgMCAgICAgMTAwNj"
    b"Q0ICA0 ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEzMTg1MTY0OTggIDAgICA"
    b"gIDAgICAgIDEw MDY0NCAgMzUwICAgICAgIGAKH4sIAAAAAAACA+3RQUvDMBQH8Jz7KXLU"
    b"w7pmazcoczj1JAgDwXuW xTVbmpQkG/rtTds5RFBPGwj/H7R5fS9N07x0SM4ui6ZF0Y5sW"
    b"mRfx0+EsUleFNNxznKSsWw0HhNa kAvY+8AdpWS1tc78Mu+v+j+VDoU1wVl95v5P8vzH/h"
    b"eMfes/m7T9z9D/s1tyseMbWdKDdF5ZM3BS 8xADn7z0mZKyNEuepQjdQ628SJZOWafCe0l"
    b"t06a5ThZOVCrEWXsXV+Nax0ly8CAbada+pI2T6y5m 9Gp2Q0dpdp2ciqfKsXBvzatWIsSS"
    b"OIbta7O+euck38XSqh1jfj7v80tnD2otu491EUueuDIhXtKV 9NFWhs628X4r33jdaJkKW"
    b"8/jLrxwqun/bhH/z6iaa9r0B0NDxQOtuKeng2n31C6qzObz1HyaEAAA AAAAAAAAAAAAAA"
    b"AAAACAy/sAwTtOtwAoAABkYXRhLnRhci5neiAgICAgMTMxODUxNjQ5OCAgMCAg ICAgMCA"
    b"gICAgMTAwNjQ0ICAxMDcgICAgICAgYAofiwgAAAAAAAID7cqxEcIwEETRK0UVgCT7UD0Q "
    b"EpgZA/0DATNEEOHoveQHu7t9/F19GpmvtpH1s2/R2mGeemYfc9RW+9SjZGzgfr0d11LidL"
    b"6sy5ff rx0AAAAAAAAAAAA29AD/ixlwACgAAAo="
)


PKGDEB_MULTIPLE_RELATIONS = (
    b"ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTMxODU4MDA3OSAgMCAgICAgMCAgICAgMTAwNj"
    b"Q0ICA0 ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEzMTg1ODAwNzkgIDAgICA"
    b"gIDAgICAgIDEw MDY0NCAgMzgzICAgICAgIGAKH4sIAAAAAAACA+3RXUvDMBQG4F7nV5xL"
    b"BVeb2nZQ5vDrShAGgvcx izaaNiXNRMEfb9atcwq6qwnC+8CW05N3bXcSH0d7lwTjPF+uf"
    b"Jwn2+sg4rzI8nERYjxKeJJmaUR5 9AcWnReOKLp/sq75Jbdr/5+Kj6VtvLNmz+dfZNmP51"
    b"+cZN/OnxdhmxKc/97NhHwWj6qkemG8bo0a OWWE17bp2J1yXShK4nHCbpX0/UWtO8lmTlu"
    b"n/VtJtl22hWHnTlbah9TChdsJY0JIja5Uq5p5V1Lr 1LyvOR1MTimNk8Ojz2bKNsFNagit"
    b"Gif0vq4yOphOv+yl7NI2D0ZLH34v1+XyOZN1bOil7MIp8RxS 98uVb92pb6Thne2Lnqv+h"
    b"fuKHw1Vym6Ebnz4KFfSta0amjyF7zP1KuowuVjaehr+RyedblezOg/T anQtDLWrOZOvhK"
    b"dKdJt504swC9XRg3WkhKxomH/MIgAAAAAAAAAAAAAAAAAAAACAHT4AFDs6bAAo AAAKZGF"
    b"0YS50YXIuZ3ogICAgIDEzMTg1ODAwNzkgIDAgICAgIDAgICAgIDEwMDY0NCAgMTA3ICAg "
    b"ICAgIGAKH4sIAAAAAAACA+3KsRHCMBBE0StFFYBkfFY9EBKYGWP3DwTMEEGEo/eSH+wejv"
    b"F39aln vtp61s++RWvTeBpy6tmjtjqMLUrGDrb7el5Kicv1tsxffr92AAAAAAAAAAAA2NE"
    b"Db6L1AQAoAAAK"
)


PKGDEB_OR_RELATIONS = (
    b"ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTMxNzg4ODg2OSAgMCAgICAgMCAgICAgMTAwNj"
    b"Q0ICA0 ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEzMTc4ODg4NjkgIDAgICA"
    b"gIDAgICAgIDEw MDY0NCAgMzc1ICAgICAgIGAKH4sIAAAAAAACA+3R30vDMBAH8D73r7g3"
    b"FbS23brBUFHwSRAFwfeY HmtmlpQ08wf4x3vbWB2Cig8ThO8H2qbp3fXCZcfJzuViXFXLZ"
    b"zGu8u3nRlIUo+GgHBXVUPaLvCwH CVXJH1h0UQWi5GHmg/sm7qfv/1R2rL2Lwdsdz380HH"
    b"45f5n6p/kXo0GeUI7579yt0o9qyhPy4Siw VdF416X3HDpZTKjI8vSOdVy9zE2n09tgfDD"
    b"xVTLa5bay6UXQjYkStQhSSFkrQXx0yS27uptQG7he rQvaPzmlMssP6O1jt0z7yD6sj9qE"
    b"XCvjolwcJnTlG0cnM7mf84uat5Yz7ednUqbTwbTrXi+kW2fm ylK7PiHFRkVqVCcnpf6kW"
    b"UrixtlX2uqZlKupXwcm47Rd1FwfUidLJh8b3qqyqr2qpJWTfzyxtC55 bi/2qfTcsJPvVi"
    b"+WWW4qSdw3J301WZoAAAAAAAAAAAAAAAAAAAAAAPzOO2wqjioAKAAACmRhdGEu dGFyLmd"
    b"6ICAgICAxMzE3ODg4ODY5ICAwICAgICAwICAgICAxMDA2NDQgIDEwNyAgICAgICBgCh+L "
    b"CAAAAAAAAgPtyrsRwjAURNFXiioAfZBcjwkJzIyB/oGAGSIc4eic5Aa7h2P8XX6Zen+3TD"
    b"1/9yNK"
    b"GadWR2ltRC651hGpxw4et/u8phTny3Vdfvy2dgAAAAAAAAAAANjRE6Lr2rEAKAAACg=="
)
PKGDEB_BROKEN_DESCRIPTION = (
    b"ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTY3OTIzNzM2MyAgMCAgICAgMCAgICAgMTAwNj"
    b"Q0ICA0ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuenN0IDE2NzkyMzczNjMgIDAgICAg"
    b"IDAgICAgIDEwMDY0NCAgMjY4ICAgICAgIGAKKLUv/QBoHQgAwk4uInBJ21bxEmhb1HK7ih"
    b"shSQan5wcgNCga0N2kn+wSVP33XwppIIeGBx1QBNf1M9H1XWE3fk4z9afsrX5H3l+GtZlz"
    b"e4+y5nUOhExsDOqo26a91qhCFwIjoHFGy9YXGwUUALQ1b58CXb7ja2tgOLf/RO7YGH6FkZ"
    b"DSBX4jGM9bdNozbPZ6wX+hSyfsAu9B0kzUoVTKxFLKOtZKnH98zgiU0f1T9TfCJxPRRJSi"
    b"HCmRIGktlSkRREmJQAEcILBKRqwcAxUD8QEAkmWFeAkIIKSmWvDwQBNwfBxuFeZKr7/ACR"
    b"VYL8ABU/3amMvgAU33hMJwAGz/tzlrw2MACcQUwHyabmRhdGEudGFyLnpzdCAgICAxNjc5"
    b"MjM3MzYzICAwICAgICAwICAgICAxMDA2NDQgIDg0ICAgICAgICBgCii1L/0AaF0CADQDLi"
    b"8AMDc1NTE3NTEAMTQ0MDU1NjU3NDcAMDEwNTcwACA1AAB1c3RhciAgAGJyMHRoM3IACSCQ"
    b"mwfMBhyGBqrXn71BlmwNcH3CQw=="
)


HASH1 = base64.decodebytes(b"/ezv4AefpJJ8DuYFSq4RiEHJYP4=")
HASH2 = base64.decodebytes(b"glP4DwWOfMULm0AkRXYsH/exehc=")
HASH3 = base64.decodebytes(b"NJM05mj86veaSInYxxqL1wahods=")
HASH_MINIMAL = b"6\xce\x8f\x1bM\x82MWZ\x1a\xffjAc(\xdb(\xa1\x0eG"
HASH_SIMPLE_RELATIONS = (
    b"'#\xab&k\xe6\xf5E\xcfB\x9b\xceO7\xe6\xec\xa9\xddY\xaa"
)
HASH_VERSION_RELATIONS = (
    b"\x84\xc9\xb4\xb3\r\x95\x16\x03\x95\x98\xc0\x14u\x06\xf7eA\xe65\xd1"
)
HASH_MULTIPLE_RELATIONS = (
    b"\xec\xcdi\xdc\xde-\r\xc3\xd3\xc9s\x84\xe4\xc3\xd6\xc4\x12T\xa6\x0e"
)
HASH_OR_RELATIONS = (
    b"\xa1q\xf4*\x1c\xd4L\xa1\xca\xf1\xfa?\xc3\xc7\x9f\x88\xd53B\xc9"
)
HASH_BROKEN_DESCRIPTION = (
    b"\x16\xbd\xb8+\xed\xc0\x07\x84f!\xe6d\xea\xe7\xaf\xc6\xe4\t\xad\xd7"
)


def create_deb(target_dir, pkg_name, pkg_data):
    """Create a Debian package in the specified C{target_dir}."""
    path = os.path.join(target_dir, pkg_name)
    data = base64.decodebytes(pkg_data)
    create_binary_file(path, data)


def create_simple_repository(target_dir):
    """Create a simple deb-dir repository with in C{target_dir}."""
    create_deb(target_dir, PKGNAME1, PKGDEB1)
    create_deb(target_dir, PKGNAME2, PKGDEB2)
    create_deb(target_dir, PKGNAME3, PKGDEB3)
