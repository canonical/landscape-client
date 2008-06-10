from string import Template
import pwd
import grp
import os


class BootstrapList(object):

    def __init__(self, bootstraps):
        self._bootstraps = bootstraps

    def bootstrap(self, **vars):
        for bootstrap in self._bootstraps:
            bootstrap.bootstrap(**vars)


class BootstrapPath(object):

    def __init__(self, path, username=None, group=None, mode=None):
        self.path = path
        self.username = username
        self.group = group
        self.mode = mode

    def _create(self, path):
        pass

    def bootstrap(self, **vars):
        path = Template(self.path).substitute(**vars)
        self._create(path)

        if self.mode is not None:
            os.chmod(path, self.mode)

        if os.getuid() == 0:
            if self.username is not None:
                uid = pwd.getpwnam(self.username).pw_uid
            else:
                uid = -1

            if self.group is not None:
                gid = grp.getgrnam(self.group).gr_gid
            else:
                gid = -1

            if uid != -1 or gid != -1:
                os.chown(path, uid, gid)


class BootstrapFile(BootstrapPath):

    def _create(self, path):
        open(path, "a").close()


class BootstrapDirectory(BootstrapPath):

    def _create(self, path):
        try:
            os.makedirs(path)
        except OSError:
            if not os.path.isdir(path):
                raise
