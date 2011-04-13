import glob
import os
import tempfile

from landscape.manager.plugin import ManagerPlugin


class SourcesList(ManagerPlugin):
    """A plugin managing sources.list content."""

    SOURCES_LIST = "/etc/apt/sources.list"
    SOURCES_LIST_D = "/etc/apt/sources.list.d"

    def register(self, registry):
        super(SourcesList, self).register(registry)
        registry.register_message(
            "repositories", self._handle_repositories)

    def _handle_repositories(self, message):
        """
        Handle a list of repositories to set on the machine.

        The format is the following:

        {"sources": [
          {"name": "repository-name",
           "content":
              "deb http://archive.ubuntu.com/ubuntu/ maverick main\n\
              "deb-src http://archive.ubuntu.com/ubuntu/ maverick main"}
          {"name": "repository-name-dev",
           "content":
              "deb http://archive.ubuntu.com/ubuntu/ maverick universe\n\
              "deb-src http://archive.ubuntu.com/ubuntu/ maverick universe"}],
         "gpg-keys": ["-----BEGIN PGP PUBLIC KEY BLOCK-----\n\
                      XXXX
                      -----END PGP PUBLIC KEY BLOCK-----",
                      "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\
                      YYY
                      -----END PGP PUBLIC KEY BLOCK-----"]}
        """
        fd, path = tempfile.mkstemp()
        os.close(fd)
        new_sources = file(path, "w")
        for line in file(self.SOURCES_LIST):
            if not line.strip() or line.startswith("#"):
                new_sources.write(line)
            else:
                new_sources.write("#%s" % line)
        new_sources.close()
        os.rename(path, self.SOURCES_LIST)

        for filename in glob.glob(os.path.join(self.SOURCES_LIST_D, "*.list")):
            os.rename(filename, "%s.save" % filename)

        for source in message["sources"]:
            filename = os.path.join(self.SOURCES_LIST_D,
                                    "landscape-%s.list" % source["name"])
            sources_file = file(filename, "w")
            sources_file.write(source["content"])
            sources_file.close()
