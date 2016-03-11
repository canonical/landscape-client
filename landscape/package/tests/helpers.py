import base64
import os
import textwrap
import time

import apt_inst
import apt_pkg

from landscape.lib.fs import append_file, create_file
from landscape.package.facade import AptFacade


class AptFacadeHelper(object):
    """Helper that sets up an AptFacade with a tempdir as its root."""

    def set_up(self, test_case):
        test_case.apt_root = test_case.makeDir()
        self.dpkg_status = os.path.join(
            test_case.apt_root, "var", "lib", "dpkg", "status")
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

    def _add_package(self, packages_file, name, architecture="all",
                     version="1.0", control_fields=None):
        if control_fields is None:
            control_fields = {}
        package_stanza = textwrap.dedent("""
                Package: %(name)s
                Priority: optional
                Section: misc
                Installed-Size: 1234
                Maintainer: Someone
                Architecture: %(architecture)s
                Source: source
                Version: %(version)s
                Description: description
                """ % {"name": name, "version": version,
                       "architecture": architecture})
        package_stanza = apt_pkg.rewrite_section(
            apt_pkg.TagSection(package_stanza), apt_pkg.REWRITE_PACKAGE_ORDER,
            control_fields.items())
        append_file(packages_file, "\n" + package_stanza + "\n")

    def _add_system_package(self, name, architecture="all", version="1.0",
                            control_fields=None):
        """Add a package to the dpkg status file."""
        system_control_fields = {"Status": "install ok installed"}
        if control_fields is not None:
            system_control_fields.update(control_fields)
        self._add_package(
            self.dpkg_status, name, architecture=architecture, version=version,
            control_fields=system_control_fields)

    def _install_deb_file(self, path):
        """Fake the the given deb file is installed in the system."""
        deb_file = open(path)
        deb = apt_inst.DebFile(deb_file)
        control = deb.control.extractdata("control")
        deb_file.close()
        lines = control.splitlines()
        lines.insert(1, "Status: install ok installed")
        status = "\n".join(lines)
        append_file(self.dpkg_status, status + "\n\n")

    def _add_package_to_deb_dir(self, path, name, architecture="all",
                                version="1.0", control_fields=None):
        """Add fake package information to a directory.

        There will only be basic information about the package
        available, so that get_packages() have something to return.
        There won't be an actual package in the dir.
        """
        if control_fields is None:
            control_fields = {}
        self._add_package(
            os.path.join(path, "Packages"), name, architecture=architecture,
            version=version, control_fields=control_fields)

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
            skeleton = facade.get_package_skeleton(
                version, with_info=False)
            hash = skeleton.get_hash()
            facade._pkg2hash[(version.package, version)] = hash
            hash_ids[hash] = version.package.id
        store.set_hash_ids(hash_ids)


class SimpleRepositoryHelper(object):
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

PKGDEB1 = ("ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTE2NjExNDQ5MyAgMCAgICAgMCAgICAgMT"
           "AwNjQ0ICA0ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDExNjYxMTQ0OTMg"
           "IDAgICAgIDAgICAgIDEwMDY0NCAgNDUyICAgICAgIGAKH4sIAAAAAAAAA+3UQW+bMB"
           "QHcM58Ch+7QwCbEJpomzat0rTDpmiRenfNC7EGNnuGSOmnnwMlyVK1O6VT1feTkJ+e"
           "/wRh40RxcHGJl2dZP3rnY1/zJJsmIs9Fvs/5UQQsC15A51qJjAVobftc7l/zr1QU10"
           "XmutpdeP9n0+mT+8+5+Hv/fSOdBiyh/b84MYM1n2fz7G4t0+u5SvMkhbTgs3wu+CwB"
           "xjqHsdtIhLiwKjayBh6rjTQlVLaMbuBOSxOV92FAXuX5V9a0aKv/eP5zkZyf/1TQ+X"
           "8RS6l+yRIWrD/Y4S2g09Ys2HYo+AShAun81ApU2099Rds1PFyitqjb3YLZZj8hq/Az"
           "qo1ufa5D/4uyqnwIJjfQgCncgjUICL87jdA/jF19OGmND3wXHvLn4UfJn6BsXY/hsT"
           "7Jj63jLauuLMG1/gb3UB3iY+MY/mLNutJqn1ZjeYgfOsf8Eu1WF9C/6lANq/rN+I+s"
           "qqCYrPS9XxlxHX6X2rT+AvQLuv8Gt5b90FDDDpC9L4fOJ/PQiQy0H/3COIW6GXZh1d"
           "W1xB0P2Umb078wIYQQQgghhBBCCCGEEEIIIYS8UX8AYydx2gAoAABkYXRhLnRhci5n"
           "eiAgICAgMTE2NjExNDQ5MyAgMCAgICAgMCAgICAgMTAwNjQ0ICAzOTQgICAgICAgYA"
           "ofiwgAAAAAAAAD09NnoDkwAAJzU1MwDQToNJhtaGBqYmBkbm5kDlIHpI0YFEwZ6ABK"
           "i0sSixQUGIry80vwqSMkP0SBnn5pcZH+YIp/EwYDIMd4NP7pGP/FGYlFqfqDJ/4NzY"
           "xNRuOf3vGfkp+sPzji38jEwHA0/gci/vMSc1MN9Qc6/o2B7NH4H7j4T85IzEtPzclP"
           "13NJTcpMzNNLr6Iw/s1MTHDGv5GxOSz+zUxNjYDxbw7kMSgYjMY/zYF8NwdHVm2jKx"
           "Mzepwz6J7y5jpkIOH6sDKssF1rmUqYzBX2piZj9zyFad5RHv8dLoXsqua2spF3v+PQ"
           "ffXIlN8aYepsu3x2u0202VX+QFC10st6vvMfDdacgtdzKtpe5G5tuFYx5elcpXm27O"
           "d8LH7Oj3mqP7VgD8P6dTmJ33dsPnpuBnPO3SvLDNlu6ay9It6yZon0BIZRMApGwSgY"
           "BaNgFIyCUTAKRsEoGAWjYBSMglEwCkbBKBgFo2AUjIJRMApGAUkAADhX8vgAKAAA ")

PKGDEB2 = ("ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTE2NjExNDUyMiAgMCAgICAgMCAgICAgMT"
           "AwNjQ0ICA0ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDExNjYxMTQ1MjIg"
           "IDAgICAgIDAgICAgIDEwMDY0NCAgNDUyICAgICAgIGAKH4sIAAAAAAAAA+3UTY/TMB"
           "AG4JzzK3yEQ/Phxk1aAQKxEuIAqrYSd+NMU4vEDuOkUvfX4yabthQBpy5aMY9UZTR+"
           "06ieuFEc3Fzi5UIMV+/6OtRpIrKE5/l8zn0/z9MsYCJ4Ar3rJDIWoLXdn3J/W3+mor"
           "gphesbd+P5L7Lst/NPU/7z/H2DLwKW0PxvrixSlYkiAVGIxZJnaSHFdilUDplabnnG"
           "WO8wdjuJEJdWxUY2wGO1k6aC2lbRHXzV0kTVQxiQZ3n+lTUd2vofnv+cJ9fnf57S+X"
           "8Sa6m+yQpWbDjY4RdAp61Zsf1Y8BlCDdL5pQ2oblj6gLZvebhGbVF3hxWz7XFB1uE7"
           "VDvd+VyP/htlXfsQzO6gBVO6FWsREL73GmF4GHvx+qI1PfBleMpfh39J3oOyTTOFp/"
           "oiP7XOt2z6qgLX+RvcY3WKT41z+L0121qrY1pN5Sl+6pzza7R7XcLwU8dq3NWPxr9k"
           "dQ3lbKMf/M7wIvwkten8B9Bv6PEd3Fv2WUMDB0D2qho7b81jJzLQvfEb4xTqdpzCpm"
           "8aiQcesos2p39hQgghhBBCCCGEEEIIIYQQQgj5T/0AyM2cyQAoAABkYXRhLnRhci5n"
           "eiAgICAgMTE2NjExNDUyMiAgMCAgICAgMCAgICAgMTAwNjQ0ICAzOTMgICAgICAgYA"
           "ofiwgAAAAAAAAD09NnoDkwAAJzU1MwDQToNJhtaGBqYmBkbm5sbAgUNzc3NGZQMGWg"
           "AygtLkksUlBgKMrPL8GnjpD8EAV6+qXFRfqDLP6BHCOT0finX/wXZyQWpeoPnvg3ND"
           "MyG41/esd/Sn6y/uCIfyNj89Hyf0DiPy8xN9VIf6Dj39jY3HQ0/gcu/pMzEvPSU3Py"
           "0/VcUpMyE/P00qsojH8zExOc8Q/M7Yj4Bxb8BobmBsDkomAwGv80B/LdHBzX6hpdmZ"
           "jR45xB99RGrkMGEq4Pbf0L3UWDL4XIRIk6Hjx7Urzj6SSxS/YTzKbu28sqe/64oPmF"
           "JGPj3lqR1cLMdz12u04rLHp/gM2y0mv3HOc/GqxvCl7PqWh7kbux6VrFk69zlefZsu"
           "v5WPycH/NUv7VgF8N6vfeBcgXp3NlnBFNDw5eZsd1as/aK+JzyvZ0TGEbBKBgFo2AU"
           "jIJRMApGwSgYBaNgFIyCUTAKRsEoGAWjYBSMglEwCkbBKBgFJAEAu4OlKQAoAAAK")

PKGDEB3 = ("ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTE2OTE0ODIwMyAgMCAgICAgMCAgICAgMT"
           "AwNjQ0ICA0ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDExNjkxNDgyMDMg"
           "IDAgICAgIDAgICAgIDEwMDY0NCAgNDUxICAgICAgIGAKH4sIAAAAAAAAA+3UwY7TMB"
           "AG4JzzFD7CoUkax7iqYAViJcQBVFGJu3GmqbWJHcZJpe7T4yabtnS1cOqiFfNJVUbj"
           "P43qiZuk0dVlgRRiuAaX16GeZ0JwWRSF4KEvZc4jJqJn0PtOIWMROtf9Kfe39RcqSZ"
           "tS+L7xV57/m6J4cv7zef77/EODi4hlNP+r4yIrc1mUUs43C1VmhcxLEAKkFouCbzRj"
           "vcfUbxVCWjqdWtUAT/VW2QpqVyW38MMom1T3cURe5PnXznbo6n94/mWeXZ5/ntP5fx"
           "Yrpe9UBUs2HOz4O6A3zi7Zbiz4DKEG5cPSGnQ3LH1C17c8XqFxaLr9krn2sKDq+APq"
           "relCrsfwjaquQwhmt9CCLf2StQgIP3uDMDyMvXp31poe+Do+5i/Dj5LfQLummcJTfZ"
           "afWqdb1n1Vge/CDf6hOsanxin80dlNbfQhrafyGD92TvkVup0pYfipYzXu6mcbXrK6"
           "hnK2NvdhZ/JF/EUZ24UPYNjQwzu4c+yrgQb2gOxtNXbe24dOYqG7CRvjNZp2nMK6bx"
           "qFex6zszanf2FCCCGEEEIIIYQQQgghhBBCCPlP/QK+dA1dACgAAApkYXRhLnRhci5n"
           "eiAgICAgMTE2OTE0ODIwMyAgMCAgICAgMCAgICAgMTAwNjQ0ICAzOTkgICAgICAgYA"
           "ofiwgAAAAAAAAD09NnoDkwAAJzU1MwDQToNJhtaGBqamxuYmJiagQUNzc3MmJQMGWg"
           "AygtLkksUlBgKMrPL8GnjpD8EAV6+qXFRfqDKf4NGQyAHOPR+Kdj/BdnJBal6g+e+D"
           "c0MzYZjX96x39KfrL+4Ih/IxMDw9H4H4j4z0vMTTXWH8j4B9b/hsYmBqaj8T9w8Z+c"
           "kZiXnpqTn67nkpqUmZinl15FYfybmZjgjH8jY3NE/JuYAePfHKieQcFgNP5pDuS7OT"
           "jUTq53ZWJGj3MG3VPeXIcMJFwfVoYVtmstW+Imc4W9qcnYPU9hmneUx3+HSyG7qrmt"
           "bOTd7zh0Xz0y5bdGmDrbLp/dbhNtdpU/EFSt9LKe7/xHgzWn4PWcirYXuVsbrlVMeT"
           "pXaZ4t+zkfi5/zY57qTy3Yw7B+XU7g+8L07rmG7Fe2bVxmyHZLZ+0V8Sl2Xj8mMIyC"
           "UTAKRsEoGAWjYBSMglEwCkbBKBgFo2AUjIJRMApGwSgYBaNgFIyCUTAKSAIAY/FOKA"
           "AoAAAK")

PKGDEB4 = ("ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTI3NjUxMTU3OC41MCAgICAgMCAgICAgNj"
           "Q0ICAgICA0\nICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEyNzY1MTE1Nz"
           "guNTAgICAgIDAgICAgIDY0\nNCAgICAgMjk1ICAgICAgIGAKH4sIAFoFFkwC/+3TwU"
           "6EMBAGYM48RV9goS0dqnszMSbeTEy8F6iE\nCJS04MGnt2GzBzHqiVWT/7u0yVCm8G"
           "eyPNkdjzTRukbbdd0LoTgpLqmQCRdCckoYJRewhNn4eBXv\n3Pzdcz/Vtx/3T2R57c"
           "bZu37n/EulvsxfqnKTvyyFTBhH/rt7MPWLae2RjWawIn2yPnRuPLLX00Zk\n4uBtb0"
           "2Ixfsx/qu+t83hsXuLRwRPb22ofTfN65kbFsww9ZYtU+tNY9l0ennK7pxnsw1zN7bn"
           "YsjS\nD72LT72Lc2eVJrDb/A8NhWUIvzj/nMR2/kkKzP8lNERFJZWOGWiqiF89ayVt"
           "qbWhSlfimrEsD26w\nGEEAAAAAAAAAAAAAAAAAAIC/6x1piYqhACgAAApkYXRhLnRh"
           "ci5neiAgICAgMTI3NjUxMTU3OC41\nMCAgICAgMCAgICAgNjQ0ICAgICAxNDUgICAg"
           "ICAgYAofiwgAWgUWTAL/7dFBCsMgEEDRWfcUniCZ\nsU57kJ5ASJdFSOz9K9kULLQr"
           "C4H/NiPqQvnTLMNpc3XfZ9PPfW2W1JOae9s3i5okuPzBc6t5bU9Z\nS6nf7v067z93"
           "ENO8lcd9fP/LZ/d3f4td/6h+lqD0H+7W6ocl13wSAAAAAAAAAAAAAAAAAAfzAqr5\n"
           "GFYAKAAACg==\n")

PKGDEB_MINIMAL = (
    "ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTMxNzg5MDQ3OSAgMCAgICAgMCAgICAgMTAwNj"
    "Q0ICA0 ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEzMTc4OTA0NzkgIDAgICA"
    "gIDAgICAgIDEw MDY0NCAgMjU4ICAgICAgIGAKH4sIAAAAAAACA+3Rz0rEMBAG8Jz7FPME"
    "3aT/FoqIC54EwZP3mB1s 1jQp0yz6+HaVBRFcTxWE7wfJQDKZHL5yo1anF9u2PVWzbfXXe"
    "qaM6Zq66pqurZQ2uqorRa36A8c5 WyFST4ck8ULfb/f/VLlxKWZJYeX8u6b5Mf+qbr7lb7"
    "rliDTyX92DdS/2mXsaffSjDcUjy+xT7MmU utiJG3xml4+ytNgQinvrY14WS093aYh0dVj"
    "2G36z4xS4dGm8Lm55duKn/DFmd55M0+dX9OrzQDHR nieOe47O80xJKOWBhYSDPb2cy0IB"
    "AAAAAAAAAAAAAAAAAAAAAMBF70s1/foAKAAAZGF0YS50YXIu Z3ogICAgIDEzMTc4OTA0N"
    "zkgIDAgICAgIDAgICAgIDEwMDY0NCAgMTA3ICAgICAgIGAKH4sIAAAA AAACA+3KsQ3CQB"
    "AEwCvlK4D/N4frMSGBkQz0jwmQiHCEo5lkpd09HOPv6mrMfGcbs37nR7R2Pg01"
    "ew5r32rvNUrGDp73x7SUEpfrbZl//LZ2AAAAAAAAAAAA2NELx33R7wAoAAAK")

PKGDEB_SIMPLE_RELATIONS = (
    "ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTMxODUxNjMyMiAgMCAgICAgMCAgICAgMTAwNj"
    "Q0ICA0 ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEzMTg1MTYzMjIgIDAgICA"
    "gIDAgICAgIDEw MDY0NCAgMzQ0ICAgICAgIGAKH4sIAAAAAAACA+3R3UrDMBQH8F7nKc4L"
    "rGu2tYMi4tQrQRkI3mdp tNnSpKTZ0Lc37TYVQb2aIvx/0Ob09DQfPek4Obksmud5P/J5n"
    "n0cjxLOi1mez6ecT5KMZ5NJkVCe /IJtF4QnSlZr5+03dT+9/6fSsXQ2eGdO3P9iNvuy/3"
    "mWf+o/L6Y8oQz9P7mlkBvxpErqdNMaNfLK iKCd7diD8l0MSuJpxu6VDMNDozvJll47r8N"
    "LSa7t08KwhZe1DrFq6+NkwphYpEbXqlW26kpqvaqG mLO33DFx5eyj0TLElDyEnF16JTYx"
    "s+pHHidzO12pYaYh4uxWaBvipXxJN662dLaO9wv1LPqDpNI1 53GtTnrd7re+iJu3uhGG2"
    "v2hKdQiUC26w+Hp/fAU3Tna7f8BCa+OC1ekbfzwQ3HKEgAAAAAAAAAA AAAAAAAAAACAv/"
    "EKgcHt1gAoAABkYXRhLnRhci5neiAgICAgMTMxODUxNjMyMiAgMCAgICAgMCAg ICAgMTA"
    "wNjQ0ICAxMDcgICAgICAgYAofiwgAAAAAAAID7cqxDcJQEETBK8UVwH2b+64HQgIjGegf "
    "CJCIIMLRTPKC3d0+/i6f5qpX21z52bdorR+m7Fl9imw5jhVDxQbu19txHYY4nS/r8uX3aw"
    "cAAAAA AAAAAIANPQALnD6FACgAAAo=")


PKGDEB_VERSION_RELATIONS = (
    "ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTMxODUxNjQ5OCAgMCAgICAgMCAgICAgMTAwNj"
    "Q0ICA0 ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEzMTg1MTY0OTggIDAgICA"
    "gIDAgICAgIDEw MDY0NCAgMzUwICAgICAgIGAKH4sIAAAAAAACA+3RQUvDMBQH8Jz7KXLU"
    "w7pmazcoczj1JAgDwXuW xTVbmpQkG/rtTds5RFBPGwj/H7R5fS9N07x0SM4ui6ZF0Y5sW"
    "mRfx0+EsUleFNNxznKSsWw0HhNa kAvY+8AdpWS1tc78Mu+v+j+VDoU1wVl95v5P8vzH/h"
    "eMfes/m7T9z9D/s1tyseMbWdKDdF5ZM3BS 8xADn7z0mZKyNEuepQjdQ628SJZOWafCe0l"
    "t06a5ThZOVCrEWXsXV+Nax0ly8CAbada+pI2T6y5m 9Gp2Q0dpdp2ciqfKsXBvzatWIsSS"
    "OIbta7O+euck38XSqh1jfj7v80tnD2otu491EUueuDIhXtKV 9NFWhs628X4r33jdaJkKW"
    "8/jLrxwqun/bhH/z6iaa9r0B0NDxQOtuKeng2n31C6qzObz1HyaEAAA AAAAAAAAAAAAAA"
    "AAAACAy/sAwTtOtwAoAABkYXRhLnRhci5neiAgICAgMTMxODUxNjQ5OCAgMCAg ICAgMCA"
    "gICAgMTAwNjQ0ICAxMDcgICAgICAgYAofiwgAAAAAAAID7cqxEcIwEETRK0UVgCT7UD0Q "
    "EpgZA/0DATNEEOHoveQHu7t9/F19GpmvtpH1s2/R2mGeemYfc9RW+9SjZGzgfr0d11LidL"
    "6sy5ff rx0AAAAAAAAAAAA29AD/ixlwACgAAAo=")


PKGDEB_MULTIPLE_RELATIONS = (
    "ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTMxODU4MDA3OSAgMCAgICAgMCAgICAgMTAwNj"
    "Q0ICA0 ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEzMTg1ODAwNzkgIDAgICA"
    "gIDAgICAgIDEw MDY0NCAgMzgzICAgICAgIGAKH4sIAAAAAAACA+3RXUvDMBQG4F7nV5xL"
    "BVeb2nZQ5vDrShAGgvcx izaaNiXNRMEfb9atcwq6qwnC+8CW05N3bXcSH0d7lwTjPF+uf"
    "Jwn2+sg4rzI8nERYjxKeJJmaUR5 9AcWnReOKLp/sq75Jbdr/5+Kj6VtvLNmz+dfZNmP51"
    "+cZN/OnxdhmxKc/97NhHwWj6qkemG8bo0a OWWE17bp2J1yXShK4nHCbpX0/UWtO8lmTlu"
    "n/VtJtl22hWHnTlbah9TChdsJY0JIja5Uq5p5V1Lr 1LyvOR1MTimNk8Ojz2bKNsFNagit"
    "Gif0vq4yOphOv+yl7NI2D0ZLH34v1+XyOZN1bOil7MIp8RxS 98uVb92pb6Thne2Lnqv+h"
    "fuKHw1Vym6Ebnz4KFfSta0amjyF7zP1KuowuVjaehr+RyedblezOg/T anQtDLWrOZOvhK"
    "dKdJt504swC9XRg3WkhKxomH/MIgAAAAAAAAAAAAAAAAAAAACAHT4AFDs6bAAo AAAKZGF"
    "0YS50YXIuZ3ogICAgIDEzMTg1ODAwNzkgIDAgICAgIDAgICAgIDEwMDY0NCAgMTA3ICAg "
    "ICAgIGAKH4sIAAAAAAACA+3KsRHCMBBE0StFFYBkfFY9EBKYGWP3DwTMEEGEo/eSH+wejv"
    "F39aln vtp61s++RWvTeBpy6tmjtjqMLUrGDrb7el5Kicv1tsxffr92AAAAAAAAAAAA2NE"
    "Db6L1AQAoAAAK")


PKGDEB_OR_RELATIONS = (
    "ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTMxNzg4ODg2OSAgMCAgICAgMCAgICAgMTAwNj"
    "Q0ICA0 ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDEzMTc4ODg4NjkgIDAgICA"
    "gIDAgICAgIDEw MDY0NCAgMzc1ICAgICAgIGAKH4sIAAAAAAACA+3R30vDMBAH8D73r7g3"
    "FbS23brBUFHwSRAFwfeY HmtmlpQ08wf4x3vbWB2Cig8ThO8H2qbp3fXCZcfJzuViXFXLZ"
    "zGu8u3nRlIUo+GgHBXVUPaLvCwH CVXJH1h0UQWi5GHmg/sm7qfv/1R2rL2Lwdsdz380HH"
    "45f5n6p/kXo0GeUI7579yt0o9qyhPy4Siw VdF416X3HDpZTKjI8vSOdVy9zE2n09tgfDD"
    "xVTLa5bay6UXQjYkStQhSSFkrQXx0yS27uptQG7he rQvaPzmlMssP6O1jt0z7yD6sj9qE"
    "XCvjolwcJnTlG0cnM7mf84uat5Yz7ednUqbTwbTrXi+kW2fm ylK7PiHFRkVqVCcnpf6kW"
    "UrixtlX2uqZlKupXwcm47Rd1FwfUidLJh8b3qqyqr2qpJWTfzyxtC55 bi/2qfTcsJPvVi"
    "+WWW4qSdw3J301WZoAAAAAAAAAAAAAAAAAAAAAAPzOO2wqjioAKAAACmRhdGEu dGFyLmd"
    "6ICAgICAxMzE3ODg4ODY5ICAwICAgICAwICAgICAxMDA2NDQgIDEwNyAgICAgICBgCh+L "
    "CAAAAAAAAgPtyrsRwjAURNFXiioAfZBcjwkJzIyB/oGAGSIc4eic5Aa7h2P8XX6Zen+3TD"
    "1/9yNK"
    "GadWR2ltRC651hGpxw4et/u8phTny3Vdfvy2dgAAAAAAAAAAANjRE6Lr2rEAKAAACg==")


HASH1 = base64.decodestring("/ezv4AefpJJ8DuYFSq4RiEHJYP4=")
HASH2 = base64.decodestring("glP4DwWOfMULm0AkRXYsH/exehc=")
HASH3 = base64.decodestring("NJM05mj86veaSInYxxqL1wahods=")
HASH4 = 'c\xc1\xe6\xe1U\xde\xb6:\x03\xcb\xb9\xdc\xee\x91\xb7"\xc9\xb1\xe4\x8f'
HASH5 = '|\x93K\xe0gx\xba\xe4\x85\x84\xd9\xf4%\x8bB\xbdR\x97\xdb\xfc'
HASH6 = '\xedt!=,\\\rk\xa7\xe3$\xfb\x06\x9c\x88\x92)\xc2\xfb\xd6'
HASH7 = 'D\xb1\xb6\xf5\xaa\xa8i\x84\x07#x\x97\x01\xf7`.\x9b\xde\xfb '
HASH_MINIMAL = "6\xce\x8f\x1bM\x82MWZ\x1a\xffjAc(\xdb(\xa1\x0eG"
HASH_SIMPLE_RELATIONS = (
    "'#\xab&k\xe6\xf5E\xcfB\x9b\xceO7\xe6\xec\xa9\xddY\xaa")
HASH_VERSION_RELATIONS = (
    '\x84\xc9\xb4\xb3\r\x95\x16\x03\x95\x98\xc0\x14u\x06\xf7eA\xe65\xd1')
HASH_MULTIPLE_RELATIONS = (
    '\xec\xcdi\xdc\xde-\r\xc3\xd3\xc9s\x84\xe4\xc3\xd6\xc4\x12T\xa6\x0e')
HASH_OR_RELATIONS = (
    '\xa1q\xf4*\x1c\xd4L\xa1\xca\xf1\xfa?\xc3\xc7\x9f\x88\xd53B\xc9')

RELEASES = {"hardy": """Origin: Ubuntu
Label: Ubuntu
Codename: hardy
Version: 8.04
Date: Tue, 31 Mar 2009 13:30:02 +0000
Architectures: amd64 i386
Components: main restricted
MD5Sum:
 356312bc1c0ab2b8dbe5c67f09879497 827 main/binary-i386/Packages
 ad2d9b94381264ce25cda7cfa1b2da03 555 main/binary-i386/Packages.gz
 2f6ee66ed2d2b4115fabc8eed428e42e 78 main/binary-i386/Release
 f0fd5c1bb18584cf07f9bf4a9f2e6d92 605 main/binary-amd64/Packages
 98860034ca03a73a9face10af8238a81 407 main/binary-amd64/Packages.gz
 7e40db962fe49b6db232bf559cf6f79d 79 main/binary-amd64/Release
 99e2e7213a7fdd8dd6860623bbf700e6 538 restricted/binary-i386/Packages
 7771307958f2800bafb5cd96292308bd 384 restricted/binary-i386/Packages.gz
 8686ad9c5d83484dc66a1eca2bd8030f 84 restricted/binary-i386/Release
 99e2e7213a7fdd8dd6860623bbf700e6 538 restricted/binary-amd64/Packages
 7771307958f2800bafb5cd96292308bd 384 restricted/binary-amd64/Packages.gz
 6e24798a6089cd3a21226182784995e9 85 restricted/binary-amd64/Release
SHA1:
 1f39494284f8da4a1cdd788a3d91a048c5edf7f5 827 main/binary-i386/Packages
 e79a66d7543f24f77a9ffe1409431ae717781375 555 main/binary-i386/Packages.gz
 5fe86036c60d6210b662df3acc238e2936f03581 78 main/binary-i386/Release
 37ba69be70f4a79506038c0124293187bc879014 605 main/binary-amd64/Packages
 65dca66c72b18d59cdcf671775104e86cbe2123a 407 main/binary-amd64/Packages.gz
 c9810732c61aa7de2887b5194c6a09d0b6118664 79 main/binary-amd64/Release
 4cdb64c700f798f719f5c81ae42e44582be094c5 538 restricted/binary-i386/Packages
 190f980fd80d58284129ee050f9eb70b9590fedb 384 \
restricted/binary-i386/Packages.gz
 b1d1a4d57f5c8d70184c9661a087b8a92406c76d 84 restricted/binary-i386/Release
 4cdb64c700f798f719f5c81ae42e44582be094c5 538 restricted/binary-amd64/Packages
 190f980fd80d58284129ee050f9eb70b9590fedb 384\
 restricted/binary-amd64/Packages.gz
 4bd64fb2ef44037254729ab514d3403a65db7123 85 restricted/binary-amd64/Release
""",
            "hardy-updates": """Origin: Ubuntu
Label: Ubuntu
Codename: hardy-updates
Version: 8.04
Date: Tue, 31 Mar 2009 13:32:17 +0000
Architectures: i386 amd64
Components: main restricted
MD5Sum:
 a23ba734dc4fe7c1ec8dc960cc670b8e 1227 main/binary-i386/Packages
 2d6d271964be8000808abfa2b0e999b7 713 main/binary-i386/Packages.gz
 2f6ee66ed2d2b4115fabc8eed428e42e 78 main/binary-i386/Release
 a23ba734dc4fe7c1ec8dc960cc670b8e 1227 main/binary-amd64/Packages
 2d6d271964be8000808abfa2b0e999b7 713 main/binary-amd64/Packages.gz
 7e40db962fe49b6db232bf559cf6f79d 79 main/binary-amd64/Release
 d41d8cd98f00b204e9800998ecf8427e 0 restricted/binary-i386/Packages
 7029066c27ac6f5ef18d660d5741979a 20 restricted/binary-i386/Packages.gz
 8686ad9c5d83484dc66a1eca2bd8030f 84 restricted/binary-i386/Release
 d41d8cd98f00b204e9800998ecf8427e 0 restricted/binary-amd64/Packages
 7029066c27ac6f5ef18d660d5741979a 20 restricted/binary-amd64/Packages.gz
 6e24798a6089cd3a21226182784995e9 85 restricted/binary-amd64/Release
SHA1:
 9867c9f7ebbb5741fc589d0d4395ea8f74f3b5e4 1227 main/binary-i386/Packages
 2a7061fa162a607a63453c0360678052a38f0259 713 main/binary-i386/Packages.gz
 5fe86036c60d6210b662df3acc238e2936f03581 78 main/binary-i386/Release
 9867c9f7ebbb5741fc589d0d4395ea8f74f3b5e4 1227 main/binary-amd64/Packages
 2a7061fa162a607a63453c0360678052a38f0259 713 main/binary-amd64/Packages.gz
 c9810732c61aa7de2887b5194c6a09d0b6118664 79 main/binary-amd64/Release
 da39a3ee5e6b4b0d3255bfef95601890afd80709 0 restricted/binary-i386/Packages
 46c6643f07aa7f6bfe7118de926b86defc5087c4 20 restricted/binary-i386/Packages.gz
 b1d1a4d57f5c8d70184c9661a087b8a92406c76d 84 restricted/binary-i386/Release
 da39a3ee5e6b4b0d3255bfef95601890afd80709 0 restricted/binary-amd64/Packages
 46c6643f07aa7f6bfe7118de926b86defc5087c4 20\
 restricted/binary-amd64/Packages.gz
 4bd64fb2ef44037254729ab514d3403a65db7123 85 restricted/binary-amd64/Release
"""}

PACKAGES = {"hardy":
            {"restricted":
             {"amd64": """Package: kairos
Version: 0.0.8
Architecture: all
Maintainer: Free Ekanayaka <freee@debian.org>
Installed-Size: 192
Pre-Depends: libaugeas0, python-augeas, augeas-tools, jackd, rotter, monit,\
 darkice, soma, python-remix, nfs-kernel-server, icecast2
Priority: extra
Section: admin
Filename: pool/restricted/k/kairos/kairos_0.0.8_all.deb
Size: 60768
SHA1: 1e5cc71cbd33d2b26a8feb19a48e815f271cd335
MD5sum: 5fd717ed3d15db25ffaa9d05fec62e42
Description: kairos customisation package
 This package configures and customises an kairos
 machine.

""",
              "i386": """Package: kairos
Version: 0.0.8
Architecture: all
Maintainer: Free Ekanayaka <freee@debian.org>
Installed-Size: 192
Pre-Depends: libaugeas0, python-augeas, augeas-tools, jackd, rotter, monit,\
 darkice, soma, python-remix, nfs-kernel-server, icecast2
Priority: extra
Section: admin
Filename: pool/restricted/k/kairos/kairos_0.0.8_all.deb
Size: 60768
SHA1: 1e5cc71cbd33d2b26a8feb19a48e815f271cd335
MD5sum: 5fd717ed3d15db25ffaa9d05fec62e42
Description: kairos customisation package
 This package configures and customises an kairos
 machine.

"""},
             "main":
             {"amd64": """Package: libclthreads2
Source: clthreads
Version: 2.4.0-1
Architecture: amd64
Maintainer: Debian Multimedia Maintainers\
 <pkg-multimedia-maintainers@lists.alioth.debian.org>
Installed-Size: 80
Depends: libc6 (>= 2.3.2), libgcc1 (>= 1:4.1.1), libstdc++6 (>= 4.1.1)
Priority: extra
Section: libs
Filename: pool/main/c/clthreads/libclthreads2_2.4.0-1_amd64.deb
Size: 12938
SHA1: dc6cb78896642dd436851888b8bd4454ab8f421b
MD5sum: 19960adb88e178fb7eb4997b47eee05b
Description: POSIX threads C++ access library
 C++ wrapper library around the POSIX threads API. This package includes
 the shared library object.

""",
              "i386": """Package: syslinux
Version: 2:3.73+dfsg-2
Architecture: i386
Maintainer: Daniel Baumann <daniel@debian.org>
Installed-Size: 140
Depends: libc6 (>= 2.7-1), syslinux-common (= 2:3.73+dfsg-2), dosfstools,\
 mtools
Homepage: http://syslinux.zytor.com/
Priority: optional
Section: utils
Filename: pool/main/s/syslinux/syslinux_3.73+dfsg-2_i386.deb
Size: 70384
SHA1: 6edf6a7e81a5e9759270872e45c782394dfa85e5
MD5sum: ae8baa9f6c6a172a3b127af1e6675046
Description: utilities for the syslinux bootloaders
 SYSLINUX is a suite of lightweight bootloaders, currently supporting DOS FAT
 filesystems (SYSLINUX), Linux ext2/ext3 filesystems (EXTLINUX), PXE network
 booting (PXELINUX), or bootable "El Torito" ISO 9660 CD-ROMs (ISOLINUX). It
 also includes a tool, MEMDISK, which loads legacy operating systems (such as
 DOS) from these media.

"""}},
            "hardy-updates":
            {"restricted":
             {"amd64": """""",
              "i386": """"""},
             "main":
             {"amd64": """Package: rebuildd
Version: 0.3.5
Architecture: all
Maintainer: Julien Danjou <acid@debian.org>
Installed-Size: 312
Depends: python (>= 2.5), python-support (>= 0.7.1), lsb-base,\
 python-sqlobject, python-apt
Recommends: pbuilder, python-gdchart2, python-webpy
Suggests: cowdancer
Priority: extra
Section: devel
Filename: pool/main/r/rebuildd/rebuildd_0.3.5_all.deb
Size: 24652
SHA1: 5446cd5c8a29212b403214884cae96f14824a573
MD5sum: 92e81240c2caf286ad103e44dcdc44e1
Description: build daemon aiming at rebuilding Debian packages
 This software allows you to manage a set of jobs. Each job is a package
 rebuilding task. Rebuilding is done by pbuilder (or cowbuilder if you want),
 or anything else, since everything is customizable via configuration file.
 It can also send build logs by email, event each log can be sent to a\
 different
 email address.
 .
 rebuildd is multi-threaded, so you can run multiple build jobs in parallel.
 It is also administrable via a telnet interface. A Web interface is also
 embedded so you can see your jobs queue and watch log file in real-time in\
 your
 browser.
 .
 rebuildd is designed to be run on multiple hosts even with different
 architecture set, and to parallelize the rebuild tasks.

""",
              "i386": """Package: rebuildd
Version: 0.3.5
Architecture: all
Maintainer: Julien Danjou <acid@debian.org>
Installed-Size: 312
Depends: python (>= 2.5), python-support (>= 0.7.1), lsb-base,\
 python-sqlobject, python-apt
Recommends: pbuilder, python-gdchart2, python-webpy
Suggests: cowdancer
Priority: extra
Section: devel
Filename: pool/main/r/rebuildd/rebuildd_0.3.5_all.deb
Size: 24652
SHA1: 5446cd5c8a29212b403214884cae96f14824a573
MD5sum: 92e81240c2caf286ad103e44dcdc44e1
Description: build daemon aiming at rebuilding Debian packages
 This software allows you to manage a set of jobs. Each job is a package
 rebuilding task. Rebuilding is done by pbuilder (or cowbuilder if you want),
 or anything else, since everything is customizable via configuration file.
 It can also send build logs by email, event each log can be sent to a\
 different
 email address.
 .
 rebuildd is multi-threaded, so you can run multiple build jobs in parallel.
 It is also administrable via a telnet interface. A Web interface is also
 embedded so you can see your jobs queue and watch log file in real-time in\
 your
 browser.
 .
 rebuildd is designed to be run on multiple hosts even with different
 architecture set, and to parallelize the rebuild tasks.

"""}}}


def create_deb(target_dir, pkg_name, pkg_data):
    """Create a Debian package in the specified C{target_dir}."""
    path = os.path.join(target_dir, pkg_name)
    data = base64.decodestring(pkg_data)
    create_file(path, data)


def create_simple_repository(target_dir):
    """Create a simple deb-dir repository with in C{target_dir}."""
    create_deb(target_dir, PKGNAME1, PKGDEB1)
    create_deb(target_dir, PKGNAME2, PKGDEB2)
    create_deb(target_dir, PKGNAME3, PKGDEB3)


def create_full_repository(target_dir):
    """
    Create a full APT repository with a dists/ tree rooted at C{target_dir}.
    """

    class Repository(object):

        codename = "hardy"
        variant = "hardy-updates"
        components = ["main", "restricted"]
        archs = ["amd64", "i386"]
        hashes = [HASH4, HASH5, HASH6, HASH7]

        def __init__(self, root):
            self.root = root
            self.url = "file://%s" % self.root

    repository = Repository(target_dir)
    dists_directory = os.path.join(repository.root, "dists")
    os.mkdir(dists_directory)
    for dist in [repository.codename, repository.variant]:
        dist_directory = os.path.join(dists_directory, dist)
        os.mkdir(dist_directory)
        fd = open(os.path.join(dist_directory, "Release"), "w")
        fd.write(RELEASES[dist])
        fd.close()
        for component in repository.components:
            component_directory = os.path.join(dist_directory, component)
            os.mkdir(component_directory)
            for arch in repository.archs:
                arch_directory = os.path.join(component_directory,
                                              "binary-%s" % arch)
                os.mkdir(arch_directory)
                fd = open(os.path.join(arch_directory, "Packages"), "w")
                fd.write(PACKAGES[dist][component][arch])
                fd.close()
                fd = open(os.path.join(arch_directory, "Release"), "w")
                fd.write("""Version: 8.04
Component: %s
Origin: Ubuntu
Label: Ubuntu
Architecture: %s
""" % (component, arch))
                fd.close()
    return repository
