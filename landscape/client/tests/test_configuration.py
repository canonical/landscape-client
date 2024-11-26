import os
import textwrap
import unittest
from unittest import mock

from twisted.internet.defer import succeed

from landscape.client import GROUP
from landscape.client import USER
from landscape.client.broker.registration import Identity
from landscape.client.broker.tests.helpers import BrokerConfigurationHelper
from landscape.client.configuration import actively_registered
from landscape.client.configuration import bootstrap_tree
from landscape.client.configuration import ConfigurationError
from landscape.client.configuration import EXIT_NOT_REGISTERED
from landscape.client.configuration import get_secure_id
from landscape.client.configuration import ImportOptionError
from landscape.client.configuration import LandscapeSetupConfiguration
from landscape.client.configuration import LandscapeSetupScript
from landscape.client.configuration import main
from landscape.client.configuration import print_text
from landscape.client.configuration import prompt_yes_no
from landscape.client.configuration import registration_info_text
from landscape.client.configuration import registration_sent
from landscape.client.configuration import restart_client
from landscape.client.configuration import set_secure_id
from landscape.client.configuration import setup
from landscape.client.configuration import show_help
from landscape.client.configuration import store_public_key_data
from landscape.client.registration import RegistrationInfo
from landscape.client.serviceconfig import ServiceConfigException
from landscape.client.tests.helpers import LandscapeTest
from landscape.lib.compat import ConfigParser
from landscape.lib.compat import StringIO
from landscape.lib.fetch import HTTPCodeError
from landscape.lib.fetch import PyCurlError
from landscape.lib.fs import read_binary_file
from landscape.lib.persist import Persist
from landscape.lib.testing import EnvironSaverHelper


class LandscapeConfigurationTest(LandscapeTest):
    def get_config(self, args, data_path=None):
        if data_path is None:
            data_path = os.path.join(self.makeDir(), "client")

        if "--config" not in args and "-c" not in args:
            filename = self.makeFile(
                """
[client]
url = https://landscape.canonical.com/message-system
""",
            )
            args.extend(["--config", filename, "--data-path", data_path])
        config = LandscapeSetupConfiguration()
        config.load(args)
        return config


class PrintTextTest(LandscapeTest):
    @mock.patch("sys.stdout", new_callable=StringIO)
    def test_default(self, stdout):
        print_text("Hi!")
        self.assertEqual("Hi!\n", stdout.getvalue())

    @mock.patch("sys.stderr", new_callable=StringIO)
    def test_error(self, stderr):
        print_text("Hi!", error=True)
        self.assertEqual("Hi!\n", stderr.getvalue())

    @mock.patch("sys.stdout", new_callable=StringIO)
    def test_end(self, stdout):
        print_text("Hi!", "END")
        self.assertEqual("Hi!END", stdout.getvalue())


class PromptYesNoTest(unittest.TestCase):
    def test_prompt_yes_no(self):
        """
        prompt_yes_no prompts a question and returns a boolean with the answer.
        """
        comparisons = [
            ("Y", True),
            ("y", True),
            ("yEs", True),
            ("YES", True),
            ("n", False),
            ("N", False),
            ("No", False),
            ("no", False),
            ("", True),
        ]

        for input_string, result in comparisons:
            with mock.patch(
                "landscape.client.configuration.input",
                return_value=input_string,
            ) as mock_input:
                prompt_yes_no("Foo")
            mock_input.assert_called_once_with("Foo [Y/n]: ")

    @mock.patch("landscape.client.configuration.input", return_value="")
    def test_prompt_yes_no_default(self, mock_input):
        self.assertFalse(prompt_yes_no("Foo", default=False))
        mock_input.assert_called_once_with("Foo [y/N]: ")

    @mock.patch("landscape.client.configuration.input", side_effect=("x", "n"))
    @mock.patch("landscape.client.configuration.show_help")
    def test_prompt_yes_no_invalid(self, mock_show_help, mock_input):
        self.assertFalse(prompt_yes_no("Foo"))
        mock_show_help.assert_called_once_with("Invalid input.")
        calls = [mock.call("Foo [Y/n]: "), mock.call("Foo [Y/n]: ")]
        mock_input.assert_has_calls(calls)


class ShowHelpTest(unittest.TestCase):
    @mock.patch("landscape.client.configuration.print_text")
    def test_show_help(self, mock_print_text):
        show_help("\n\n \n  Hello  \n  \n  world!  \n \n\n")
        mock_print_text.assert_called_once_with("\nHello\n\nworld!\n")


class LandscapeSetupScriptTest(LandscapeTest):
    def setUp(self):
        super().setUp()
        self.config_filename = self.makeFile()

        class MyLandscapeSetupConfiguration(LandscapeSetupConfiguration):
            default_config_filenames = [self.config_filename]

        self.config = MyLandscapeSetupConfiguration()
        self.script = LandscapeSetupScript(self.config)

    @mock.patch("landscape.client.configuration.input", return_value="Desktop")
    def test_prompt_simple(self, mock_input):
        self.script.prompt("computer_title", "Message")
        mock_input.assert_called_once_with("Message: ")
        self.assertEqual(self.config.computer_title, "Desktop")

    @mock.patch("landscape.client.configuration.input", return_value="")
    def test_prompt_with_default(self, mock_input):
        self.config.computer_title = "default"
        self.script.prompt("computer_title", "Message")

        mock_input.assert_called_once_with("Message [default]: ")
        self.assertEqual(self.config.computer_title, "default")

    @mock.patch(
        "landscape.client.configuration.input",
        side_effect=("", "Desktop"),
    )
    @mock.patch("landscape.client.configuration.show_help")
    def test_prompt_with_required(self, mock_show_help, mock_input):
        self.script.prompt("computer_title", "Message", True)
        mock_show_help.assert_called_once_with(
            "This option is required to configure Landscape.",
        )

        calls = [mock.call("Message: "), mock.call("Message: ")]
        mock_input.assert_has_calls(calls)

        self.assertEqual(self.config.computer_title, "Desktop")

    @mock.patch("landscape.client.configuration.input", return_value="")
    def test_prompt_with_required_and_default(self, mock_input):
        self.config.computer_title = "Desktop"
        self.script.prompt("computer_title", "Message", True)
        mock_input.assert_called_once_with("Message [Desktop]: ")
        self.assertEqual(self.config.computer_title, "Desktop")

    @mock.patch(
        "landscape.client.configuration.input",
        return_value="landscape.hello.com",
    )
    @mock.patch(
        "landscape.client.configuration.prompt_yes_no",
        return_value=True,
    )
    @mock.patch("landscape.client.configuration.show_help")
    def test_prompt_landscape_edition(
        self,
        mock_help,
        prompt_yes_no,
        mock_input,
    ):
        self.script.query_landscape_edition()
        self.script.query_account_name()
        self.assertEqual(
            self.config.ping_url,
            "http://landscape.hello.com/ping",
        )
        self.assertEqual(
            self.config.url,
            "https://landscape.hello.com/message-system",
        )
        self.assertEqual(self.config.account_name, "standalone")

    @mock.patch(
        "landscape.client.configuration.input",
        return_value="http://landscape.hello.com",
    )
    @mock.patch(
        "landscape.client.configuration.prompt_yes_no",
        return_value=True,
    )
    @mock.patch("landscape.client.configuration.show_help")
    def test_prompt_landscape_edition_strip_http(
        self,
        mock_help,
        prompt_yes_no,
        mock_input,
    ):
        self.script.query_landscape_edition()
        self.assertEqual(
            self.config.ping_url,
            "http://landscape.hello.com/ping",
        )
        self.assertEqual(
            self.config.url,
            "https://landscape.hello.com/message-system",
        )

    @mock.patch(
        "landscape.client.configuration.input",
        return_value="https://landscape.hello.com",
    )
    @mock.patch(
        "landscape.client.configuration.prompt_yes_no",
        return_value=True,
    )
    @mock.patch("landscape.client.configuration.show_help")
    def test_prompt_landscape_edition_strip_https(
        self,
        mock_help,
        prompt_yes_no,
        mock_input,
    ):
        self.script.query_landscape_edition()
        self.assertEqual(
            self.config.ping_url,
            "http://landscape.hello.com/ping",
        )
        self.assertEqual(
            self.config.url,
            "https://landscape.hello.com/message-system",
        )

    @mock.patch(
        "landscape.client.configuration.input",
        return_value="landscape.hello.com",
    )
    @mock.patch(
        "landscape.client.configuration.prompt_yes_no",
        return_value=False,
    )
    @mock.patch("landscape.client.configuration.show_help")
    def test_prompt_landscape_edition_saas(
        self,
        mock_help,
        prompt_yes_no,
        mock_input,
    ):
        self.script.query_landscape_edition()
        self.assertEqual(
            self.config.ping_url,
            "http://landscape.canonical.com/ping",
        )
        self.assertEqual(
            self.config.url,
            "https://landscape.canonical.com/message-system",
        )

    @mock.patch("landscape.client.configuration.input", return_value="Yay")
    def test_prompt_for_unknown_variable(self, mock_input):
        """
        It should be possible to prompt() defining a variable that doesn't
        'exist' in the configuration, and still have it set there.
        """
        self.assertFalse(hasattr(self.config, "variable"))

        self.script.prompt("variable", "Variable")
        mock_input.assert_called_once_with("Variable: ")
        self.assertEqual(self.config.variable, "Yay")

    @mock.patch(
        "landscape.client.configuration.getpass.getpass",
        side_effect=("password", "password"),
    )
    def test_password_prompt_simple_matching(self, mock_getpass):
        self.script.password_prompt("registration_key", "Password")
        calls = [mock.call("Password: "), mock.call("Please confirm: ")]
        mock_getpass.assert_has_calls(calls)
        self.assertEqual(self.config.registration_key, "password")

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch(
        "landscape.client.configuration.getpass.getpass",
        side_effect=("password", "", "password", "password"),
    )
    def test_password_prompt_simple_non_matching(
        self,
        mock_getpass,
        mock_show_help,
    ):
        self.script.password_prompt("registration_key", "Password")

        calls = [
            mock.call("Password: "),
            mock.call("Please confirm: "),
            mock.call("Password: "),
            mock.call("Please confirm: "),
        ]
        mock_getpass.assert_has_calls(calls)
        mock_show_help.assert_called_once_with("Keys must match.")
        self.assertEqual(self.config.registration_key, "password")

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch(
        "landscape.client.configuration.getpass.getpass",
        side_effect=("", "password", "password"),
    )
    def test_password_prompt_simple_matching_required(
        self,
        mock_getpass,
        mock_show_help,
    ):
        self.script.password_prompt("registration_key", "Password", True)

        calls = [
            mock.call("Password: "),
            mock.call("Password: "),
            mock.call("Please confirm: "),
        ]
        mock_getpass.assert_has_calls(calls)
        mock_show_help.assert_called_once_with(
            "This option is required to configure Landscape.",
        )
        self.assertEqual(self.config.registration_key, "password")

    @mock.patch("landscape.client.configuration.input")
    def test_query_computer_title_defined_on_command_line(self, mock_input):
        self.config.load_command_line(["-t", "Computer title"])
        self.script.query_computer_title()
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.show_help")
    def test_query_account_name(self, mock_show_help):
        help_snippet = "You must now specify the name of the Landscape account"
        self.script.prompt = mock.Mock()
        self.script.query_account_name()
        self.script.prompt.assert_called_once_with(
            "account_name",
            "Account name",
            True,
        )
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

        self.script.query_account_name()

    @mock.patch("landscape.client.configuration.input")
    def test_query_account_name_defined_on_command_line(self, mock_input):
        self.config.load_command_line(["-a", "Account name"])
        self.script.query_account_name()
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.show_help")
    def test_query_registration_key(self, mock_show_help):
        help_snippet = "A registration key may be"
        self.script.password_prompt = mock.Mock()
        self.script.query_registration_key()
        self.script.password_prompt.assert_called_once_with(
            "registration_key",
            "(Optional) Registration Key",
        )
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.getpass.getpass")
    def test_query_registration_key_defined_on_command_line(
        self,
        mock_getpass,
    ):
        self.config.load_command_line(["-p", "shared-secret"])
        self.script.query_registration_key()
        mock_getpass.assert_not_called()

    @mock.patch("landscape.client.configuration.show_help")
    def test_query_proxies(self, mock_show_help):
        help_snippet = "The Landscape client communicates"
        self.script.prompt = mock.Mock()

        self.script.query_proxies()
        calls = [
            mock.call("http_proxy", "HTTP proxy URL"),
            mock.call("https_proxy", "HTTPS proxy URL"),
        ]
        self.script.prompt.assert_has_calls(calls)
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.input")
    def test_query_proxies_defined_on_command_line(self, mock_input):
        self.config.load_command_line(
            [
                "--http-proxy",
                "localhost:8080",
                "--https-proxy",
                "localhost:8443",
            ],
        )
        self.script.query_proxies()
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.show_help")
    def test_query_http_proxy_defined_on_command_line(self, mock_show_help):
        help_snippet = "The Landscape client communicates"
        self.script.prompt = mock.Mock()

        self.config.load_command_line(["--http-proxy", "localhost:8080"])
        self.script.query_proxies()
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.show_help")
    def test_query_https_proxy_defined_on_command_line(self, mock_show_help):
        help_snippet = "The Landscape client communicates"
        self.script.prompt = mock.Mock()
        self.config.load_command_line(["--https-proxy", "localhost:8443"])
        self.script.query_proxies()
        self.script.prompt.assert_called_once_with(
            "http_proxy",
            "HTTP proxy URL",
        )
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch(
        "landscape.client.configuration.pwd.getpwnam",
        side_effect=(None, None, None, KeyError()),
    )
    def test_query_script_users_on_command_line_with_unknown_user(
        self,
        mock_getpwnam,
    ):
        """
        If several users are provided on the command line, we verify the users
        and raise a ConfigurationError if any are unknown on this system.
        """
        self.config.load_command_line(
            [
                "--script-users",
                "root, nobody, landscape, unknown",
                "--include-manager-plugins",
                "ScriptPlugin",
            ],
        )
        self.assertRaises(ConfigurationError, self.script.query_script_plugin)
        calls = [
            mock.call("root"),
            mock.call("nobody"),
            mock.call("landscape"),
            mock.call("unknown"),
        ]
        mock_getpwnam.assert_has_calls(calls)

    def test_query_script_users_defined_on_command_line_with_all_user(self):
        """
        We shouldn't accept all as a synonym for ALL
        """
        self.config.load_command_line(
            [
                "--script-users",
                "all",
                "--include-manager-plugins",
                "ScriptPlugin",
            ],
        )
        self.assertRaises(ConfigurationError, self.script.query_script_plugin)

    def test_query_script_users_defined_on_command_line_with_ALL_user(  # noqa: E501,N802
        self,
    ):
        """
        ALL is the special marker for all users.
        """
        self.config.load_command_line(
            [
                "--script-users",
                "ALL",
                "--include-manager-plugins",
                "ScriptPlugin",
            ],
        )
        self.script.query_script_plugin()
        self.assertEqual(self.config.script_users, "ALL")

    def test_query_script_users_command_line_with_ALL_and_extra_user(  # noqa: E501,N802
        self,
    ):
        """
        If ALL and additional users are provided as the users on the command
        line, this should raise an appropriate ConfigurationError.
        """
        self.config.load_command_line(
            [
                "--script-users",
                "ALL, kevin",
                "--include-manager-plugins",
                "ScriptPlugin",
            ],
        )
        self.assertRaises(ConfigurationError, self.script.query_script_plugin)

    @mock.patch("landscape.client.configuration.input")
    def test_tags_defined_on_command_line(self, mock_input):
        """
        Tags defined on the command line can be verified by the user.
        """
        self.config.load_command_line(["--tags", "server,london"])
        self.script.query_tags()
        self.assertEqual(self.config.tags, "server,london")
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.input")
    def test_invalid_tags_defined_on_command_line_raises_error(
        self,
        mock_input,
    ):
        """
        Invalid tags on the command line raises a ConfigurationError.
        """
        self.config.load_command_line(["--tags", "<script>alert();</script>"])
        self.assertRaises(ConfigurationError, self.script.query_tags)
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.show_help")
    def test_access_group_not_defined_on_command_line(self, mock_show_help):
        """
        If an access group is not provided, the user should be prompted for it.
        """
        help_snippet = (
            "You may provide an access group for this computer "
            "e.g. webservers."
        )
        self.script.prompt = mock.Mock()
        self.script.query_access_group()
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.input")
    def test_access_group_defined_on_command_line(self, mock_input):
        """
        When an access group is provided on the command line, do not prompt
        the user for it.
        """
        self.config.load_command_line(["--access-group", "webservers"])
        self.script.query_access_group()
        self.assertEqual(self.config.access_group, "webservers")
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.input")
    def test_stagger_defined_on_command_line(self, mock_input):
        self.assertEqual(self.config.stagger_launch, 0.1)
        self.config.load_command_line(["--stagger-launch", "0.5"])
        self.assertEqual(self.config.stagger_launch, 0.5)
        mock_input.assert_not_called()


class BootstrapTreeTest(LandscapeConfigurationTest):
    @mock.patch("os.chmod")
    def test_bootstrap_tree(self, mock_chmod):
        """
        The L{bootstrap_tree} function creates the client dir and
        /annotations.d under it with the correct permissions.
        """
        client_path = self.makeDir()
        annotations_path = os.path.join(client_path, "annotations.d")

        config = self.get_config([], data_path=client_path)
        bootstrap_tree(config)
        mock_chmod.assert_any_call(client_path, 0o755)
        mock_chmod.assert_called_with(annotations_path, 0o755)
        self.assertTrue(os.path.isdir(client_path))
        self.assertTrue(os.path.isdir(annotations_path))


def noop_print(*args, **kws):
    """A print that doesn't do anything."""
    pass


class ConfigurationFunctionsTest(LandscapeConfigurationTest):

    helpers = [EnvironSaverHelper]

    def setUp(self):
        super().setUp()

        self.mock_getuid = mock.patch("os.getuid", return_value=0).start()
        patches = mock.patch.multiple(
            "landscape.client.configuration",
            bootstrap_tree=mock.DEFAULT,
            init_app_logging=mock.DEFAULT,
            set_secure_id=mock.DEFAULT,
        ).start()
        self.mock_bootstrap_tree = patches["bootstrap_tree"]

        self.addCleanup(mock.patch.stopall)

    def get_content(self, config):
        """Write C{config} to a file and return it's contents as a string."""
        config_file = self.makeFile("")
        original_config = config.config
        try:
            config.config = config_file
            config.write()
            with open(config.config) as fh:
                text = fh.read().strip() + "\n"
            return text
        finally:
            config.config = original_config

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.getpass.getpass")
    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.show_help")
    def test_setup(self, mock_help, mock_input, mock_getpass, mock_print_text):
        filename = self.makeFile(
            "[client]\n"
            "computer_title = Old Title\n"
            "account_name = Old Name\n"
            "registration_key = Old Password\n"
            "http_proxy = http://old.proxy\n"
            "https_proxy = https://old.proxy\n"
            "url = http://url\n",
        )

        def side_effect_input(prompt):
            fixtures = {
                "[Old Title]": "New Title",
                "[Old Name]": "New Name",
                "[http://old.proxy]": "http://new.proxy",
                "[https://old.proxy]": "https://new.proxy",
                "Will you be using your own "
                "Self-Hosted Landscape installation? [y/N]": "n",
            }
            for key, value in fixtures.items():
                if key in prompt:
                    return value
            raise KeyError(f"Couldn't find answer for {prompt}")

        def side_effect_getpass(prompt):
            fixtures = {
                "(Optional) Registration Key:": "New Password",
                "Please confirm:": "New Password",
            }
            for key, value in fixtures.items():
                if key in prompt:
                    return value
            raise KeyError(f"Couldn't find answer for {prompt}")

        mock_input.side_effect = side_effect_input
        mock_getpass.side_effect = side_effect_getpass

        config = self.get_config(["--no-start", "--config", filename])
        setup(config)
        self.assertEqual(type(config), LandscapeSetupConfiguration)

        # Reload it to ensure it was written down.
        config.reload()

        self.assertEqual(
            "sudo landscape-config "
            "--account-name 'New Name' "
            "--registration-key HIDDEN "
            "--https-proxy https://new.proxy "
            "--http-proxy http://new.proxy",
            mock_help.mock_calls[-1].args[0],
        )

        proxy_arg = mock_help.mock_calls[-3].args[0]
        self.assertIn("https://new.proxy", proxy_arg)
        self.assertIn("http://new.proxy", proxy_arg)

        summary_arg = mock_help.mock_calls[-4].args[0]
        self.assertIn("Computer's Title: New Title", summary_arg)
        self.assertIn("Account Name: New Name", summary_arg)
        self.assertIn("Landscape FQDN: landscape.canonical.com", summary_arg)
        self.assertIn("Registration Key: True", summary_arg)

        self.assertEqual(config.computer_title, "New Title")
        self.assertEqual(config.account_name, "New Name")
        self.assertEqual(config.registration_key, "New Password")
        self.assertEqual(config.http_proxy, "http://new.proxy")
        self.assertEqual(config.https_proxy, "https://new.proxy")
        self.assertEqual(config.include_manager_plugins, "")

    @mock.patch("landscape.client.configuration.IS_SNAP", "1")
    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.getpass.getpass")
    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.show_help")
    def test_setup_on_the_snap_version(
        self,
        mock_help,
        mock_input,
        mock_getpass,
        mock_print_text,
    ):
        filename = self.makeFile(
            "[client]\n"
            "computer_title = Old Title\n"
            "account_name = Old Name\n"
            "registration_key = Old Password\n"
            "http_proxy = http://old.proxy\n"
            "https_proxy = https://old.proxy\n"
            "url = http://url\n",
        )

        def side_effect_input(prompt):
            fixtures = {
                "[Old Title]": "New Title",
                "[Old Name]": "New Name",
                "[http://old.proxy]": "http://new.proxy",
                "[https://old.proxy]": "https://new.proxy",
                "Will you be using your own "
                "Self-Hosted Landscape installation? [y/N]": "n",
            }
            for key, value in fixtures.items():
                if key in prompt:
                    return value

        def side_effect_getpass(prompt):
            fixtures = {
                "(Optional) Registration Key:": "New Password",
                "Please confirm:": "New Password",
            }
            for key, value in fixtures.items():
                if key in prompt:
                    return value

        mock_input.side_effect = side_effect_input
        mock_getpass.side_effect = side_effect_getpass

        config = self.get_config(["--no-start", "--config", filename])
        setup(config)

        self.assertEqual(
            "sudo landscape-client.config "
            "--account-name 'New Name' "
            "--registration-key HIDDEN "
            "--https-proxy https://new.proxy "
            "--http-proxy http://new.proxy",
            mock_help.mock_calls[-1].args[0],
        )

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_silent_setup(self, mock_serviceconfig):
        """
        Only command-line options are used in silent mode.
        """
        config = self.get_config(["--silent", "-a", "account", "-t", "rex"])
        setup(config)
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)
        self.assertConfigEqual(
            self.get_content(config),
            f"""\
[client]
computer_title = rex
data_path = {config.data_path}
account_name = account
url = https://landscape.canonical.com/message-system
""",
        )

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_silent_setup_no_register(self, mock_serviceconfig):
        """
        Called with command line options to write a config file but no
        registration or validation of parameters is attempted.
        """
        config = self.get_config(["--silent", "--no-start"])
        setup(config)
        self.assertConfigEqual(
            self.get_content(config),
            f"""\
[client]
data_path = {config.data_path}
url = https://landscape.canonical.com/message-system
""",
        )

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_silent_setup_no_register_with_default_preseed_params(
        self,
        mock_serviceconfig,
    ):
        """
        Make sure that the configuration can be used to write the
        configuration file after a fresh install.
        """
        args = [
            "--silent",
            "--no-start",
            "--computer-title",
            "",
            "--account-name",
            "",
            "--registration-key",
            "",
            "--url",
            "https://landscape.canonical.com/message-system",
            "--exchange-interval",
            "900",
            "--urgent-exchange-interval",
            "60",
            "--ping-url",
            "http://landscape.canonical.com/ping",
            "--ping-interval",
            "30",
            "--http-proxy",
            "",
            "--https-proxy",
            "",
            "--tags",
            "",
        ]
        config = self.get_config(args)
        setup(config)
        self.assertConfigEqual(
            self.get_content(config),
            "[client]\n"
            "http_proxy = \n"
            "tags = \n"
            f"data_path = {config.data_path}\n"
            "registration_key = \n"
            "account_name = \n"
            "computer_title = \n"
            "https_proxy = \n"
            "url = https://landscape.canonical.com/message-system\n"
            "exchange_interval = 900\n"
            "ping_interval = 30\n"
            "ping_url = http://landscape.canonical.com/ping\n"
            "urgent_exchange_interval = 60\n",
        )

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_silent_setup_unicode_computer_title(self, mock_serviceconfig):
        """
        Setup accepts a non-ascii computer title and registration is
        attempted.
        """
        config = self.get_config(["--silent", "-a", "account", "-t", "mélody"])
        setup(config)
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)
        self.assertConfigEqual(
            self.get_content(config),
            f"""\
[client]
computer_title = mélody
data_path = {config.data_path}
account_name = account
url = https://landscape.canonical.com/message-system
""",
        )

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_silent_setup_without_computer_title(self, mock_serviceconfig):
        """A computer title is required."""
        config = self.get_config(["--silent", "-a", "account"])
        self.assertRaises(ConfigurationError, setup, config)

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_silent_setup_without_account_name(self, mock_serviceconfig):
        """An account name is required."""
        config = self.get_config(["--silent", "-t", "rex"])
        self.assertRaises(ConfigurationError, setup, config)
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)

    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_silent_script_users_imply_script_execution_plugin(
        self,
        mock_serviceconfig,
        mock_input,
    ):
        """
        If C{--script-users} is specified, without C{ScriptExecution} in the
        list of manager plugins, it will be automatically added.
        """
        filename = self.makeFile(
            """
[client]
url = https://localhost:8080/message-system
bus = session
""",
        )

        config = self.get_config(
            [
                "--config",
                filename,
                "--silent",
                "-a",
                "account",
                "-t",
                "rex",
                "--script-users",
                "root, nobody",
            ],
        )
        mock_serviceconfig.restart_landscape.return_value = True
        setup(config)
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)
        mock_input.assert_not_called()
        parser = ConfigParser()
        parser.read(filename)
        self.assertEqual(
            {
                "url": "https://localhost:8080/message-system",
                "bus": "session",
                "computer_title": "rex",
                "include_manager_plugins": "ScriptExecution",
                "script_users": "root, nobody",
                "account_name": "account",
            },
            dict(parser.items("client")),
        )

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_silent_script_users_with_all_user(self, mock_serviceconfig):
        """
        In silent mode, we shouldn't accept invalid users, it should raise a
        configuration error.
        """
        config = self.get_config(
            [
                "--script-users",
                "all",
                "--include-manager-plugins",
                "ScriptPlugin",
                "-a",
                "account",
                "-t",
                "rex",
                "--silent",
            ],
        )
        self.assertRaises(ConfigurationError, setup, config)
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_silent_setup_with_ping_url(self, mock_serviceconfig):
        mock_serviceconfig.restart_landscape.return_value = True
        filename = self.makeFile(
            """
[client]
ping_url = http://landscape.canonical.com/ping
registration_key = shared-secret
log_level = debug
random_key = random_value
""",
        )

        config = self.get_config(
            [
                "--config",
                filename,
                "--silent",
                "-a",
                "account",
                "-t",
                "rex",
                "--ping-url",
                "http://localhost/ping",
            ],
        )
        setup(config)
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)

        parser = ConfigParser()
        parser.read(filename)
        self.assertEqual(
            {
                "log_level": "debug",
                "registration_key": "shared-secret",
                "ping_url": "http://localhost/ping",
                "random_key": "random_value",
                "computer_title": "rex",
                "account_name": "account",
            },
            dict(parser.items("client")),
        )

    @mock.patch("landscape.client.configuration.LandscapeSetupScript")
    def test_setup_with_proxies_from_environment(self, mock_setup_script):
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"

        filename = self.makeFile("[client]\n" "url = http://url\n")

        config = self.get_config(["--no-start", "--config", filename])
        setup(config)

        # Reload it to ensure it was written down.
        config.reload()

        mock_setup_script().run.assert_called_once_with()

        self.assertEqual(config.http_proxy, "http://environ")
        self.assertEqual(config.https_proxy, "https://environ")

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_silent_setup_with_proxies_from_environment(
        self,
        mock_serviceconfig,
    ):
        """
        Only command-line options are used in silent mode.
        """
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"

        filename = self.makeFile(
            """
[client]
registration_key = shared-secret
""",
        )
        config = self.get_config(
            ["--config", filename, "--silent", "-a", "account", "-t", "rex"],
        )
        setup(config)
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)
        parser = ConfigParser()
        parser.read(filename)
        self.assertEqual(
            {
                "registration_key": "shared-secret",
                "http_proxy": "http://environ",
                "https_proxy": "https://environ",
                "computer_title": "rex",
                "account_name": "account",
            },
            dict(parser.items("client")),
        )

    @mock.patch("landscape.client.configuration.LandscapeSetupScript")
    def test_setup_prefers_proxies_from_config_over_environment(
        self,
        mock_setup_script,
    ):
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"

        filename = self.makeFile(
            "[client]\n"
            "http_proxy = http://config\n"
            "https_proxy = https://config\n"
            "url = http://url\n",
        )

        config = self.get_config(["--no-start", "--config", filename])
        setup(config)
        mock_setup_script().run.assert_called_once_with()

        # Reload it to ensure it was written down.
        config.reload()

        self.assertEqual(config.http_proxy, "http://config")
        self.assertEqual(config.https_proxy, "https://config")

    @mock.patch("landscape.client.configuration.sys.exit")
    @mock.patch("landscape.client.configuration.input", return_value="n")
    @mock.patch("landscape.client.configuration.attempt_registration")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_no_registration(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_sys_exit,
    ):
        main(["-c", self.make_working_config()], print=noop_print)
        mock_register.assert_not_called()
        mock_input.assert_called_once_with(
            "\nRequest a new registration for this computer now? [Y/n]: ",
        )

    @mock.patch("landscape.client.configuration.sys.exit")
    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.attempt_registration")
    @mock.patch("landscape.client.configuration.setup")
    def test_skip_registration(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_sys_exit,
    ):
        """
        Registration and input asking user to register is not called
        when flag on
        """
        main(
            ["-c", self.make_working_config(), "--skip-registration"],
            print=noop_print,
        )
        mock_register.assert_not_called()
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.attempt_registration")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_no_registration_silent(self, mock_setup, mock_register):
        """Skip registration works in silent mode"""
        main(
            [
                "-c",
                self.make_working_config(),
                "--skip-registration",
                "--silent",
            ],
            print=noop_print,
        )
        mock_register.assert_not_called()

    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch("landscape.client.configuration.sys.exit")
    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.attempt_registration")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_force_registration_silent(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_sys_exit,
        mock_restart_client,
    ):
        """Force registration works in silent mode"""
        main(
            [
                "-c",
                self.make_working_config(),
                "--force-registration",
                "--silent",
            ],
            print=noop_print,
        )
        mock_restart_client.assert_called_once()
        mock_register.assert_called_once()
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch("landscape.client.configuration.input")
    @mock.patch(
        "landscape.client.configuration.attempt_registration",
        return_value=0,
    )
    @mock.patch("landscape.client.configuration.setup")
    def test_main_register_if_needed_silent(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_restart_client,
    ):
        """Conditional registration works in silent mode"""
        system_exit = self.assertRaises(
            SystemExit,
            main,
            [
                "-c",
                self.make_working_config(),
                "--register-if-needed",
                "--silent",
            ],
        )
        self.assertEqual(0, system_exit.code)
        mock_restart_client.assert_called_once()
        mock_register.assert_called_once()
        mock_input.assert_not_called()

    @mock.patch(
        "landscape.client.configuration.registration_sent",
        return_value=True,
    )
    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.attempt_registration")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_do_not_register_if_not_needed_silent(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_restart_client,
        mock_is_registered,
    ):
        """Conditional registration works in silent mode"""
        system_exit = self.assertRaises(
            SystemExit,
            main,
            [
                "-c",
                self.make_working_config(),
                "--register-if-needed",
                "--silent",
            ],
            print=noop_print,
        )
        self.assertEqual(0, system_exit.code)
        mock_restart_client.assert_called_once()
        mock_register.assert_not_called()
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch(
        "landscape.client.configuration.attempt_registration",
        return_value=0,
    )
    @mock.patch("landscape.client.configuration.setup")
    def test_main_silent(self, mock_setup, mock_register, mock_restart_client):
        """
        In silent mode, the client should register when the registration
        details are changed/set.
        """
        config_filename = self.makeFile(
            "[client]\n"
            "computer_title = Old Title\n"
            "account_name = Old Name\n"
            "registration_key = Old Password\n",
        )

        exception = self.assertRaises(
            SystemExit,
            main,
            ["-c", config_filename, "--silent"],
        )
        self.assertEqual(0, exception.code)
        mock_setup.assert_called_once()
        mock_restart_client.assert_called_once()
        mock_register.assert_called_once()

    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch("landscape.client.configuration.input", return_value="y")
    @mock.patch(
        "landscape.client.configuration.attempt_registration",
        return_value=0,
    )
    @mock.patch("landscape.client.configuration.setup")
    def test_main_user_interaction_success(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_restart_client,
    ):
        """The successful result of register() is communicated to the user."""
        exception = self.assertRaises(
            SystemExit,
            main,
            ["-c", self.make_working_config()],
        )
        self.assertEqual(0, exception.code)
        mock_setup.assert_called_once()
        mock_restart_client.assert_called_once()
        mock_register.assert_called_once()
        mock_input.assert_called_once_with(
            "\nRequest a new registration for this computer now? [Y/n]: ",
        )

    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch("landscape.client.configuration.input", return_value="y")
    @mock.patch(
        "landscape.client.configuration.attempt_registration",
        return_value=2,
    )
    @mock.patch("landscape.client.configuration.setup")
    def test_main_user_interaction_failure(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_restart_client,
    ):
        """The failed result of register() is communicated to the user."""
        exception = self.assertRaises(
            SystemExit,
            main,
            ["-c", self.make_working_config()],
        )
        self.assertEqual(2, exception.code)
        mock_setup.assert_called_once()
        mock_restart_client.assert_called_once()
        mock_register.assert_called_once()
        mock_input.assert_called_once_with(
            "\nRequest a new registration for this computer now? [Y/n]: ",
        )

    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch("landscape.client.configuration.input")
    @mock.patch(
        "landscape.client.configuration.attempt_registration",
        return_value=0,
    )
    @mock.patch("landscape.client.configuration.setup")
    def test_main_user_interaction_success_silent(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_restart_client,
    ):
        """Successful result is communicated to the user even with --silent."""
        exception = self.assertRaises(
            SystemExit,
            main,
            ["--silent", "-c", self.make_working_config()],
        )
        self.assertEqual(0, exception.code)
        mock_setup.assert_called_once()
        mock_restart_client.assert_called_once()
        mock_register.assert_called_once()
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch("landscape.client.configuration.input")
    @mock.patch(
        "landscape.client.configuration.attempt_registration",
        return_value=2,
    )
    @mock.patch("landscape.client.configuration.setup")
    def test_main_user_interaction_failure_silent(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_restart_client,
    ):
        """
        A failure result is communicated to the user even with --silent.
        """
        exception = self.assertRaises(
            SystemExit,
            main,
            ["--silent", "-c", self.make_working_config()],
        )
        self.assertEqual(2, exception.code)
        mock_setup.assert_called_once()
        mock_restart_client.assert_called_once()
        mock_register.assert_called_once()
        mock_input.assert_not_called()

    def make_working_config(self):
        data_path = self.makeFile()
        return self.makeFile(
            "[client]\n"
            "computer_title = Old Title\n"
            "account_name = Old Name\n"
            "registration_key = Old Password\n"
            "http_proxy = http://old.proxy\n"
            "https_proxy = https://old.proxy\n"
            "data_path = {}\n"
            "url = http://url\n".format(data_path),
        )

    @mock.patch("landscape.client.configuration.input", return_value="")
    @mock.patch("landscape.client.configuration.attempt_registration")
    @mock.patch("landscape.client.configuration.LandscapeSetupScript")
    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_register_system_exit(
        self,
        mock_serviceconfig,
        mock_setup_script,
        mock_register,
        mock_input,
    ):
        mock_serviceconfig.is_configured_to_run.return_value = False
        self.assertRaises(
            SystemExit,
            main,
            ["--config", self.make_working_config()],
            print=noop_print,
        )
        mock_serviceconfig.is_configured_to_run.assert_called_once_with()
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)
        mock_serviceconfig.restart_landscape.assert_called_once_with()
        mock_setup_script().run.assert_called_once_with()
        mock_register.assert_called_once()
        mock_input.assert_called_with(
            "\nRequest a new registration for this computer now? [Y/n]: ",
        )

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_errors_from_restart_landscape(
        self,
        mock_serviceconfig,
        mock_print_text,
    ):
        """
        If a ProcessError exception is raised from restart_landscape (because
        the client failed to be restarted), an informative message is printed
        and the script exits.
        """
        mock_serviceconfig.restart_landscape.side_effect = (
            ServiceConfigException("Couldn't restart the Landscape client.")
        )

        config = self.get_config(["--silent", "-a", "account", "-t", "rex"])
        setup(config)
        system_exit = self.assertRaises(SystemExit, restart_client, config)
        self.assertEqual(system_exit.code, 2)
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)
        mock_serviceconfig.restart_landscape.assert_called_once_with()
        mock_print_text.assert_any_call(
            "Couldn't restart the Landscape client.",
            error=True,
        )

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_errors_from_restart_landscape_ok_no_register(
        self,
        mock_serviceconfig,
        mock_print_text,
    ):
        """
        Exit code 0 will be returned if the client fails to be restarted and
        --ok-no-register was passed.
        """
        mock_serviceconfig.restart_landscape.side_effect = (
            ServiceConfigException("Couldn't restart the Landscape client.")
        )

        config = self.get_config(
            ["--silent", "-a", "account", "-t", "rex", "--ok-no-register"],
        )
        setup(config)
        system_exit = self.assertRaises(SystemExit, restart_client, config)
        self.assertEqual(system_exit.code, 0)
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)
        mock_serviceconfig.restart_landscape.assert_called_once_with()
        mock_print_text.assert_any_call(
            "Couldn't restart the Landscape client.",
            error=True,
        )

    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch("landscape.client.configuration.input", return_value="")
    @mock.patch("landscape.client.configuration.attempt_registration")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_with_register(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_restart_client,
    ):
        self.assertRaises(
            SystemExit,
            main,
            ["-c", self.make_working_config()],
            print=noop_print,
        )
        mock_setup.assert_called_once()
        mock_restart_client.assert_called_once()
        mock_register.assert_called_once()
        mock_input.assert_called_once_with(
            "\nRequest a new registration for this computer now? [Y/n]: ",
        )

    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.attempt_registration")
    @mock.patch("landscape.client.configuration.setup")
    def test_register_silent(
        self,
        mock_setup,
        mock_register,
        mock_input,
        mock_restart_client,
    ):
        """
        Silent registration uses specified configuration to attempt a
        registration with the server.
        """
        self.assertRaises(
            SystemExit,
            main,
            ["--silent", "-c", self.make_working_config()],
            print=noop_print,
        )
        mock_setup.assert_called_once()
        mock_restart_client.assert_called_once()
        mock_register.assert_called_once()
        mock_input.assert_not_called()

    @mock.patch(
        "landscape.client.configuration.ClientRegistrationInfo.from_identity",
    )
    @mock.patch("landscape.client.configuration.restart_client")
    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.set_secure_id")
    @mock.patch("landscape.client.configuration.register")
    @mock.patch("landscape.client.configuration.setup")
    def test_register_insecure_id(
        self,
        mock_setup,
        mock_register,
        mock_set_secure_id,
        mock_input,
        mock_restart_client,
        mock_client_info,
    ):
        """
        Tests that silent registration sets insecure id when provided
        """

        mock_register.return_value = RegistrationInfo(
            10,
            "fake-secure-id",
            "fake-server-uuid",
        )

        self.assertRaises(
            SystemExit,
            main,
            ["--silent", "-c", self.make_working_config()],
            print=noop_print,
        )

        mock_setup.assert_called_once()
        mock_input.assert_not_called()
        mock_set_secure_id.assert_called_once_with(
            mock.ANY,
            "fake-secure-id",
            10,
        )

    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.attempt_registration")
    @mock.patch(
        "landscape.client.configuration.stop_client_and_disable_init_script",
    )
    def test_disable(self, mock_stop_client, mock_register, mock_input):
        main(["--disable", "-c", self.make_working_config()])
        mock_stop_client.assert_called_once_with()
        mock_register.assert_not_called()
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_stop_client_and_disable_init_scripts(self, mock_serviceconfig):
        main(["--disable", "-c", self.make_working_config()])
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(False)
        mock_serviceconfig.stop_landscape.assert_called_once_with()

    def test_non_root(self):
        self.mock_getuid.return_value = 1000
        sys_exit = self.assertRaises(
            SystemExit,
            main,
            ["-c", self.make_working_config()],
        )
        self.mock_getuid.assert_called_once_with()
        self.assertIn("landscape-config must be run as root", str(sys_exit))

    @mock.patch("sys.stdout", new_callable=StringIO)
    def test_main_with_help_and_non_root(self, mock_stdout):
        """It's possible to call 'landscape-config --help' as normal user."""
        self.mock_getuid.return_value = 1000
        self.assertRaises(SystemExit, main, ["--help"])
        self.assertIn(
            "show this help message and exit",
            mock_stdout.getvalue(),
        )

    @mock.patch("sys.stdout", new_callable=StringIO)
    def test_main_with_help_and_non_root_short(self, mock_stdout):
        """It's possible to call 'landscape-config -h' as normal user."""
        self.mock_getuid.return_value = 1000
        self.assertRaises(SystemExit, main, ["-h"])
        self.assertIn(
            "show this help message and exit",
            mock_stdout.getvalue(),
        )

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_import_from_file(self, mock_serviceconfig):
        configuration = (
            "[client]\n"
            "computer_title = New Title\n"
            "account_name = New Name\n"
            "registration_key = New Password\n"
            "http_proxy = http://new.proxy\n"
            "https_proxy = https://new.proxy\n"
            "url = http://new.url\n"
        )

        import_filename = self.makeFile(
            configuration,
            basename="import_config",
        )
        config_filename = self.makeFile("", basename="final_config")

        config = self.get_config(
            [
                "--config",
                config_filename,
                "--silent",
                "--import",
                import_filename,
            ],
        )
        setup(config)

        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)

        options = ConfigParser()
        options.read(config_filename)

        self.assertEqual(
            dict(options.items("client")),
            {
                "computer_title": "New Title",
                "account_name": "New Name",
                "registration_key": "New Password",
                "http_proxy": "http://new.proxy",
                "https_proxy": "https://new.proxy",
                "url": "http://new.url",
            },
        )

    def test_import_from_empty_file(self):
        config_filename = self.makeFile("", basename="final_config")
        import_filename = self.makeFile("", basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(
                [
                    "--config",
                    config_filename,
                    "--silent",
                    "--import",
                    import_filename,
                ],
            )
        except ImportOptionError as error:
            self.assertEqual(
                str(error),
                f"Nothing to import at {import_filename}.",
            )
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_non_existent_file(self):
        config_filename = self.makeFile("", basename="final_config")
        import_filename = self.makeFile(basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(
                [
                    "--config",
                    config_filename,
                    "--silent",
                    "--import",
                    import_filename,
                ],
            )
        except ImportOptionError as error:
            self.assertEqual(
                str(error),
                f"File {import_filename} doesn't exist.",
            )
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_file_with_empty_client_section(self):
        old_configuration = "[client]\n"

        config_filename = self.makeFile(
            "",
            old_configuration,
            basename="final_config",
        )
        import_filename = self.makeFile("", basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(
                [
                    "--config",
                    config_filename,
                    "--silent",
                    "--import",
                    import_filename,
                ],
            )
        except ImportOptionError as error:
            self.assertEqual(
                str(error),
                f"Nothing to import at {import_filename}.",
            )
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_bogus_file(self):
        config_filename = self.makeFile("", basename="final_config")
        import_filename = self.makeFile(
            "<strong>BOGUS!</strong>",
            basename="import_config",
        )

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(
                [
                    "--config",
                    config_filename,
                    "--silent",
                    "--import",
                    import_filename,
                ],
            )
        except ImportOptionError as error:
            self.assertIn(
                f"Nothing to import at {import_filename}",
                str(error),
            )
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_unreadable_file(self):
        """
        An error is raised when unable to read configuration from the
        specified file.
        """
        import_filename = self.makeFile(
            "[client]\nfoo=bar",
            basename="import_config",
        )
        # Remove read permissions
        os.chmod(import_filename, os.stat(import_filename).st_mode - 0o444)
        error = self.assertRaises(
            ImportOptionError,
            self.get_config,
            ["--import", import_filename],
        )
        expected_message = (
            f"Couldn't read configuration from {import_filename}."
        )
        self.assertEqual(str(error), expected_message)

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_import_from_file_preserves_old_options(self, mock_serviceconfig):
        old_configuration = (
            "[client]\n"
            "computer_title = Old Title\n"
            "account_name = Old Name\n"
            "registration_key = Old Password\n"
            "http_proxy = http://old.proxy\n"
            "https_proxy = https://old.proxy\n"
            "url = http://old.url\n"
        )

        new_configuration = (
            "[client]\n"
            "account_name = New Name\n"
            "registration_key = New Password\n"
            "url = http://new.url\n"
        )

        config_filename = self.makeFile(
            old_configuration,
            basename="final_config",
        )
        import_filename = self.makeFile(
            new_configuration,
            basename="import_config",
        )

        # Use a command line option as well to test the precedence.
        config = self.get_config(
            [
                "--config",
                config_filename,
                "--silent",
                "--import",
                import_filename,
                "-p",
                "Command Line Password",
            ],
        )
        setup(config)

        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)
        options = ConfigParser()
        options.read(config_filename)

        self.assertEqual(
            dict(options.items("client")),
            {
                "computer_title": "Old Title",
                "account_name": "New Name",
                "registration_key": "Command Line Password",
                "http_proxy": "http://old.proxy",
                "https_proxy": "https://old.proxy",
                "url": "http://new.url",
            },
        )

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_import_from_file_may_reset_old_options(self, mock_serviceconfig):
        """
        This test ensures that setting an empty option in an imported
        configuration file will actually set the local value to empty
        too, rather than being ignored.
        """
        old_configuration = (
            "[client]\n"
            "computer_title = Old Title\n"
            "account_name = Old Name\n"
            "registration_key = Old Password\n"
            "url = http://old.url\n"
        )

        new_configuration = "[client]\n" "registration_key =\n"

        config_filename = self.makeFile(
            old_configuration,
            basename="final_config",
        )
        import_filename = self.makeFile(
            new_configuration,
            basename="import_config",
        )

        config = self.get_config(
            [
                "--config",
                config_filename,
                "--silent",
                "--import",
                import_filename,
            ],
        )
        setup(config)
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)

        options = ConfigParser()
        options.read(config_filename)

        self.assertEqual(
            dict(options.items("client")),
            {
                "computer_title": "Old Title",
                "account_name": "Old Name",
                "registration_key": "",  # <==
                "url": "http://old.url",
            },
        )

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch")
    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_import_from_url(
        self,
        mock_serviceconfig,
        mock_fetch,
        mock_print_text,
    ):
        mock_serviceconfig.restart_landscape.return_value = True
        configuration = (
            b"[client]\n"
            b"computer_title = New Title\n"
            b"account_name = New Name\n"
            b"registration_key = New Password\n"
            b"http_proxy = http://new.proxy\n"
            b"https_proxy = https://new.proxy\n"
            b"url = http://new.url\n"
        )

        mock_fetch.return_value = configuration

        config_filename = self.makeFile("", basename="final_config")

        config = self.get_config(
            [
                "--config",
                config_filename,
                "--silent",
                "--import",
                "https://config.url",
            ],
        )
        setup(config)
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...",
        )
        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)

        options = ConfigParser()
        options.read(config_filename)

        self.assertEqual(
            dict(options.items("client")),
            {
                "computer_title": "New Title",
                "account_name": "New Name",
                "registration_key": "New Password",
                "http_proxy": "http://new.proxy",
                "https_proxy": "https://new.proxy",
                "url": "http://new.url",
            },
        )

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch")
    def test_import_from_url_with_http_code_fetch_error(
        self,
        mock_fetch,
        mock_print_text,
    ):
        mock_fetch.side_effect = HTTPCodeError(501, "")
        config_filename = self.makeFile("", basename="final_config")

        try:
            self.get_config(
                [
                    "--config",
                    config_filename,
                    "--silent",
                    "--import",
                    "https://config.url",
                ],
            )
        except ImportOptionError as error:
            self.assertEqual(
                str(error),
                "Couldn't download configuration from "
                "https://config.url: Server "
                "returned HTTP code 501",
            )
        else:
            self.fail("ImportOptionError not raised")
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...",
        )

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch")
    def test_import_from_url_with_pycurl_error(
        self,
        mock_fetch,
        mock_print_text,
    ):
        mock_fetch.side_effect = PyCurlError(60, "pycurl message")

        config_filename = self.makeFile("", basename="final_config")

        try:
            self.get_config(
                [
                    "--config",
                    config_filename,
                    "--silent",
                    "--import",
                    "https://config.url",
                ],
            )
        except ImportOptionError as error:
            self.assertEqual(
                str(error),
                "Couldn't download configuration from "
                "https://config.url: Error 60: pycurl message",
            )
        else:
            self.fail("ImportOptionError not raised")
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...",
        )

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch", return_value=b"")
    def test_import_from_url_with_empty_content(
        self,
        mock_fetch,
        mock_print_text,
    ):
        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--silent", "--import", "https://config.url"])
        except ImportOptionError as error:
            self.assertEqual(
                str(error),
                "Nothing to import at https://config.url.",
            )
        else:
            self.fail("ImportOptionError not raised")
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...",
        )

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch(
        "landscape.client.configuration.fetch",
        return_value=b"<strong>BOGUS!</strong>",
    )
    def test_import_from_url_with_bogus_content(
        self,
        mock_fetch,
        mock_print_text,
    ):
        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--silent", "--import", "https://config.url"])
        except ImportOptionError as error:
            self.assertEqual(
                "Nothing to import at https://config.url.",
                str(error),
            )
        else:
            self.fail("ImportOptionError not raised")
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...",
        )

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch(
        "landscape.client.configuration.fetch",
        side_effect=HTTPCodeError(404, ""),
    )
    def test_import_error_is_handled_nicely_by_main(
        self,
        mock_fetch,
        mock_print_text,
    ):
        system_exit = self.assertRaises(
            SystemExit,
            main,
            ["--import", "https://config.url"],
        )
        self.assertEqual(system_exit.code, 1)
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_any_call(
            "Fetching configuration from https://config.url...",
        )
        mock_print_text.assert_called_with(
            "Couldn't download configuration from https://config.url: "
            "Server returned HTTP code 404",
            error=True,
        )

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_base64_ssl_public_key_is_exported_to_file(
        self,
        mock_serviceconfig,
        mock_print_text,
    ):
        mock_serviceconfig.restart_landscape.return_value = True
        data_path = self.makeDir()
        config_filename = self.makeFile(f"[client]\ndata_path={data_path}")
        key_filename = os.path.join(
            data_path,
            os.path.basename(config_filename) + ".ssl_public_key",
        )

        config = self.get_config(
            [
                "--silent",
                "-c",
                config_filename,
                "-u",
                "url",
                "-a",
                "account",
                "-t",
                "title",
                "--ssl-public-key",
                "base64:SGkgdGhlcmUh",
            ],
        )
        config.data_path = data_path
        setup(config)

        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)
        mock_print_text.assert_called_once_with(
            f"Writing SSL CA certificate to {key_filename}...",
        )
        with open(key_filename) as fh:
            self.assertEqual("Hi there!", fh.read())

        options = ConfigParser()
        options.read(config_filename)
        self.assertEqual(options.get("client", "ssl_public_key"), key_filename)

    @mock.patch("landscape.client.configuration.ServiceConfig")
    def test_normal_ssl_public_key_is_not_exported_to_file(
        self,
        mock_serviceconfig,
    ):
        mock_serviceconfig.restart_landscape.return_value = True
        config_filename = self.makeFile("")

        config = self.get_config(
            [
                "--silent",
                "-c",
                config_filename,
                "-u",
                "url",
                "-a",
                "account",
                "-t",
                "title",
                "--ssl-public-key",
                "/some/filename",
            ],
        )
        setup(config)

        mock_serviceconfig.set_start_on_boot.assert_called_once_with(True)
        key_filename = config_filename + ".ssl_public_key"
        self.assertFalse(os.path.isfile(key_filename))

        options = ConfigParser()
        options.read(config_filename)
        self.assertEqual(
            options.get("client", "ssl_public_key"),
            "/some/filename",
        )

    # We test them individually since they must work individually.
    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch")
    def test_import_from_url_honors_http_proxy(
        self,
        mock_fetch,
        mock_print_text,
    ):
        self.ensure_import_from_url_honors_proxy_options(
            "http_proxy",
            mock_fetch,
            mock_print_text,
        )

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch")
    def test_import_from_url_honors_https_proxy(
        self,
        mock_fetch,
        mock_print_text,
    ):
        self.ensure_import_from_url_honors_proxy_options(
            "https_proxy",
            mock_fetch,
            mock_print_text,
        )

    def ensure_import_from_url_honors_proxy_options(
        self,
        proxy_option,
        mock_fetch,
        mock_print_text,
    ):
        def check_proxy(url):
            self.assertEqual("https://config.url", url)
            self.assertEqual(os.environ.get(proxy_option), "http://proxy")
            # Doesn't matter.  We just want to check the context around it.
            return ""

        mock_fetch.side_effect = check_proxy

        config_filename = self.makeFile("", basename="final_config")

        try:
            self.get_config(
                [
                    "--config",
                    config_filename,
                    "--silent",
                    "--" + proxy_option.replace("_", "-"),
                    "http://proxy",
                    "--import",
                    "https://config.url",
                ],
            )
        except ImportOptionError:
            # The returned content is empty.  We don't really care for
            # this test.
            pass
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...",
        )


class FakeConnectorFactory:
    def __init__(self, remote):
        self.remote = remote

    def __call__(self, reactor, config):
        self.reactor = reactor
        self.config = config
        return self

    def connect(self, max_retries=None, quiet=False):
        return succeed(self.remote)

    def disconnect(self):
        return succeed(None)


class FauxConnection:
    def __init__(self):
        self.callbacks = []
        self.errbacks = []

    def addCallback(self, func, *args, **kws):  # noqa: N802
        self.callbacks.append(func)

    def addErrback(self, func, *args, **kws):  # noqa: N802
        self.errbacks.append(func)


class FauxConnector:

    was_disconnected = False

    def __init__(self, reactor=None, config=None):
        self.reactor = reactor
        self.config = config

    def connect(self, max_retries, quiet):
        self.max_retries = max_retries
        self.connection = FauxConnection()
        return self.connection

    def disconnect(self):
        self.was_disconnected = True


class SSLCertificateDataTest(LandscapeConfigurationTest):
    @mock.patch("landscape.client.configuration.print_text")
    def test_store_public_key_data(self, mock_print_text):
        """
        L{store_public_key_data} writes the SSL CA supplied by the server to a
        file for later use, this file is called after the name of the
        configuration file with .ssl_public_key.
        """
        config = self.get_config([])
        os.mkdir(config.data_path)
        key_filename = os.path.join(
            config.data_path,
            os.path.basename(config.get_config_filename()) + ".ssl_public_key",
        )

        self.assertEqual(
            key_filename,
            store_public_key_data(config, b"123456789"),
        )
        self.assertEqual(b"123456789", read_binary_file(key_filename))
        mock_print_text.assert_called_once_with(
            f"Writing SSL CA certificate to {key_filename}...",
        )


class IsRegisteredTest(LandscapeTest):

    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super().setUp()
        persist_file = os.path.join(self.config.data_path, "broker.bpickle")
        self.persist = Persist(filename=persist_file)

    def test_registration_sent_false(self):
        """
        If the client hasn't previously sent a registration request,
        registration_sent returns False
        """
        self.assertFalse(registration_sent(self.config))

    def test_registration_sent_true(self):
        """
        If the client has previously sent a registration request,
        registration_sent returns True.
        """
        self.persist.set("registration.secure-id", "super-secure")
        self.persist.save()
        self.assertTrue(registration_sent(self.config))

    def test_actively_registered_true(self):
        """
        If the client is actively registered with the server returns True
        """
        self.persist.set(
            "message-store.accepted-types",
            ["test", "temperature"],
        )
        self.persist.save()
        self.assertTrue(actively_registered(self.config))

    def test_actively_registered_false(self):
        """
        If the client is not actively registered with the server returns False
        """
        self.persist.set("message-store.accepted-types", ["test", "register"])
        self.persist.save()
        self.assertFalse(actively_registered(self.config))

    def test_actively_registered_false_only_test(self):
        """
        If the client is not actively registered with the server returns False.
        Here we check add only test to the accepted types as it is always an
        accepted type by the server. In the actively_registered function we
        check to see if the len(accepted_types) > 1 to make sure there are more
        accepted types than just the test. This test case makes sure that we
        fail the test case of only test if provided in accepted types
        """
        self.persist.set("message-store.accepted-types", ["test"])
        self.persist.save()
        self.assertFalse(actively_registered(self.config))


class RegistrationInfoTest(LandscapeTest):

    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super().setUp()

        self.custom_args = ["hello.py"]  # Fake python script name
        self.account_name = "world"
        self.data_path = self.makeDir()
        self.config_text = textwrap.dedent(
            """
            [client]
            computer_title = hello
            account_name = {}
            data_path = {}
        """.format(
                self.account_name,
                self.data_path,
            ),
        )

        mock.patch("landscape.client.configuration.init_app_logging").start()

        self.addCleanup(mock.patch.stopall)

    def test_not_registered(self):
        """False when client is not registered"""
        config_filename = self.config.default_config_filenames[0]
        self.makeFile(self.config_text, path=config_filename)
        self.config.load(self.custom_args)
        text = registration_info_text(self.config, False)
        self.assertIn("False", text)
        self.assertNotIn(self.account_name, text)

    def test_registered(self):
        """
        When client is registered, then the text should display as True and
        account name should be present
        """
        config_filename = self.config.default_config_filenames[0]
        self.makeFile(self.config_text, path=config_filename)
        self.config.load(self.custom_args)
        text = registration_info_text(self.config, True)
        self.assertIn("True", text)
        self.assertIn(self.account_name, text)

    def test_custom_config_path(self):
        """The custom config path should show up in the text"""
        custom_path = self.makeFile(self.config_text)
        self.custom_args += ["-c", custom_path]
        self.config.load(self.custom_args)
        text = registration_info_text(self.config, False)
        self.assertIn(custom_path, text)

    def test_data_path(self):
        """The config data path should show in the text"""
        config_filename = self.config.default_config_filenames[0]
        self.makeFile(self.config_text, path=config_filename)
        self.config.load(self.custom_args)
        text = registration_info_text(self.config, False)
        self.assertIn(self.data_path, text)

    def test_registered_exit_code(self):
        """Returns exit code zero when client is registered"""
        Identity.secure_id = "test"  # Simulate successful registration
        exception = self.assertRaises(
            SystemExit,
            main,
            ["--is-registered", "--silent"],
            print=noop_print,
        )
        self.assertEqual(0, exception.code)

    def test_not_registered_exit_code(self):
        """Returns special return code when client is not registered"""
        exception = self.assertRaises(
            SystemExit,
            main,
            ["--is-registered", "--silent"],
            print=noop_print,
        )
        self.assertEqual(EXIT_NOT_REGISTERED, exception.code)


class SetSecureIdTest(LandscapeTest):
    """Tests for the `set_secure_id` function."""

    @mock.patch("landscape.client.configuration.Persist")
    @mock.patch("landscape.client.configuration.Identity")
    def test_function(self, Identity, Persist):
        config = mock.Mock(data_path="/tmp/landscape")

        set_secure_id(config, "fancysecureid")

        Persist.assert_called_once_with(
            filename="/tmp/landscape/broker.bpickle",
            user=USER,
            group=GROUP,
        )
        Persist().save.assert_called_once_with()
        Identity.assert_called_once_with(config, Persist())
        self.assertEqual(Identity().secure_id, "fancysecureid")


class GetSecureIdTest(LandscapeTest):
    @mock.patch("landscape.client.configuration.Persist")
    @mock.patch("landscape.client.configuration.Identity")
    def test_function(self, Identity, Persist):
        config = mock.Mock(data_path="/tmp/landscape")

        set_secure_id(config, "fancysecureid")

        secure_id = get_secure_id(config)

        self.assertEqual(secure_id, "fancysecureid")
