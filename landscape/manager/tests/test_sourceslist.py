import os

from landscape.manager.sourceslist import SourcesList

from landscape.tests.helpers import LandscapeTest, ManagerHelper


class SourcesListTests(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super(SourcesListTests, self).setUp()
        self.sourceslist = SourcesList()
        self.sources_path = self.makeDir()
        self.sourceslist.SOURCES_LIST = os.path.join(self.sources_path,
                                                     "sources.list")
        sources_d = os.path.join(self.sources_path, "sources.list.d")
        os.mkdir(sources_d)
        self.sourceslist.SOURCES_LIST_D = sources_d
        self.manager.add(self.sourceslist)

    def test_comment_sources_list(self):
        """
        When getting a repository message, L{SourcesList} comments the whole
        sources.list file.
        """
        sources = file(self.sourceslist.SOURCES_LIST, "w")
        sources.write("oki\n\ndoki\n#comment\n")
        sources.close()

        self.manager.dispatch_message(
            {"type": "repositories", "repositories": [], "gpg-keys": []})

        self.assertEqual(
            "#oki\n\n#doki\n#comment\n",
            file(self.sourceslist.SOURCES_LIST).read())

