import os
from unittest import mock

from twisted.internet.defer import Deferred
from twisted.internet.defer import succeed

from landscape.client.manager.aptsources import AptSources
from landscape.client.manager.plugin import FAILED
from landscape.client.manager.plugin import SUCCEEDED
from landscape.client.package.reporter import find_reporter_command
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import ManagerHelper


class FakeStatResult:
    def __init__(self, st_mode, st_uid, st_gid):
        self.st_mode = st_mode
        self.st_uid = st_uid
        self.st_gid = st_gid


class AptSourcesTests(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()
        self.sourceslist = AptSources()
        self.sources_path = self.makeDir()
        self.sourceslist.SOURCES_LIST = os.path.join(
            self.sources_path,
            "sources.list",
        )
        sources_d = os.path.join(self.sources_path, "sources.list.d")
        os.mkdir(sources_d)
        self.sourceslist.SOURCES_LIST_D = sources_d
        self.manager.add(self.sourceslist)

        with open(self.sourceslist.SOURCES_LIST, "w") as sources:
            sources.write("\n")

        service = self.broker_service
        service.message_store.set_accepted_types(["operation-result"])

        self.sourceslist._run_process = lambda *args, **kwargs: succeed(None)
        self.log_helper.ignore_errors(".*")

    def test_replace_sources_list(self):
        """
        When getting a repository message, AptSources replaces the
        sources.list file.
        """
        with open(self.sourceslist.SOURCES_LIST, "w") as sources:
            sources.write("oki\n\ndoki\n#comment\n # other comment\n")

        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": [{"name": "bla", "content": b""}],
                "gpg-keys": [],
                "operation-id": 1,
            },
        )

        with open(self.sourceslist.SOURCES_LIST) as sources:
            self.assertEqual(
                "# Landscape manages repositories for this computer\n"
                "# Original content of sources.list can be found in "
                "sources.list.save\n",
                sources.read(),
            )

    def test_save_sources_list(self):
        """
        When getting a repository message, AptSources saves a copy of the
        sources.list file.
        """
        with open(self.sourceslist.SOURCES_LIST, "w") as sources:
            sources.write("oki\n\ndoki\n#comment\n # other comment\n")

        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": [{"name": "bla", "content": b""}],
                "gpg-keys": [],
                "operation-id": 1,
            },
        )

        saved_sources_path = f"{self.sourceslist.SOURCES_LIST}.save"
        self.assertTrue(os.path.exists(saved_sources_path))
        with open(saved_sources_path) as saved_sources:
            self.assertEqual(
                "oki\n\ndoki\n#comment\n # other comment\n",
                saved_sources.read(),
            )

    def test_existing_saved_sources_list(self):
        """
        When getting a repository message, AptSources saves a copy of the
        sources.list file, only if a previously saved copy doesn't exist
        """
        with open(self.sourceslist.SOURCES_LIST, "w") as sources:
            sources.write("oki\n\ndoki\n#comment\n # other comment\n")

        saved_sources_path = f"{self.sourceslist.SOURCES_LIST}.save"
        with open(saved_sources_path, "w") as saved_sources:
            saved_sources.write("original content\n")

        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": [{"name": "bla", "content": b""}],
                "gpg-keys": [],
                "operation-id": 1,
            },
        )

        self.assertTrue(os.path.exists(saved_sources_path))
        with open(saved_sources_path) as saved_sources:
            self.assertEqual("original content\n", saved_sources.read())

    def test_sources_list_unicode(self):
        """
        When receiving apt-sources-replace, client correctly also handles
        unicode content correctly.
        """
        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": [{"name": "bla", "content": "fancy content"}],
                "gpg-keys": [],
                "operation-id": 1,
            },
        )

        saved_sources_path = os.path.join(
            self.sourceslist.SOURCES_LIST_D,
            "landscape-bla.list",
        )
        self.assertTrue(os.path.exists(saved_sources_path))
        with open(saved_sources_path, "rb") as saved_sources:
            self.assertEqual(b"fancy content", saved_sources.read())

    def test_restore_sources_list(self):
        """
        When getting a repository message without sources, AptSources
        restores the previous contents of the sources.list file.
        """
        saved_sources_path = f"{self.sourceslist.SOURCES_LIST}.save"
        with open(saved_sources_path, "w") as old_sources:
            old_sources.write("original content\n")

        with open(self.sourceslist.SOURCES_LIST, "w") as sources:
            sources.write("oki\n\ndoki\n#comment\n # other comment\n")

        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": [],
                "gpg-keys": [],
                "operation-id": 1,
            },
        )

        with open(self.sourceslist.SOURCES_LIST) as sources:
            self.assertEqual("original content\n", sources.read())

    def test_sources_list_permissions(self):
        """
        When getting a repository message, L{AptSources} keeps sources.list
        permissions.
        """
        with open(self.sourceslist.SOURCES_LIST, "w") as sources:
            sources.write("oki\n\ndoki\n#comment\n # other comment\n")

        # change file mode from default to check it's restored
        os.chmod(self.sourceslist.SOURCES_LIST, 0o400)
        sources_stat_orig = os.stat(self.sourceslist.SOURCES_LIST)

        fake_stats = FakeStatResult(
            st_mode=sources_stat_orig.st_mode,
            st_uid=30,
            st_gid=30,
        )

        orig_stat = os.stat

        def mocked_stat(filename):
            if filename.endswith("sources.list"):
                return fake_stats
            return orig_stat(filename)

        _mock_stat = mock.patch("os.stat", side_effect=mocked_stat)
        _mock_chown = mock.patch("os.chown")
        with _mock_stat as mock_stat, _mock_chown as mock_chown:
            self.manager.dispatch_message(
                {
                    "type": "apt-sources-replace",
                    "sources": [{"name": "bla", "content": b""}],
                    "gpg-keys": [],
                    "operation-id": 1,
                },
            )

            service = self.broker_service
            self.assertMessages(
                service.message_store.get_pending_messages(),
                [
                    {
                        "type": "operation-result",
                        "status": SUCCEEDED,
                        "operation-id": 1,
                    },
                ],
            )

            mock_stat.assert_any_call(self.sourceslist.SOURCES_LIST)
            mock_chown.assert_any_call(
                self.sourceslist.SOURCES_LIST,
                fake_stats.st_uid,
                fake_stats.st_gid,
            )

        sources_stat_after = os.stat(self.sourceslist.SOURCES_LIST)
        self.assertEqual(sources_stat_orig.st_mode, sources_stat_after.st_mode)

    def test_random_failures(self):
        """
        If a failure happens during the manipulation of sources, the activity
        is reported as FAILED with the error message.
        """

        def buggy_source_handler(*args):
            raise RuntimeError("foo")

        self.sourceslist._handle_sources = buggy_source_handler

        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": [{"name": "bla", "content": b""}],
                "gpg-keys": [],
                "operation-id": 1,
            },
        )

        msg = "RuntimeError: foo"
        service = self.broker_service
        self.assertMessages(
            service.message_store.get_pending_messages(),
            [
                {
                    "type": "operation-result",
                    "result-text": msg,
                    "status": FAILED,
                    "operation-id": 1,
                },
            ],
        )

    def test_renames_sources_list_d(self):
        """
        The sources files (.list, .sources) in sources.list.d
        are renamed to .save when a message is received
        if config says to manage them, which is the default.
        """
        FILE_1_LIST = os.path.join(
            self.sourceslist.SOURCES_LIST_D, "file1.list"
        )

        FILE_2_SOURCES = os.path.join(
            self.sourceslist.SOURCES_LIST_D, "file2.sources"
        )
        with open(
            FILE_1_LIST,
            "w",
        ) as source1:
            source1.write("ok\n")

        with open(
            FILE_2_SOURCES,
            "w",
        ) as source2:
            source2.write("ok\n")

        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": [],
                "gpg-keys": [],
                "operation-id": 1,
            },
        )

        self.assertFalse(
            os.path.exists(FILE_1_LIST),
        )

        self.assertFalse(os.path.exists(FILE_2_SOURCES))

        self.assertTrue(
            os.path.exists(f"{FILE_1_LIST}.save"),
        )

        self.assertTrue(
            os.path.exists(f"{FILE_2_SOURCES}.save"),
        )

    def test_does_not_rename_sources_list_d(self):
        """
        The sources files (.list, .sources) in sources.list.d
        are not renamed to .save when a message is received
        if config says not to manage them
        """
        FILE_3_LIST = os.path.join(
            self.sourceslist.SOURCES_LIST_D, "file3.list"
        )

        FILE_4_SOURCES = os.path.join(
            self.sourceslist.SOURCES_LIST_D, "file4.sources"
        )
        with open(
            FILE_3_LIST,
            "w",
        ) as source3:
            source3.write("ok\n")
        with open(
            FILE_4_SOURCES,
            "w",
        ) as source4:
            source4.write("ok\n")

        self.manager.config.manage_sources_list_d = False
        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": [],
                "gpg-keys": [],
                "operation-id": 1,
            },
        )

        self.assertTrue(
            os.path.exists(FILE_3_LIST),
        )

        self.assertTrue(
            os.path.exists(FILE_4_SOURCES),
        )

        self.assertFalse(
            os.path.exists(f"{FILE_3_LIST}.save"),
        )

        self.assertFalse(
            os.path.exists(f"{FILE_4_SOURCES}.save"),
        )

    def test_create_landscape_sources(self):
        """
        For every sources listed in the sources field of the message,
        C{AptSources} creates a file with the content in sources.list.d.
        """
        sources = [
            {"name": "dev", "content": b"oki\n"},
            {"name": "lucid", "content": b"doki\n"},
        ]
        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": sources,
                "gpg-keys": [],
                "operation-id": 1,
            },
        )

        dev_file = os.path.join(
            self.sourceslist.SOURCES_LIST_D,
            "landscape-dev.list",
        )
        self.assertTrue(os.path.exists(dev_file))
        with open(dev_file) as file:
            result = file.read()
        self.assertEqual("oki\n", result)

        lucid_file = os.path.join(
            self.sourceslist.SOURCES_LIST_D,
            "landscape-lucid.list",
        )
        self.assertTrue(os.path.exists(lucid_file))
        with open(lucid_file) as file:
            result = file.read()
        self.assertEqual("doki\n", result)

    def test_import_gpg_keys(self):
        """
        C{AptSources} runs a process with apt-key for every keys in the
        message.
        """

        self.sourceslist.TRUSTED_GPG_D = self.makeDir()

        gpg_keys = ["key1", "key2"]
        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": [],
                "gpg-keys": gpg_keys,
                "operation-id": 1,
            },
        )

        keys = []
        gpg_dirpath = self.sourceslist.TRUSTED_GPG_D
        for filename in os.listdir(gpg_dirpath):
            filepath = os.path.join(gpg_dirpath, filename)
            with open(filepath, "r") as fh:
                keys.append(fh.read())

        self.assertCountEqual(keys, gpg_keys)

    def test_run_reporter(self):
        """
        After receiving a message, L{AptSources} triggers a reporter run to
        have the new packages reported to the server.
        """
        deferred = Deferred()

        def _run_process(command, args, env={}, path=None, uid=None, gid=None):
            self.assertEqual(
                find_reporter_command(self.manager.config),
                command,
            )
            self.assertEqual(
                [
                    "--force-apt-update",
                    f"--config={self.manager.config.config}",
                ],
                args,
            )
            deferred.callback(("ok", "", 0))
            return deferred

        self.sourceslist._run_process = _run_process

        self.manager.dispatch_message(
            {
                "type": "apt-sources-replace",
                "sources": [],
                "gpg-keys": [],
                "operation-id": 1,
            },
        )

        return deferred

    def test_run_reporter_snap(self):
        """After receiving a message, `AptSources` in a snap triggers a
        reporter run as root to have the new packages reported to the server.
        """
        deferred = Deferred()

        def _run_process(command, args, env={}, path=None, uid=None, gid=None):
            self.assertEqual(
                find_reporter_command(self.manager.config),
                command,
            )
            self.assertEqual(
                [
                    "--force-apt-update",
                    f"--config={self.manager.config.config}",
                ],
                args,
            )
            self.assertEqual(uid, 0)
            self.assertEqual(gid, 0)
            deferred.callback(("ok", "", 0))
            return deferred

        self.sourceslist._run_process = _run_process

        with mock.patch.multiple(
            "landscape.client.manager.aptsources",
            USER="root",
            GROUP="root",
        ):
            with mock.patch("os.getuid") as getuid:
                getuid.return_value = 0
                self.manager.dispatch_message(
                    {
                        "type": "apt-sources-replace",
                        "sources": [],
                        "gpg-keys": [],
                        "operation-id": 1,
                    },
                )

        return deferred
