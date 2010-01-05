import os
from getpass import getpass
from ConfigParser import ConfigParser

from dbus import DBusException

from twisted.internet.defer import Deferred, succeed, fail
from twisted.internet import reactor

from landscape.lib.fetch import HTTPCodeError, PyCurlError
from landscape.configuration import (
    print_text, LandscapeSetupScript, LandscapeSetupConfiguration,
    register, setup, main, setup_init_script_and_start_client,
    stop_client_and_disable_init_script, ConfigurationError,
    fetch_import_url, ImportOptionError)
from landscape.broker.registration import InvalidCredentialsError
from landscape.sysvconfig import SysVConfig, ProcessError
from landscape.tests.helpers import (LandscapeTest, LandscapeIsolatedTest,
                                     RemoteBrokerHelper, EnvironSaverHelper)
from landscape.tests.mocker import ARGS, KWARGS, ANY, MATCH, CONTAINS, expect


def get_config(self, args):
    if "--config" not in args and "-c" not in args:
        filename = self.makeFile("""
[client]
url = https://landscape.canonical.com/message-system
""")
        args.extend(["--config", filename])
    config = LandscapeSetupConfiguration(fetch_import_url)
    config.load(args)
    return config


class PrintTextTest(LandscapeTest):

    def test_default(self):
        stdout_mock = self.mocker.replace("sys.stdout")

        self.mocker.order()
        stdout_mock.write("Hi!\n")
        stdout_mock.flush()
        self.mocker.unorder()

        # Trial likes to flush things inside run().
        stdout_mock.flush()
        self.mocker.count(0, None)

        self.mocker.replay()

        print_text("Hi!")

    def test_error(self):
        stderr_mock = self.mocker.replace("sys.stderr")

        self.mocker.order()
        stderr_mock.write("Hi!\n")
        stderr_mock.flush()
        self.mocker.unorder()

        # Trial likes to flush things inside run().
        stderr_mock.flush()
        self.mocker.count(0, None)

        self.mocker.replay()

        print_text("Hi!", error=True)

    def test_end(self):
        stdout_mock = self.mocker.replace("sys.stdout")

        self.mocker.order()
        stdout_mock.write("Hi!END")
        stdout_mock.flush()
        self.mocker.unorder()

        # Trial likes to flush things inside run().
        stdout_mock.flush()
        self.mocker.count(0, None)

        self.mocker.replay()

        print_text("Hi!", "END")


class LandscapeSetupScriptTest(LandscapeTest):

    def setUp(self):
        super(LandscapeSetupScriptTest, self).setUp()
        self.config_filename = self.makeFile()
        class MyLandscapeSetupConfiguration(LandscapeSetupConfiguration):
            default_config_filenames = [self.config_filename]
        self.config = MyLandscapeSetupConfiguration(None)
        self.script = LandscapeSetupScript(self.config)

    def test_show_help(self):
        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("\nHello\n\nworld!\n")
        print_text_mock(ANY)
        self.mocker.count(0)
        self.mocker.replay()

        self.script.show_help("\n\n \n  Hello  \n  \n  world!  \n \n\n")

    def test_prompt_simple(self):
        mock = self.mocker.replace(raw_input, passthrough=False)
        mock("Message: ")
        self.mocker.result("Desktop")
        self.mocker.replay()

        self.script.prompt("computer_title", "Message")

        self.assertEquals(self.config.computer_title, "Desktop")

    def test_prompt_with_default(self):
        mock = self.mocker.replace(raw_input, passthrough=False)
        mock("Message [default]: ")
        self.mocker.result("")
        self.mocker.replay()

        self.config.computer_title = "default"
        self.script.prompt("computer_title", "Message")

        self.assertEquals(self.config.computer_title, "default")

    def test_prompt_with_required(self):
        self.mocker.order()
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        script_mock = self.mocker.patch(self.script)
        raw_input_mock("Message: ")
        self.mocker.result("")
        script_mock.show_help("This option is required to configure Landscape.")
        raw_input_mock("Message: ")
        self.mocker.result("Desktop")
        self.mocker.replay()

        self.script.prompt("computer_title", "Message", True)

        self.assertEquals(self.config.computer_title, "Desktop")

    def test_prompt_with_required_and_default(self):
        self.mocker.order()
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        script_mock = self.mocker.patch(self.script)
        raw_input_mock("Message [Desktop]: ")
        self.mocker.result("")
        self.mocker.replay()
        self.config.computer_title = "Desktop"
        self.script.prompt("computer_title", "Message", True)
        self.assertEquals(self.config.computer_title, "Desktop")

    def test_prompt_for_unknown_variable(self):
        """
        It should be possible to prompt() defining a variable that doesn't
        'exist' in the configuration, and still have it set there.
        """
        self.mocker.order()
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        self.assertFalse(hasattr(self.config, "variable"))
        self.expect(raw_input_mock("Variable: ")).result("Yay")
        self.mocker.replay()
        self.script.prompt("variable", "Variable")
        self.assertEquals(self.config.variable, "Yay")

    def test_password_prompt_simple_matching(self):
        mock = self.mocker.replace(getpass, passthrough=False)
        mock("Password: ")
        self.mocker.result("password")
        mock("Please confirm: ")
        self.mocker.result("password")
        self.mocker.replay()

        self.script.password_prompt("registration_password", "Password")
        self.assertEquals(self.config.registration_password, "password")

    def test_password_prompt_simple_non_matching(self):
        mock = self.mocker.replace(getpass, passthrough=False)
        mock("Password: ")
        self.mocker.result("password")

        script_mock = self.mocker.patch(self.script)
        script_mock.show_help("Passwords must match.")

        mock("Please confirm: ")
        self.mocker.result("")
        mock("Password: ")
        self.mocker.result("password")
        mock("Please confirm: ")
        self.mocker.result("password")
        self.mocker.replay()
        self.script.password_prompt("registration_password", "Password")
        self.assertEquals(self.config.registration_password, "password")

    def test_password_prompt_simple_matching_required(self):
        mock = self.mocker.replace(getpass, passthrough=False)
        mock("Password: ")
        self.mocker.result("")

        script_mock = self.mocker.patch(self.script)
        script_mock.show_help("This option is required to configure Landscape.")

        mock("Password: ")
        self.mocker.result("password")
        mock("Please confirm: ")
        self.mocker.result("password")

        self.mocker.replay()

        self.script.password_prompt("registration_password", "Password", True)
        self.assertEquals(self.config.registration_password, "password")

    def test_prompt_yes_no(self):
        comparisons = [("Y", True),
                       ("y", True),
                       ("yEs", True),
                       ("YES", True),
                       ("n", False),
                       ("N", False),
                       ("No", False),
                       ("no", False),
                       ("", True)]

        self.mocker.order()
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        for comparison in comparisons:
            self.expect(raw_input_mock("Foo [Y/n]")).result(comparison[0])
        self.mocker.replay()
        for comparison in comparisons:
            self.assertEquals(self.script.prompt_yes_no("Foo"), comparison[1])

    def test_prompt_yes_no_default(self):
        self.mocker.order()
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        self.expect(raw_input_mock("Foo [y/N]")).result("")
        self.mocker.replay()
        self.assertFalse(self.script.prompt_yes_no("Foo", default=False))

    def test_prompt_yes_no_invalid(self):
        self.mocker.order()
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        script_mock = self.mocker.patch(self.script)
        self.expect(raw_input_mock("Foo [Y/n]")).result("x")
        script_mock.show_help("Invalid input.")
        self.expect(raw_input_mock("Foo [Y/n]")).result("n")
        self.mocker.replay()
        self.assertFalse(self.script.prompt_yes_no("Foo"))

    def get_matcher(self, help_snippet):
        def match_help(help):
            return help.strip().startswith(help_snippet)
        return MATCH(match_help)

    def test_query_computer_title(self):
        help_snippet = "The computer title you"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt("computer_title", "This computer's title", True)
        self.mocker.replay()

        self.script.query_computer_title()

    def test_query_computer_title_defined_on_command_line(self):
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        self.expect(raw_input_mock(ANY)).count(0)
        self.mocker.replay()

        self.config.load_command_line(["-t", "Computer title"])
        self.script.query_computer_title()

    def test_query_account_name(self):
        help_snippet = "You must now specify the name of the Landscape account"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt("account_name", "Account name", True)
        self.mocker.replay()

        self.script.query_account_name()

    def test_query_account_name_defined_on_command_line(self):
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        self.expect(raw_input_mock(ANY)).count(0)
        self.mocker.replay()

        self.config.load_command_line(["-a", "Account name"])
        self.script.query_account_name()

    def test_query_registration_password(self):
        help_snippet = "A registration password may be"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.password_prompt("registration_password",
                                    "Account registration password")
        self.mocker.replay()
        self.script.query_registration_password()

    def test_query_registration_password_defined_on_command_line(self):
        getpass_mock = self.mocker.replace("getpass.getpass", passthrough=False)
        self.expect(getpass_mock(ANY)).count(0)
        self.mocker.replay()

        self.config.load_command_line(["-p", "shared-secret"])
        self.script.query_registration_password()

    def test_query_proxies(self):
        help_snippet = "The Landscape client communicates"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt("http_proxy", "HTTP proxy URL")
        script_mock.prompt("https_proxy", "HTTPS proxy URL")
        self.mocker.replay()
        self.script.query_proxies()

    def test_query_proxies_defined_on_command_line(self):
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        self.expect(raw_input_mock(ANY)).count(0)
        self.mocker.replay()

        self.config.load_command_line(["--http-proxy", "localhost:8080",
                                       "--https-proxy", "localhost:8443"])
        self.script.query_proxies()

    def test_query_http_proxy_defined_on_command_line(self):
        help_snippet = "The Landscape client communicates"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt("https_proxy", "HTTPS proxy URL")
        self.mocker.replay()

        self.config.load_command_line(["--http-proxy", "localhost:8080"])
        self.script.query_proxies()

    def test_query_https_proxy_defined_on_command_line(self):
        help_snippet = "The Landscape client communicates"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt("http_proxy", "HTTP proxy URL")
        self.mocker.replay()

        self.config.load_command_line(["--https-proxy", "localhost:8443"])
        self.script.query_proxies()

    def test_query_script_plugin_no(self):
        help_snippet = "Landscape has a feature which enables administrators"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt_yes_no("Enable script execution?", default=False)
        self.mocker.result(False)
        self.mocker.replay()
        self.script.query_script_plugin()
        self.assertEquals(self.config.include_manager_plugins, "")

    def test_query_script_plugin_yes(self):
        """
        If the user *does* want script execution, then the script asks which
        users to enable it for.
        """
        help_snippet = "Landscape has a feature which enables administrators"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt_yes_no("Enable script execution?", default=False)
        self.mocker.result(True)
        script_mock.show_help(
            self.get_matcher("By default, scripts are restricted"))
        script_mock.prompt("script_users", "Script users")
        self.mocker.replay()
        self.script.query_script_plugin()
        self.assertEquals(self.config.include_manager_plugins,
                          "ScriptExecution")

    def test_disable_script_plugin(self):
        """
        Answering NO to enabling the script plugin while it's already enabled
        will disable it.
        """
        self.config.include_manager_plugins = "ScriptExecution"
        help_snippet = "Landscape has a feature which enables administrators"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt_yes_no("Enable script execution?", default=True)
        self.mocker.result(False)
        self.mocker.replay()
        self.script.query_script_plugin()
        self.assertEquals(self.config.include_manager_plugins, "")

    def test_disabling_script_plugin_leaves_existing_inclusions(self):
        """
        Disabling the script execution plugin doesn't remove other included
        plugins.
        """
        self.config.include_manager_plugins = "FooPlugin, ScriptExecution"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(ANY)
        script_mock.prompt_yes_no("Enable script execution?", default=True)
        self.mocker.result(False)
        self.mocker.replay()
        self.script.query_script_plugin()
        self.assertEquals(self.config.include_manager_plugins, "FooPlugin")

    def test_enabling_script_plugin_leaves_existing_inclusions(self):
        """
        Enabling the script execution plugin doesn't remove other included
        plugins.
        """
        self.config.include_manager_plugins = "FooPlugin"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(ANY)
        script_mock.prompt_yes_no("Enable script execution?", default=False)
        self.mocker.result(True)
        script_mock.show_help(ANY)
        script_mock.prompt("script_users", "Script users")
        self.mocker.replay()
        self.script.query_script_plugin()
        self.assertEquals(self.config.include_manager_plugins,
                          "FooPlugin, ScriptExecution")

    def test_query_script_plugin_defined_on_command_line(self):
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        self.expect(raw_input_mock(ANY)).count(0)
        self.mocker.replay()

        self.config.load_command_line(
            ["--include-manager-plugins", "ScriptExecution",
             "--script-users", "root, nobody"])
        self.script.query_script_plugin()
        self.assertEquals(self.config.include_manager_plugins,
                          "ScriptExecution")
        self.assertEquals(self.config.script_users, "root, nobody")

    def test_query_script_manager_plugins_defined_on_command_line(self):
        self.config.include_manager_plugins = "FooPlugin"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(ANY)
        script_mock.prompt_yes_no("Enable script execution?", default=False)
        self.mocker.result(True)
        script_mock.show_help(ANY)
        script_mock.prompt("script_users", "Script users")
        self.mocker.replay()

        self.config.load_command_line(
            ["--include-manager-plugins", "FooPlugin, ScriptExecution"])
        self.script.query_script_plugin()
        self.assertEquals(self.config.include_manager_plugins,
                          "FooPlugin, ScriptExecution")

    def test_query_script_users_defined_on_command_line(self):
        """
        Confirm with the user for users specified for the ScriptPlugin.
        """
        self.config.include_manager_plugins = "FooPlugin"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(ANY)
        script_mock.prompt_yes_no("Enable script execution?", default=False)
        self.mocker.result(True)
        script_mock.show_help(ANY)
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        self.expect(raw_input_mock(ANY)).count(0)
        self.mocker.replay()

        self.config.load_command_line(
            ["--script-users", "root, nobody, landscape"])
        self.script.query_script_plugin()
        self.assertEquals(self.config.script_users,
                          "root, nobody, landscape")

    def test_query_script_users_defined_on_command_line_with_unknown_user(self):
        """
        If several users are provided on the command line, we verify the users
        and raise a ConfigurationError if any are unknown on this system.
        """
        pwnam_mock = self.mocker.replace("pwd.getpwnam")
        pwnam_mock("root")
        self.mocker.result(None)
        pwnam_mock("nobody")
        self.mocker.result(None)
        pwnam_mock("landscape")
        self.mocker.result(None)
        pwnam_mock("unknown")
        self.mocker.throw(KeyError())
        self.mocker.replay()

        self.config.load_command_line(
            ["--script-users", "root, nobody, landscape, unknown",
            "--include-manager-plugins", "ScriptPlugin"])
        self.assertRaises(ConfigurationError, self.script.query_script_plugin)

    def test_query_script_users_defined_on_command_line_with_all_user(self):
        """
        We shouldn't accept all as a synonym for ALL
        """
        self.config.load_command_line(
            ["--script-users", "all",
            "--include-manager-plugins", "ScriptPlugin"])
        self.assertRaises(ConfigurationError, self.script.query_script_plugin)

    def test_query_script_users_defined_on_command_line_with_ALL_user(self):
        """
        ALL is the special marker for all users.
        """
        self.config.load_command_line(
            ["--script-users", "ALL",
             "--include-manager-plugins", "ScriptPlugin"])
        self.script.query_script_plugin()
        self.assertEquals(self.config.script_users,
                          "ALL")

    def test_query_script_users_defined_on_command_line_with_ALL_and_extra_user(self):
        """
        If ALL and additional users are provided as the users on the command
        line, this should raise an appropriate ConfigurationError.
        """
        self.config.load_command_line(
            ["--script-users", "ALL, kevin",
            "--include-manager-plugins", "ScriptPlugin"])
        self.assertRaises(ConfigurationError, self.script.query_script_plugin)

    def test_invalid_user_entered_by_user(self):
        """
        If an invalid user is entered on the command line the user should be
        informed and prompted again.
        """
        help_snippet = "Landscape has a feature which enables administrators"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt_yes_no("Enable script execution?", default=False)
        self.mocker.result(True)
        script_mock.show_help(
            self.get_matcher("By default, scripts are restricted"))
        script_mock.prompt_get_input("Script users: ", False)
        self.mocker.result(u"nonexistent")
        script_mock.show_help("Unknown system users: nonexistent")
        script_mock.prompt_get_input("Script users: ", False)
        self.mocker.result(u"root")
        self.mocker.replay()
        self.script.query_script_plugin()
        self.assertEquals(self.config.script_users,
                          "root")

    def test_tags_not_defined_on_command_line(self):
        """
        If tags are not provided, the user should be prompted for them.
        """
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help("You may provide tags for this computer e.g. "
                              "server,hardy.")
        script_mock.prompt("tags", "Tags", False)
        self.mocker.replay()
        self.script.query_tags()

    def test_invalid_tags_entered_by_user(self):
        """
        If tags are not provided, the user should be prompted for them, and
        they should be valid tags, if not the user should be prompted for them
        again.
        """
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help("You may provide tags for this computer e.g. "
                              "server,hardy.")
        script_mock.prompt_get_input("Tags: ", False)
        self.mocker.result(u"<script>alert();</script>")
        script_mock.show_help("Tag names may only contain alphanumeric "
                              "characters.")
        script_mock.prompt_get_input("Tags: ", False)
        self.mocker.result(u"london")
        self.mocker.replay()
        self.script.query_tags()

    def test_tags_defined_on_command_line(self):
        """
        Tags defined on the command line can be verified by the user.
        """
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        self.expect(raw_input_mock(ANY)).count(0)
        self.mocker.replay()
        self.config.load_command_line(["--tags", u"server,london"])
        self.script.query_tags()
        self.assertEquals(self.config.tags, u"server,london")

    def test_invalid_tags_defined_on_command_line_raises_error(self):
        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        self.expect(raw_input_mock(ANY)).count(0)
        self.mocker.replay()
        self.config.load_command_line(["--tags", u"<script>alert();</script>"])
        self.assertRaises(ConfigurationError, self.script.query_tags)

    def test_show_header(self):
        help_snippet = "This script will"
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        self.mocker.replay()

        self.script.show_header()

    def test_run(self):
        script_mock = self.mocker.patch(self.script)
        script_mock.show_header()
        script_mock.query_computer_title()
        script_mock.query_account_name()
        script_mock.query_registration_password()
        script_mock.query_proxies()
        script_mock.query_script_plugin()
        script_mock.query_tags()
        self.mocker.replay()

        self.script.run()


class ConfigurationFunctionsTest(LandscapeTest):

    helpers = [EnvironSaverHelper]

    def setUp(self):
        super(ConfigurationFunctionsTest, self).setUp()
        self.mocker.replace("os.getuid")()
        self.mocker.count(0, None)
        self.mocker.result(0)

    def get_config(self, args):
        return get_config(self, args)

    def get_content(self, config):
        """Write C{config} to a file and return it's contents as a string."""
        config_file = self.makeFile("")
        original_config = config.config
        try:
            config.config = config_file
            config.write()
            return open(config.config, "r").read().strip() + "\n"
        finally:
            config.config = original_config

    def test_setup(self):
        filename = self.makeFile("[client]\n"
                                 "computer_title = Old Title\n"
                                 "account_name = Old Name\n"
                                 "registration_password = Old Password\n"
                                 "http_proxy = http://old.proxy\n"
                                 "https_proxy = https://old.proxy\n"
                                 "url = http://url\n"
                                 "include_manager_plugins = ScriptExecution\n"
                                 "tags = london, server"
                                 )

        raw_input = self.mocker.replace("__builtin__.raw_input",
                                        name="raw_input")
        getpass = self.mocker.replace("getpass.getpass")

        C = CONTAINS

        expect(raw_input(C("[Old Title]"))).result("New Title")
        expect(raw_input(C("[Old Name]"))).result("New Name")
        expect(getpass(C("registration password:"))).result("New Password")
        expect(getpass(C("Please confirm:"))).result("New Password")
        expect(raw_input(C("[http://old.proxy]"))).result("http://new.proxy")
        expect(raw_input(C("[https://old.proxy]"))).result("https://new.proxy")
        expect(raw_input(C("Enable script execution? [Y/n]"))).result("n")
        expect(raw_input(C("Tags [london, server]: "))).result(
            u"glasgow, laptop")

        # Negative assertion.  We don't want it called in any other way.
        expect(raw_input(ANY)).count(0)

        # We don't care about these here, but don't show any output please.
        print_text_mock = self.mocker.replace(print_text)
        expect(print_text_mock(ANY)).count(0, None)

        self.mocker.replay()
        config = self.get_config(["--no-start", "--config", filename])
        setup(config)
        self.assertEquals(type(config), LandscapeSetupConfiguration)

        # Reload it to ensure it was written down.
        config.reload()

        self.assertEquals(config.computer_title, "New Title")
        self.assertEquals(config.account_name, "New Name")
        self.assertEquals(config.registration_password, "New Password")
        self.assertEquals(config.http_proxy, "http://new.proxy")
        self.assertEquals(config.https_proxy, "https://new.proxy")
        self.assertEquals(config.include_manager_plugins, "")
        self.assertEquals(config.tags, u"glasgow, laptop")

    def test_silent_setup(self):
        """
        Only command-line options are used in silent mode and registration is
        attempted.
        """
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.replay()

        config = self.get_config(["--silent", "-a", "account", "-t", "rex"])
        setup(config)
        self.assertEquals(self.get_content(config), """\
[client]
url = https://landscape.canonical.com/message-system
computer_title = rex
account_name = account
""")

    def test_silent_setup_without_computer_title(self):
        """A computer title is required."""
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        self.mocker.replay()

        config = self.get_config(["--silent", "-a", "account"])
        self.assertRaises(ConfigurationError, setup, config)

    def test_silent_setup_without_account_name(self):
        """An account name is required."""
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        self.mocker.replay()

        config = self.get_config(["--silent", "-t", "rex"])
        self.assertRaises(ConfigurationError, setup, config)

    def test_silent_script_users_imply_script_execution_plugin(self):
        """
        If C{--script-users} is specified, without C{ScriptExecution} in the
        list of manager plugins, it will be automatically added.
        """
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.result(True)

        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        self.expect(raw_input_mock(ANY)).count(0)
        self.mocker.replay()

        filename = self.makeFile("""
[client]
url = https://localhost:8080/message-system
bus = session
""")

        config = self.get_config(["--config", filename, "--silent",
                                  "-a", "account", "-t", "rex",
                                  "--script-users", "root, nobody"])
        setup(config)
        contents = open(filename, "r").read().strip() + "\n"
        self.assertEquals(contents, """\
[client]
url = https://localhost:8080/message-system
bus = session
computer_title = rex
include_manager_plugins = ScriptExecution
script_users = root, nobody
account_name = account
""")

    def test_silent_script_users_with_all_user(self):
        """
        In silent mode, we shouldn't accept invalid users, it should raise a
        configuration error.
        """
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        self.mocker.replay()

        config = self.get_config(
            ["--script-users", "all",
             "--include-manager-plugins", "ScriptPlugin",
             "-a", "account",
             "-t", "rex",
             "--silent"])
        self.assertRaises(ConfigurationError, setup, config)

    def test_silent_setup_with_ping_url(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.result(True)
        self.mocker.replay()

        filename = self.makeFile("""
[client]
url = https://landscape.canonical.com/message-system
ping_url = http://landscape.canonical.com/ping
registration_password = shared-secret
log_level = debug
random_key = random_value
""")
        config = self.get_config(["--config", filename, "--silent",
                                  "-a", "account", "-t", "rex",
                                  "--ping-url", "http://localhost/ping"])
        setup(config)
        self.assertEquals(self.get_content(config), """\
[client]
log_level = debug
registration_password = shared-secret
computer_title = rex
url = https://landscape.canonical.com/message-system
ping_url = http://localhost/ping
random_key = random_value
account_name = account
""")

    def test_setup_with_proxies_from_environment(self):
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"

        script_mock = self.mocker.patch(LandscapeSetupScript)
        script_mock.run()

        filename = self.makeFile("[client]\n"
                                 "url = http://url\n")

        self.mocker.replay()

        config = self.get_config(["--no-start", "--config", filename])
        setup(config)

        # Reload it to ensure it was written down.
        config.reload()

        self.assertEquals(config.http_proxy, "http://environ")
        self.assertEquals(config.https_proxy, "https://environ")

    def test_silent_setup_with_proxies_from_environment(self):
        """
        Only command-line options are used in silent mode and registration is
        attempted.
        """
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.replay()

        filename = self.makeFile("""
[client]
url = https://landscape.canonical.com/message-system
registration_password = shared-secret
""")
        config = self.get_config(["--config", filename, "--silent",
                                  "-a", "account", "-t", "rex"])
        setup(config)
        self.assertEquals(self.get_content(config), """\
[client]
registration_password = shared-secret
computer_title = rex
http_proxy = http://environ
https_proxy = https://environ
url = https://landscape.canonical.com/message-system
account_name = account
""")

    def test_setup_prefers_proxies_from_config_over_environment(self):
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"

        script_mock = self.mocker.patch(LandscapeSetupScript)
        script_mock.run()

        filename = self.makeFile("[client]\n"
                                 "http_proxy = http://config\n"
                                 "https_proxy = https://config\n"
                                 "url = http://url\n")

        self.mocker.replay()

        config = self.get_config(["--no-start", "--config", filename])
        setup(config)

        # Reload it to enusre it was written down.
        config.reload()

        self.assertEquals(config.http_proxy, "http://config")
        self.assertEquals(config.https_proxy, "https://config")

    def test_main_no_registration(self):
        setup_mock = self.mocker.replace(setup)
        setup_mock(ANY)

        raw_input_mock = self.mocker.replace(raw_input)
        raw_input_mock("\nRequest a new registration for "
                       "this computer now? (Y/n): ")
        self.mocker.result("n")

        # This must not be called.
        register_mock = self.mocker.replace(register, passthrough=False)
        register_mock(ANY)
        self.mocker.count(0)

        self.mocker.replay()

        main(["-c", self.make_working_config()])

    def make_working_config(self):
        return self.makeFile("[client]\n"
                             "computer_title = Old Title\n"
                             "account_name = Old Name\n"
                             "registration_password = Old Password\n"
                             "http_proxy = http://old.proxy\n"
                             "https_proxy = https://old.proxy\n"
                             "url = http://url\n")

    def test_register(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.is_configured_to_run()
        self.mocker.result(False)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()

        script_mock = self.mocker.patch(LandscapeSetupScript)
        script_mock.run()

        raw_input_mock = self.mocker.replace(raw_input)
        raw_input_mock("\nRequest a new registration for "
                       "this computer now? (Y/n): ")
        self.mocker.result("")

        raw_input_mock("\nThe Landscape client must be started "
                       "on boot to operate correctly.\n\n"
                       "Start Landscape client on boot? (Y/n): ")
        self.mocker.result("")

        register_mock = self.mocker.replace(register, passthrough=False)
        register_mock(ANY)

        self.mocker.replay()
        main(["--config", self.make_working_config()])

    def test_errors_from_restart_landscape(self):
        """
        If a ProcessError exception is raised from restart_landscape (because
        the client failed to be restarted), an informative message is printed
        and the script exits.
        """
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        print_text_mock = self.mocker.replace(print_text)

        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.throw(ProcessError)

        print_text_mock("Couldn't restart the Landscape client.", error=True)
        print_text_mock(CONTAINS("This machine will be registered"), error=True)

        self.mocker.replay()

        config = self.get_config(["--silent", "-a", "account", "-t", "rex"])
        system_exit = self.assertRaises(SystemExit, setup, config)
        self.assertEquals(system_exit.code, 2)

    def test_errors_from_restart_landscape_ok_no_register(self):
        """
        Exit code 0 will be returned if the client fails to be restarted and
        --ok-no-register was passed.
        """
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        print_text_mock = self.mocker.replace(print_text)

        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.throw(ProcessError)

        print_text_mock("Couldn't restart the Landscape client.", error=True)
        print_text_mock(CONTAINS("This machine will be registered"), error=True)

        self.mocker.replay()

        config = self.get_config(["--silent", "-a", "account", "-t", "rex",
                                  "--ok-no-register"])
        system_exit = self.assertRaises(SystemExit, setup, config)
        self.assertEquals(system_exit.code, 0)

    def test_main_with_register(self):
        setup_mock = self.mocker.replace(setup)
        setup_mock(ANY)
        raw_input_mock = self.mocker.replace(raw_input)
        raw_input_mock("\nRequest a new registration for "
                       "this computer now? (Y/n): ")
        self.mocker.result("")

        register_mock = self.mocker.replace(register, passthrough=False)
        register_mock(ANY)

        self.mocker.replay()
        main(["-c", self.make_working_config()])

    def test_setup_init_script_and_start_client(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        self.mocker.replay()

        setup_init_script_and_start_client()

    def test_setup_init_script_and_start_client_silent(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)

        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        raw_input_mock(ANY)
        self.mocker.count(0)
        self.mocker.replay()
        setup_init_script_and_start_client()

    def test_register_silent(self):
        """
        Silent registration uses specified configuration to attempt a
        registration with the server.
        """
        setup_mock = self.mocker.replace(setup)
        setup_mock(ANY)
        # No interaction should be requested.
        raw_input_mock = self.mocker.replace(raw_input)
        raw_input_mock(ANY)
        self.mocker.count(0)

        # The registration logic should be called and passed the configuration
        # file.
        register_mock = self.mocker.replace(register, passthrough=False)
        register_mock(ANY)

        self.mocker.replay()

        main(["--silent", "-c", self.make_working_config()])

    def test_disable(self):
        stop_client_and_disable_init_script_mock = self.mocker.replace(
            stop_client_and_disable_init_script)
        stop_client_and_disable_init_script_mock()

        # No interaction should be requested.
        raw_input_mock = self.mocker.replace(raw_input)
        raw_input_mock(ANY)
        self.mocker.count(0)

        # Registration logic should not be invoked.
        register_mock = self.mocker.replace(register, passthrough=False)
        register_mock(ANY)
        self.mocker.count(0)

        self.mocker.replay()

        main(["--disable", "-c", self.make_working_config()])

    def test_stop_client_and_disable_init_scripts(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(False)
        sysvconfig_mock.stop_landscape()
        self.mocker.replay()

        main(["--disable", "-c", self.make_working_config()])

    def test_non_root(self):
        self.mocker.reset() # Forget the thing done in setUp
        self.mocker.replace("os.getuid")()
        self.mocker.result(1000)
        self.mocker.replay()
        sys_exit = self.assertRaises(SystemExit,
                                     main, ["-c", self.make_working_config()])
        self.assertIn("landscape-config must be run as root", str(sys_exit))

    def test_import_from_file(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.result(True)
        self.mocker.replay()

        configuration = (
            "[client]\n"
            "computer_title = New Title\n"
            "account_name = New Name\n"
            "registration_password = New Password\n"
            "http_proxy = http://new.proxy\n"
            "https_proxy = https://new.proxy\n"
            "url = http://new.url\n")

        import_filename = self.makeFile(configuration, basename="import_config")
        config_filename = self.makeFile("", basename="final_config")

        config = self.get_config(["--config", config_filename, "--silent",
                                  "--import", import_filename])
        setup(config)

        options = ConfigParser()
        options.read(config_filename)

        self.assertEquals(dict(options.items("client")),
                          {"computer_title": "New Title",
                           "account_name": "New Name",
                           "registration_password": "New Password",
                           "http_proxy": "http://new.proxy",
                           "https_proxy": "https://new.proxy",
                           "url": "http://new.url"})

    def test_import_from_empty_file(self):
        self.mocker.replay()

        config_filename = self.makeFile("", basename="final_config")
        import_filename = self.makeFile("", basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", import_filename])
        except ImportOptionError, error:
            self.assertEquals(str(error), 
                              "Nothing to import at %s." % import_filename)
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_non_existent_file(self):
        self.mocker.replay()

        config_filename = self.makeFile("", basename="final_config")
        import_filename = self.makeFile(basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", import_filename])
        except ImportOptionError, error:
            self.assertEquals(str(error), 
                              "File %s doesn't exist." % import_filename)
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_file_with_empty_client_section(self):
        self.mocker.replay()

        old_configuration = "[client]\n"

        config_filename = self.makeFile("", old_configuration,
                                        basename="final_config")
        import_filename = self.makeFile("", basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", import_filename])
        except ImportOptionError, error:
            self.assertEquals(str(error), 
                              "Nothing to import at %s." % import_filename)
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_bogus_file(self):
        self.mocker.replay()

        config_filename = self.makeFile("", basename="final_config")
        import_filename = self.makeFile("<strong>BOGUS!</strong>",
                                        basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", import_filename])
        except ImportOptionError, error:
            self.assertIn("File contains no section headers.", str(error))
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_file_preserves_old_options(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.result(True)
        self.mocker.replay()

        old_configuration = (
            "[client]\n"
            "computer_title = Old Title\n"
            "account_name = Old Name\n"
            "registration_password = Old Password\n"
            "http_proxy = http://old.proxy\n"
            "https_proxy = https://old.proxy\n"
            "url = http://old.url\n")

        new_configuration = (
            "[client]\n"
            "account_name = New Name\n"
            "registration_password = New Password\n"
            "url = http://new.url\n")

        config_filename = self.makeFile(old_configuration,
                                        basename="final_config")
        import_filename = self.makeFile(new_configuration,
                                        basename="import_config")

        # Use a command line option as well to test the precedence.
        config = self.get_config(["--config", config_filename, "--silent",
                                  "--import", import_filename,
                                  "-p", "Command Line Password"])
        setup(config)

        options = ConfigParser()
        options.read(config_filename)

        self.assertEquals(dict(options.items("client")),
                          {"computer_title": "Old Title",
                           "account_name": "New Name",
                           "registration_password": "Command Line Password",
                           "http_proxy": "http://old.proxy",
                           "https_proxy": "https://old.proxy",
                           "url": "http://new.url"})

    def test_import_from_file_may_reset_old_options(self):
        """
        This test ensures that setting an empty option in an imported
        configuration file will actually set the local value to empty
        too, rather than being ignored.
        """
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.result(True)
        self.mocker.replay()

        old_configuration = (
            "[client]\n"
            "computer_title = Old Title\n"
            "account_name = Old Name\n"
            "registration_password = Old Password\n"
            "url = http://old.url\n")

        new_configuration = (
            "[client]\n"
            "registration_password =\n")

        config_filename = self.makeFile(old_configuration,
                                        basename="final_config")
        import_filename = self.makeFile(new_configuration,
                                        basename="import_config")

        config = self.get_config(["--config", config_filename, "--silent",
                                  "--import", import_filename])
        setup(config)

        options = ConfigParser()
        options.read(config_filename)

        self.assertEquals(dict(options.items("client")),
                          {"computer_title": "Old Title",
                           "account_name": "Old Name",
                           "registration_password": "", # <==
                           "url": "http://old.url"})

    def test_import_from_url(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.result(True)

        configuration = (
            "[client]\n"
            "computer_title = New Title\n"
            "account_name = New Name\n"
            "registration_password = New Password\n"
            "http_proxy = http://new.proxy\n"
            "https_proxy = https://new.proxy\n"
            "url = http://new.url\n")

        fetch_mock = self.mocker.replace("landscape.lib.fetch.fetch")
        fetch_mock("https://config.url")
        self.mocker.result(configuration)

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Fetching configuration from https://config.url...")

        self.mocker.replay()

        config_filename = self.makeFile("", basename="final_config")

        config = self.get_config(["--config", config_filename, "--silent",
                                  "--import", "https://config.url"])
        setup(config)

        options = ConfigParser()
        options.read(config_filename)

        self.assertEquals(dict(options.items("client")),
                          {"computer_title": "New Title",
                           "account_name": "New Name",
                           "registration_password": "New Password",
                           "http_proxy": "http://new.proxy",
                           "https_proxy": "https://new.proxy",
                           "url": "http://new.url"})

    def test_import_from_url_with_http_code_fetch_error(self):
        fetch_mock = self.mocker.replace("landscape.lib.fetch.fetch")
        fetch_mock("https://config.url")
        self.mocker.throw(HTTPCodeError(501, ""))

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Fetching configuration from https://config.url...")

        self.mocker.replay()

        config_filename = self.makeFile("", basename="final_config")

        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", "https://config.url"])
        except ImportOptionError, error:
            self.assertEquals(str(error),
                              "Couldn't download configuration from "
                              "https://config.url: Server "
                              "returned HTTP code 501")
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_url_with_pycurl_error(self):
        fetch_mock = self.mocker.replace("landscape.lib.fetch.fetch")
        fetch_mock("https://config.url")
        self.mocker.throw(PyCurlError(60, "pycurl message"))

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Fetching configuration from https://config.url...")

        self.mocker.replay()

        config_filename = self.makeFile("", basename="final_config")

        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", "https://config.url"])
        except ImportOptionError, error:
            self.assertEquals(str(error),
                              "Couldn't download configuration from "
                              "https://config.url: Error 60: pycurl message")
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_url_with_empty_content(self):
        fetch_mock = self.mocker.replace("landscape.lib.fetch.fetch")
        fetch_mock("https://config.url")
        self.mocker.result("")

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Fetching configuration from https://config.url...")

        self.mocker.replay()

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--silent", "--import", "https://config.url"])
        except ImportOptionError, error:
            self.assertEquals(str(error), 
                              "Nothing to import at https://config.url.")
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_url_with_bogus_content(self):
        fetch_mock = self.mocker.replace("landscape.lib.fetch.fetch")
        fetch_mock("https://config.url")
        self.mocker.result("<strong>BOGUS!</strong>")

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Fetching configuration from https://config.url...")

        self.mocker.replay()

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--silent", "--import", "https://config.url"])
        except ImportOptionError, error:
            self.assertIn("File contains no section headers.", str(error))
        else:
            self.fail("ImportOptionError not raised")

    def test_import_error_is_handled_nicely_by_main(self):
        fetch_mock = self.mocker.replace("landscape.lib.fetch.fetch")
        fetch_mock("https://config.url")
        self.mocker.throw(HTTPCodeError(404, ""))

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Fetching configuration from https://config.url...")
        print_text_mock(CONTAINS("Server returned HTTP code 404"), error=True)

        self.mocker.replay()

        system_exit = self.assertRaises(
            SystemExit, main, ["--import", "https://config.url"])
        self.assertEquals(system_exit.code, 1)

    def test_base64_ssl_public_key_is_exported_to_file(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.result(True)

        config_filename = self.makeFile("")
        key_filename = config_filename + ".ssl_public_key"
        self.addCleanup(os.remove, key_filename)

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Writing SSL public key to %s..." % key_filename)

        self.mocker.replay()

        config = self.get_config(["--silent", "-c", config_filename,
                                  "-u", "url", "-a", "account", "-t", "title",
                                  "--ssl-public-key", "base64:SGkgdGhlcmUh"])
        setup(config)

        self.assertTrue(os.path.isfile(key_filename))
        self.assertEquals(open(key_filename).read(), "Hi there!")

        options = ConfigParser()
        options.read(config_filename)
        self.assertEquals(options.get("client", "ssl_public_key"),
                          key_filename)

    def test_normal_ssl_public_key_is_not_exported_to_file(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        self.mocker.result(True)
        self.mocker.replay()

        config_filename = self.makeFile("")

        config = self.get_config(["--silent", "-c", config_filename,
                                  "-u", "url", "-a", "account", "-t", "title",
                                  "--ssl-public-key", "/some/filename"])
        setup(config)

        key_filename = config_filename + ".ssl_public_key"
        self.assertFalse(os.path.isfile(key_filename))

        options = ConfigParser()
        options.read(config_filename)
        self.assertEquals(options.get("client", "ssl_public_key"),
                          "/some/filename")

    # We test them individually since they must work individually.
    def test_import_from_url_honors_http_proxy(self):
        self.ensure_import_from_url_honors_proxy_options("http_proxy")

    def test_import_from_url_honors_https_proxy(self):
        self.ensure_import_from_url_honors_proxy_options("https_proxy")

    def ensure_import_from_url_honors_proxy_options(self, proxy_option):
        def check_proxy(url):
            self.assertEquals(os.environ.get(proxy_option), "http://proxy")

        fetch_mock = self.mocker.replace("landscape.lib.fetch.fetch")
        fetch_mock("https://config.url")
        self.mocker.call(check_proxy)

        # Doesn't matter.  We just want to check the context around it.
        self.mocker.result("")

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Fetching configuration from https://config.url...")

        self.mocker.replay()

        config_filename = self.makeFile("", basename="final_config")

        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--" + proxy_option.replace("_", "-"),
                             "http://proxy",
                             "--import", "https://config.url"])
        except ImportOptionError:
            pass # The returned content is empty.  We don't really
                 # care for this test.  Mocker will ensure the tests
                 # we care about are done.


class RegisterFunctionTest(LandscapeIsolatedTest):

    # Due to the way these tests run, the run() method on the reactor is called
    # *before* any of the remote methods (reload, register) are called, because
    # these tests "hold" the reactor until after the tests runs, then the
    # reactor is given back control of the process, *then* all the remote calls
    # in the dbus queue are fired.

    helpers = [RemoteBrokerHelper]

    def test_register_success(self):
        service = self.broker_service

        registration_mock = self.mocker.replace(service.registration)
        config_mock = self.mocker.replace(service.config)
        print_text_mock = self.mocker.replace(print_text)
        reactor_mock = self.mocker.proxy("twisted.internet.reactor")
        install_mock = self.mocker.replace("landscape.reactor.install")

        # This must necessarily happen in the following order.
        self.mocker.order()

        install_mock()

        # This very informative message is printed out.
        print_text_mock("Please wait... ", "")

        time_mock = self.mocker.replace("time")
        time_mock.sleep(ANY)
        self.mocker.count(1)

        reactor_mock.run()

        # After a nice dance the configuration is reloaded.
        config_mock.reload()

        # The register() method is called.  We fire the "registration-done"
        # event after it's done, so that it cascades into a deferred callback.

        def register_done(deferred_result):
            service.reactor.fire("registration-done")
        registration_mock.register()
        self.mocker.passthrough(register_done)

        # The deferred callback finally prints out this message.
        print_text_mock("System successfully registered.")

        result = Deferred()
        reactor_mock.stop()
        self.mocker.call(lambda: result.callback(None))

        # Nothing else is printed!
        print_text_mock(ANY)
        self.mocker.count(0)

        self.mocker.replay()

        # DO IT!
        register(service.config, reactor_mock)

        return result

    def test_register_failure(self):
        """
        When registration fails because of invalid credentials, a message will
        be printed to the console and the program will exit.
        """
        service = self.broker_service

        self.log_helper.ignore_errors(InvalidCredentialsError)
        registration_mock = self.mocker.replace(service.registration)
        config_mock = self.mocker.replace(service.config)
        print_text_mock = self.mocker.replace(print_text)
        reactor_mock = self.mocker.proxy("twisted.internet.reactor")
        install_mock = self.mocker.replace("landscape.reactor.install")

        # This must necessarily happen in the following order.
        self.mocker.order()

        install_mock()

        # This very informative message is printed out.
        print_text_mock("Please wait... ", "")

        time_mock = self.mocker.replace("time")
        time_mock.sleep(ANY)
        self.mocker.count(1)

        reactor_mock.run()

        # After a nice dance the configuration is reloaded.
        config_mock.reload()

        # The register() method is called.  We fire the "registration-failed"
        # event after it's done, so that it cascades into a deferred errback.
        def register_done(deferred_result):
            service.reactor.fire("registration-failed")
        registration_mock.register()
        self.mocker.passthrough(register_done)

        # The deferred errback finally prints out this message.
        print_text_mock("Invalid account name or registration password.",
                        error=True)

        result = Deferred()
        reactor_mock.stop()
        self.mocker.call(lambda: result.callback(None))

        # Nothing else is printed!
        print_text_mock(ANY)
        self.mocker.count(0)

        self.mocker.replay()

        # DO IT!
        register(service.config, reactor_mock)

        return result

    def test_register_exchange_failure(self):
        """
        When registration fails because the server couldn't be contacted, a
        message is printed and the program quits.
        """
        service = self.broker_service

        registration_mock = self.mocker.replace(service.registration)
        config_mock = self.mocker.replace(service.config)
        print_text_mock = self.mocker.replace(print_text)
        reactor_mock = self.mocker.proxy("twisted.internet.reactor")
        install_mock = self.mocker.replace("landscape.reactor.install")

        # This must necessarily happen in the following order.
        self.mocker.order()

        install_mock()

        # This very informative message is printed out.
        print_text_mock("Please wait... ", "")

        time_mock = self.mocker.replace("time")
        time_mock.sleep(ANY)
        self.mocker.count(1)

        reactor_mock.run()

        # After a nice dance the configuration is reloaded.
        config_mock.reload()

        def register_done(deferred_result):
            service.reactor.fire("exchange-failed")
        registration_mock.register()
        self.mocker.passthrough(register_done)

        # The deferred errback finally prints out this message.
        print_text_mock("We were unable to contact the server. "
                        "Your internet connection may be down. "
                        "The landscape client will continue to try and contact "
                        "the server periodically.",
                        error=True)


        result = Deferred()
        reactor_mock.stop()
        self.mocker.call(lambda: result.callback(None))

        # Nothing else is printed!
        print_text_mock(ANY)
        self.mocker.count(0)

        self.mocker.replay()

        # DO IT!
        register(service.config, reactor_mock)

        return result

    def test_register_timeout_failure(self):
        # XXX This test will take about 30 seconds to run on some versions of
        # dbus, as it really is waiting for the dbus call to timeout.  We can
        # remove it after it's possible for us to specify dbus timeouts on all
        # supported platforms (current problematic ones are edgy through gutsy)
        service = self.broker_service

        registration_mock = self.mocker.replace(service.registration)
        config_mock = self.mocker.replace(service.config)
        print_text_mock = self.mocker.replace(print_text)
        reactor_mock = self.mocker.proxy("twisted.internet.reactor")
        install_mock = self.mocker.replace("landscape.reactor.install")

        # This must necessarily happen in the following order.
        self.mocker.order()

        install_mock()

        # This very informative message is printed out.
        print_text_mock("Please wait... ", "")

        time_mock = self.mocker.replace("time")
        time_mock.sleep(ANY)
        self.mocker.count(1)

        reactor_mock.run()

        # After a nice dance the configuration is reloaded.
        config_mock.reload()

        registration_mock.register()
        self.mocker.passthrough()

        # Nothing else is printed!
        print_text_mock(ANY)
        self.mocker.count(0)

        self.mocker.replay()

        result = Deferred()

        reactor.addSystemEventTrigger("during",
                                      "landscape-registration-error",
                                      result.callback, None)
        # DO IT!
        register(service.config, reactor_mock)

        return result

    def test_register_bus_connection_failure(self):
        """
        If the bus can't be connected to, landscape-config will print an
        explanatory message and exit cleanly.
        """
        remote_broker_factory = self.mocker.replace(
            "landscape.broker.remote.RemoteBroker", passthrough=False)
        print_text_mock = self.mocker.replace(print_text)
        install_mock = self.mocker.replace("landscape.reactor.install")
        time_mock = self.mocker.replace("time")

        install_mock()
        print_text_mock(ARGS)
        time_mock.sleep(ANY)

        remote_broker_factory(ARGS, KWARGS)
        self.mocker.throw(DBusException)

        print_text_mock(
            CONTAINS("There was an error communicating with the "
                     "Landscape client"),
            error=True)
        print_text_mock(CONTAINS("This machine will be registered"), error=True)

        self.mocker.replay()
        config = get_config(self, ["-a", "accountname", "--silent"])
        system_exit = self.assertRaises(SystemExit, register, config)
        self.assertEquals(system_exit.code, 2)

    def test_register_bus_connection_failure_ok_no_register(self):
        """
        Exit code 0 will be returned if we can't contact Landscape via DBus and
        --ok-no-register was passed.
        """
        remote_broker_factory = self.mocker.replace(
            "landscape.broker.remote.RemoteBroker", passthrough=False)
        print_text_mock = self.mocker.replace(print_text)
        install_mock = self.mocker.replace("landscape.reactor.install")
        time_mock = self.mocker.replace("time")

        install_mock()
        print_text_mock(ARGS)
        time_mock.sleep(ANY)

        remote_broker_factory(ARGS, KWARGS)
        self.mocker.throw(DBusException)

        print_text_mock(
            CONTAINS("There was an error communicating with the "
                     "Landscape client"),
            error=True)
        print_text_mock(CONTAINS("This machine will be registered"), error=True)

        self.mocker.replay()
        config = get_config(self, ["-a", "accountname", "--silent",
                                   "--ok-no-register"])
        system_exit = self.assertRaises(SystemExit, register, config)
        self.assertEquals(system_exit.code, 0)


class RegisterFunctionNoServiceTest(LandscapeIsolatedTest):

    def setUp(self):
        super(RegisterFunctionNoServiceTest, self).setUp()
        self.configuration = LandscapeSetupConfiguration(None)
        # Let's not mess about with the system bus
        self.configuration.load_command_line(["--bus", "session"])

    def test_register_dbus_error(self):
        """
        When registration fails because of a DBUS error, a message is printed
        and the program exits.
        """
        print_text_mock = self.mocker.replace(print_text)
        reactor_mock = self.mocker.proxy("twisted.internet.reactor")
        install_mock = self.mocker.replace("landscape.reactor.install")

        install_mock()
        print_text_mock("Please wait... ", "")

        print_text_mock("Error occurred contacting Landscape Client. "
                        "Is it running?",
                        error=True)

        # WHOAH DUDE. This waits for callLater(0, reactor.stop).
        result = Deferred()
        reactor_mock.callLater(0, ANY)
        self.mocker.call(lambda seconds, thingy: thingy())
        reactor_mock.stop()
        self.mocker.call(lambda: result.callback(None))
        reactor_mock.run()

        self.mocker.replay()

        # DO IT!
        register(self.configuration, reactor_mock)

        return result

    def test_register_unknown_error(self):
        """
        When registration fails because of an unknown error, a message is
        printed and the program exits.
        """
        # We'll just mock the remote here to have it raise an exception.
        remote_broker_factory = self.mocker.replace(
            "landscape.broker.remote.RemoteBroker", passthrough=False)

        print_text_mock = self.mocker.replace(print_text)
        reactor_mock = self.mocker.proxy("twisted.internet.reactor")
        install_mock = self.mocker.replace("landscape.reactor.install")
        # This is unordered. It's just way too much of a pain.

        install_mock()
        print_text_mock("Please wait... ", "")
        time_mock = self.mocker.replace("time")
        time_mock.sleep(ANY)
        self.mocker.count(1)

        # SNORE
        remote_broker = remote_broker_factory(ANY, retry_timeout=0)
        self.mocker.result(succeed(None))
        remote_broker.reload_configuration()
        self.mocker.result(succeed(None))
        remote_broker.connect_to_signal(ARGS, KWARGS)
        self.mocker.result(succeed(None))
        self.mocker.count(3)

        # here it is!
        remote_broker.register()
        self.mocker.result(fail(ZeroDivisionError))

        print_text_mock(ANY, error=True)
        def check_logged_failure(text, error):
            self.assertTrue("ZeroDivisionError" in text)
        self.mocker.call(check_logged_failure)
        print_text_mock("Unknown error occurred.", error=True)

        # WHOAH DUDE. This waits for callLater(0, reactor.stop).
        result = Deferred()
        reactor_mock.callLater(0, ANY)
        self.mocker.call(lambda seconds, thingy: thingy())
        reactor_mock.stop()
        self.mocker.call(lambda: result.callback(None))

        reactor_mock.run()

        self.mocker.replay()

        register(self.configuration, reactor_mock)

        return result
