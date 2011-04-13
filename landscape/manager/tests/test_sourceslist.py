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

        sources = file(self.sourceslist.SOURCES_LIST, "w")
        sources.write("\n")
        sources.close()

    def test_comment_sources_list(self):
        """
        When getting a repository message, L{SourcesList} comments the whole
        sources.list file.
        """
        sources = file(self.sourceslist.SOURCES_LIST, "w")
        sources.write("oki\n\ndoki\n#comment\n")
        sources.close()

        self.manager.dispatch_message(
            {"type": "repositories", "sources": [], "gpg-keys": []})

        self.assertEqual(
            "#oki\n\n#doki\n#comment\n",
            file(self.sourceslist.SOURCES_LIST).read())

    def test_rename_sources_list_d(self):
        """
        The sources files in sources.list.d are renamed to .save when a message
        is received.
        """
        sources1 = file(
            os.path.join(self.sourceslist.SOURCES_LIST_D, "file1.list"), "w")
        sources1.write("ok\n")
        sources1.close()

        sources2 = file(
            os.path.join(self.sourceslist.SOURCES_LIST_D,
                         "file2.list.save"), "w")
        sources2.write("ok\n")
        sources2.close()

        self.manager.dispatch_message(
            {"type": "repositories", "sources": [], "gpg-keys": []})

        self.assertFalse(
            os.path.exists(
                os.path.join(self.sourceslist.SOURCES_LIST_D, "file1.list")))

        self.assertTrue(
            os.path.exists(
                os.path.join(self.sourceslist.SOURCES_LIST_D,
                             "file1.list.save")))

        self.assertTrue(
            os.path.exists(
                os.path.join(self.sourceslist.SOURCES_LIST_D,
                             "file2.list.save")))

    def test_create_landscape_sources(self):
        """
        For every sources listed in the sources field of the message,
        C{SourcesList} creates a file with the content in sources.list.d.
        """
        sources = [{"name": "dev", "content": "oki\n"},
                   {"name": "lucid", "content": "doki\n"}]
        self.manager.dispatch_message(
            {"type": "repositories", "sources": sources, "gpg-keys": []})

        dev_file = os.path.join(self.sourceslist.SOURCES_LIST_D,
                                "landscape-dev.list")
        self.assertTrue(os.path.exists(dev_file))
        self.assertEqual("oki\n", file(dev_file).read())

        lucid_file = os.path.join(self.sourceslist.SOURCES_LIST_D,
                                  "landscape-lucid.list")
        self.assertTrue(os.path.exists(lucid_file))
        self.assertEqual("doki\n", file(lucid_file).read())
