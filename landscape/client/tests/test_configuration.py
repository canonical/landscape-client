from __future__ import print_function

import mock
from functools import partial
import os
import sys
import unittest

from twisted.internet.defer import succeed, fail, Deferred
from twisted.python.compat import iteritems

from landscape.lib.compat import ConfigParser
from landscape.lib.compat import StringIO
from landscape.client.broker.registration import RegistrationError
from landscape.client.broker.tests.helpers import (
    RemoteBrokerHelper, BrokerConfigurationHelper)
from landscape.client.configuration import (
    print_text, LandscapeSetupScript, LandscapeSetupConfiguration,
    register, setup, main, setup_init_script_and_start_client,
    ConfigurationError, prompt_yes_no, show_help,
    ImportOptionError, store_public_key_data,
    bootstrap_tree, got_connection, success, failure, exchange_failure,
    handle_registration_errors, done, got_error, report_registration_outcome,
    determine_exit_code, is_registered)
from landscape.lib.amp import MethodCallError
from landscape.lib.fetch import HTTPCodeError, PyCurlError
from landscape.lib.fs import read_binary_file
from landscape.lib.persist import Persist
from landscape.lib.testing import EnvironSaverHelper
from landscape.client.sysvconfig import ProcessError
from landscape.client.tests.helpers import (
        LandscapeTest, FakeBrokerServiceHelper)


class LandscapeConfigurationTest(LandscapeTest):

    def get_config(self, args, data_path=None):
        if data_path is None:
            data_path = os.path.join(self.makeDir(), "client")

        if "--config" not in args and "-c" not in args:
            filename = self.makeFile("""
[client]
url = https://landscape.canonical.com/message-system
""")
            args.extend(["--config", filename, "--data-path", data_path])
        config = LandscapeSetupConfiguration()
        config.load(args)
        return config


class SuccessTests(unittest.TestCase):

    def test_success(self):
        """The success handler records the success."""
        results = []
        success(results.append)
        self.assertEqual(["success"], results)


class FailureTests(unittest.TestCase):

    def test_failure(self):
        """The failure handler records the failure and returns non-zero."""
        results = []
        self.assertNotEqual(0, failure(results.append, "an-error"))
        self.assertEqual(["an-error"], results)


class ExchangeFailureTests(unittest.TestCase):

    def test_exchange_failure_ssl(self):
        """The exchange_failure() handler records whether or not the failure
        involved SSL or not and returns non-zero."""
        results = []
        self.assertNotEqual(0,
                            exchange_failure(results.append, ssl_error=True))
        self.assertEqual(["ssl-error"], results)

    def test_exchange_failure_non_ssl(self):
        """
        The exchange_failure() handler records whether or not the failure
        involved SSL or not and returns non-zero.
        """
        results = []
        self.assertNotEqual(0,
                            exchange_failure(results.append, ssl_error=False))
        self.assertEqual(["non-ssl-error"], results)


class HandleRegistrationErrorsTests(unittest.TestCase):

    def test_handle_registration_errors_traps(self):
        """
        The handle_registration_errors() function traps RegistrationError
        and MethodCallError errors.
        """
        class FauxFailure(object):
            def trap(self, *trapped):
                self.trapped_exceptions = trapped

        faux_connector = FauxConnector()
        faux_failure = FauxFailure()

        results = []
        add_result = results.append

        self.assertNotEqual(
            0,
            handle_registration_errors(
                add_result, faux_failure, faux_connector))
        self.assertTrue(
            [RegistrationError, MethodCallError],
            faux_failure.trapped_exceptions)

    def test_handle_registration_errors_disconnects_cleanly(self):
        """
        The handle_registration_errors function disconnects the broker
        connector cleanly.
        """
        class FauxFailure(object):
            def trap(self, *trapped):
                pass

        faux_connector = FauxConnector()
        faux_failure = FauxFailure()

        results = []
        add_result = results.append

        self.assertNotEqual(
            0,
            handle_registration_errors(
                add_result, faux_failure, faux_connector))
        self.assertTrue(faux_connector.was_disconnected)

    def test_handle_registration_errors_as_errback(self):
        """
        The handle_registration_errors functions works as an errback.

        This test was put in place to assert the parameters passed to the
        function when used as an errback are in the correct order.
        """
        faux_connector = FauxConnector()
        calls = []

        def i_raise(result):
            calls.append(True)
            return RegistrationError("Bad mojo")

        results = []
        add_result = results.append

        deferred = Deferred()
        deferred.addCallback(i_raise)
        deferred.addErrback(
            partial(handle_registration_errors, add_result), faux_connector)
        deferred.callback("")  # This kicks off the callback chain.

        self.assertEqual([True], calls)


class DoneTests(unittest.TestCase):

    def test_done(self):
        """The done() function handles cleaning up."""
        class FauxConnector(object):
            was_disconnected = False

            def disconnect(self):
                self.was_disconnected = True

        class FauxReactor(object):
            was_stopped = False

            def stop(self):
                self.was_stopped = True

        faux_connector = FauxConnector()
        faux_reactor = FauxReactor()

        done(None, faux_connector, faux_reactor)
        self.assertTrue(faux_connector.was_disconnected)
        self.assertTrue(faux_reactor.was_stopped)


class GotErrorTests(unittest.TestCase):

    def test_got_error(self):
        """The got_error() function handles displaying errors and exiting."""
        class FauxFailure(object):

            def getTraceback(self):
                return "traceback"

        results = []
        printed = []

        def faux_print(text, file):
            printed.append((text, file))

        mock_reactor = mock.Mock()

        got_error(FauxFailure(), reactor=mock_reactor,
                  add_result=results.append, print=faux_print)
        mock_reactor.stop.assert_called_once_with()

        self.assertIsInstance(results[0], SystemExit)
        self.assertEqual([('traceback', sys.stderr)], printed)


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
        comparisons = [("Y", True),
                       ("y", True),
                       ("yEs", True),
                       ("YES", True),
                       ("n", False),
                       ("N", False),
                       ("No", False),
                       ("no", False),
                       ("", True)]

        for input_string, result in comparisons:
            with mock.patch("landscape.client.configuration.input",
                            return_value=input_string) as mock_input:
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
        super(LandscapeSetupScriptTest, self).setUp()
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

    @mock.patch("landscape.client.configuration.input",
                side_effect=("", "Desktop"))
    @mock.patch("landscape.client.configuration.show_help")
    def test_prompt_with_required(self, mock_show_help, mock_input):
        self.script.prompt("computer_title", "Message", True)
        mock_show_help.assert_called_once_with(
            "This option is required to configure Landscape.")

        calls = [mock.call("Message: "), mock.call("Message: ")]
        mock_input.assert_has_calls(calls)

        self.assertEqual(self.config.computer_title, "Desktop")

    @mock.patch("landscape.client.configuration.input", return_value="")
    def test_prompt_with_required_and_default(self, mock_input):
        self.config.computer_title = "Desktop"
        self.script.prompt("computer_title", "Message", True)
        mock_input.assert_called_once_with("Message [Desktop]: ")
        self.assertEqual(self.config.computer_title, "Desktop")

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

    @mock.patch("landscape.client.configuration.getpass.getpass",
                side_effect=("password", "password"))
    def test_password_prompt_simple_matching(self, mock_getpass):
        self.script.password_prompt("registration_key", "Password")
        calls = [mock.call("Password: "), mock.call("Please confirm: ")]
        mock_getpass.assert_has_calls(calls)
        self.assertEqual(self.config.registration_key, "password")

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.getpass.getpass",
                side_effect=("password", "", "password", "password"))
    def test_password_prompt_simple_non_matching(self, mock_getpass,
                                                 mock_show_help):
        self.script.password_prompt("registration_key", "Password")

        calls = [mock.call("Password: "), mock.call("Please confirm: "),
                 mock.call("Password: "), mock.call("Please confirm: ")]
        mock_getpass.assert_has_calls(calls)
        mock_show_help.assert_called_once_with("Keys must match.")
        self.assertEqual(self.config.registration_key, "password")

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.getpass.getpass",
                side_effect=("", "password", "password"))
    def test_password_prompt_simple_matching_required(self, mock_getpass,
                                                      mock_show_help):
        self.script.password_prompt("registration_key", "Password", True)

        calls = [mock.call("Password: "), mock.call("Password: "),
                 mock.call("Please confirm: ")]
        mock_getpass.assert_has_calls(calls)
        mock_show_help.assert_called_once_with(
            "This option is required to configure Landscape.")
        self.assertEqual(self.config.registration_key, "password")

    @mock.patch("landscape.client.configuration.show_help")
    def test_query_computer_title(self, mock_show_help):
        help_snippet = "The computer title you"
        self.script.prompt = mock.Mock()
        self.script.query_computer_title()
        self.script.prompt.assert_called_once_with(
            "computer_title", "This computer's title", True)
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.input")
    def test_query_computer_title_defined_on_command_line(
            self, mock_input):
        self.config.load_command_line(["-t", "Computer title"])
        self.script.query_computer_title()
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.show_help")
    def test_query_account_name(self, mock_show_help):
        help_snippet = "You must now specify the name of the Landscape account"
        self.script.prompt = mock.Mock()
        self.script.query_account_name()
        self.script.prompt.assert_called_once_with(
            "account_name", "Account name", True)
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
            "registration_key", "Account registration key")
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.getpass.getpass")
    def test_query_registration_key_defined_on_command_line(
            self, mock_getpass):
        self.config.load_command_line(["-p", "shared-secret"])
        self.script.query_registration_key()
        mock_getpass.assert_not_called()

    @mock.patch("landscape.client.configuration.show_help")
    def test_query_proxies(self, mock_show_help):
        help_snippet = "The Landscape client communicates"
        self.script.prompt = mock.Mock()

        self.script.query_proxies()
        calls = [mock.call("http_proxy", "HTTP proxy URL"),
                 mock.call("https_proxy", "HTTPS proxy URL")]
        self.script.prompt.assert_has_calls(calls)
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.input")
    def test_query_proxies_defined_on_command_line(self, mock_input):
        self.config.load_command_line(["--http-proxy", "localhost:8080",
                                       "--https-proxy", "localhost:8443"])
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
            "http_proxy", "HTTP proxy URL")
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.prompt_yes_no",
                return_value=False)
    def test_query_script_plugin_no(self, mock_prompt_yes_no, mock_show_help):
        help_snippet = "Landscape has a feature which enables administrators"

        self.script.query_script_plugin()
        self.assertEqual(self.config.include_manager_plugins, "")
        mock_prompt_yes_no.assert_called_once_with(
            "Enable script execution?", default=False)
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.prompt_yes_no",
                return_value=True)
    def test_query_script_plugin_yes(self, mock_prompt_yes_no, mock_show_help):
        """
        If the user *does* want script execution, then the script asks which
        users to enable it for.
        """
        help_snippet = "Landscape has a feature which enables administrators"
        self.script.prompt = mock.Mock()

        self.script.query_script_plugin()
        mock_prompt_yes_no.assert_called_once_with(
            "Enable script execution?", default=False)
        first_call, second_call = mock_show_help.mock_calls
        self.assertTrue(first_call.strip().startswith(help_snippet))
        self.assertTrue(second_call.strip().startswith(
            "By default, scripts are restricted"))

        self.script.prompt.assert_called_once_with(
            "script_users", "Script users")
        self.assertEqual(self.config.include_manager_plugins,
                         "ScriptExecution")

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.prompt_yes_no",
                return_value=False)
    def test_disable_script_plugin(self, mock_prompt_yes_no, mock_show_help):
        """
        Answering NO to enabling the script plugin while it's already enabled
        will disable it.
        """
        self.config.include_manager_plugins = "ScriptExecution"
        help_snippet = "Landscape has a feature which enables administrators"

        self.script.query_script_plugin()
        mock_prompt_yes_no.assert_called_once_with(
            "Enable script execution?", default=True)
        self.assertEqual(self.config.include_manager_plugins, "")
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.prompt_yes_no",
                return_value=False)
    def test_disabling_script_plugin_leaves_existing_inclusions(
            self, mock_prompt_yes_no, mock_show_help):
        """
        Disabling the script execution plugin doesn't remove other included
        plugins.
        """
        self.config.include_manager_plugins = "FooPlugin, ScriptExecution"

        self.script.query_script_plugin()
        mock_prompt_yes_no.assert_called_once_with(
            "Enable script execution?", default=True)
        self.assertEqual(self.config.include_manager_plugins, "FooPlugin")
        mock_show_help.assert_called_once_with(mock.ANY)

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.prompt_yes_no",
                return_value=True)
    def test_enabling_script_plugin_leaves_existing_inclusions(
            self, mock_prompt_yes_no, mock_show_help):
        """
        Enabling the script execution plugin doesn't remove other included
        plugins.
        """
        self.config.include_manager_plugins = "FooPlugin"

        self.script.prompt = mock.Mock()

        self.script.query_script_plugin()
        mock_prompt_yes_no.assert_called_once_with(
            "Enable script execution?", default=False)

        self.script.prompt.assert_called_once_with(
            "script_users", "Script users")
        self.assertEqual(2, mock_show_help.call_count)
        self.assertEqual(self.config.include_manager_plugins,
                         "FooPlugin, ScriptExecution")

    @mock.patch("landscape.client.configuration.input")
    def test_query_script_plugin_defined_on_command_line(self, mock_input):
        self.config.load_command_line(
            ["--include-manager-plugins", "ScriptExecution",
             "--script-users", "root, nobody"])
        self.script.query_script_plugin()
        mock_input.assert_not_called()
        self.assertEqual(self.config.include_manager_plugins,
                         "ScriptExecution")
        self.assertEqual(self.config.script_users, "root, nobody")

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.prompt_yes_no",
                return_value=True)
    def test_query_script_manager_plugins_defined_on_command_line(
            self, mock_prompt_yes_no, mock_show_help):
        self.script.prompt = mock.Mock()

        self.config.load_command_line(
            ["--include-manager-plugins", "FooPlugin, ScriptExecution"])
        self.script.query_script_plugin()
        self.script.prompt.assert_called_once_with(
            "script_users", "Script users")
        self.assertEqual(2, mock_show_help.call_count)
        self.assertEqual(self.config.include_manager_plugins,
                         "FooPlugin, ScriptExecution")

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.prompt_yes_no",
                return_value=True)
    @mock.patch("landscape.client.configuration.pwd.getpwnam",
                return_value=None)
    def test_query_script_users_defined_on_command_line(self, mock_getpwnam,
                                                        mock_prompt_yes_no,
                                                        mock_show_help):
        """
        Confirm with the user for users specified for the ScriptPlugin.
        """
        self.script.prompt_get_input = mock.Mock(return_value=None)

        self.config.include_manager_plugins = "FooPlugin"

        self.config.load_command_line(
            ["--script-users", "root, nobody, landscape"])
        self.script.query_script_plugin()

        mock_getpwnam.assert_called_with("landscape")
        mock_prompt_yes_no.assert_called_once_with(
            "Enable script execution?", default=False)
        self.script.prompt_get_input.assert_called_once_with(
            "Script users [root, nobody, landscape]: ", False)
        self.assertEqual(2, mock_show_help.call_count)
        self.assertEqual(self.config.script_users,
                         "root, nobody, landscape")

    @mock.patch("landscape.client.configuration.pwd.getpwnam",
                side_effect=(None, None, None, KeyError()))
    def test_query_script_users_on_command_line_with_unknown_user(
            self, mock_getpwnam):
        """
        If several users are provided on the command line, we verify the users
        and raise a ConfigurationError if any are unknown on this system.
        """
        self.config.load_command_line(
            ["--script-users", "root, nobody, landscape, unknown",
             "--include-manager-plugins", "ScriptPlugin"])
        self.assertRaises(ConfigurationError, self.script.query_script_plugin)
        calls = [mock.call("root"), mock.call("nobody"),
                 mock.call("landscape"), mock.call("unknown")]
        mock_getpwnam.assert_has_calls(calls)

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
        self.assertEqual(self.config.script_users, "ALL")

    def test_query_script_users_command_line_with_ALL_and_extra_user(self):
        """
        If ALL and additional users are provided as the users on the command
        line, this should raise an appropriate ConfigurationError.
        """
        self.config.load_command_line(
            ["--script-users", "ALL, kevin",
             "--include-manager-plugins", "ScriptPlugin"])
        self.assertRaises(ConfigurationError, self.script.query_script_plugin)

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.prompt_yes_no",
                return_value=True)
    def test_invalid_user_entered_by_user(self, mock_prompt_yes_no,
                                          mock_show_help):
        """
        If an invalid user is entered on the command line the user should be
        informed and prompted again.
        """
        help_snippet = "Landscape has a feature which enables administrators"
        self.script.prompt_get_input = mock.Mock(
            side_effect=(u"nonexistent", u"root"))

        self.script.query_script_plugin()
        self.assertEqual(self.config.script_users, "root")
        first_call, second_call, third_call = mock_show_help.mock_calls
        self.assertTrue(first_call.strip().startswith(help_snippet))
        self.assertTrue(second_call.strip().startswith(
            "By default, scripts are restricted"))
        self.assertTrue(third_call.strip().startswith(
            "Unknown system users: nonexistsent"))

    @mock.patch("landscape.client.configuration.show_help")
    def test_tags_not_defined_on_command_line(self, mock_show_help):
        """
        If tags are not provided, the user should be prompted for them.
        """
        help_snippet = ("You may provide tags for this computer e.g. "
                        "server,precise.")
        self.script.prompt = mock.Mock()

        self.script.query_tags()
        self.script.prompt.assert_called_once_with(
            "tags", "Tags", False)
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    @mock.patch("landscape.client.configuration.show_help")
    @mock.patch("landscape.client.configuration.prompt_yes_no")
    def test_invalid_tags_entered_by_user(self, mock_prompt_yes_no,
                                          mock_show_help):
        """
        If tags are not provided, the user should be prompted for them, and
        they should be valid tags, if not the user should be prompted for them
        again.
        """
        self.script.prompt_get_input = mock.Mock(
            side_effect=(u"<script>alert();</script>", u"london"))

        self.script.query_tags()
        first_call, second_call = mock_show_help.mock_calls
        self.assertTrue(
            first_call.strip().startswith("You may provide tags for this "
                                          "computer e.g. server,precise."))
        self.assertTrue(
            second_call.strip().startswith("Tag names may only contain "
                                           "alphanumeric characters."))
        calls = [("Tags: ", False), ("Tags: ", False)]
        self.script.prompt_get_input.has_calls(calls)

    @mock.patch("landscape.client.configuration.input")
    def test_tags_defined_on_command_line(self, mock_input):
        """
        Tags defined on the command line can be verified by the user.
        """
        self.config.load_command_line(["--tags", u"server,london"])
        self.script.query_tags()
        self.assertEqual(self.config.tags, u"server,london")
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.input")
    def test_invalid_tags_defined_on_command_line_raises_error(
            self, mock_input):
        """
        Invalid tags on the command line raises a ConfigurationError.
        """
        self.config.load_command_line(["--tags", u"<script>alert();</script>"])
        self.assertRaises(ConfigurationError, self.script.query_tags)
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.show_help")
    def test_access_group_not_defined_on_command_line(self, mock_show_help):
        """
        If an access group is not provided, the user should be prompted for it.
        """
        help_snippet = ("You may provide an access group for this computer "
                        "e.g. webservers.")
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
        self.config.load_command_line(["--access-group", u"webservers"])
        self.script.query_access_group()
        self.assertEqual(self.config.access_group, u"webservers")
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.input")
    def test_stagger_defined_on_command_line(self, mock_input):
        self.assertEqual(self.config.stagger_launch, 0.1)
        self.config.load_command_line(["--stagger-launch", "0.5"])
        self.assertEqual(self.config.stagger_launch, 0.5)
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.show_help")
    def test_show_header(self, mock_show_help):
        help_snippet = "This script will"
        self.script.show_header()
        [call] = mock_show_help.mock_calls
        self.assertTrue(call.strip().startswith(help_snippet))

    def test_run(self):
        self.script.show_header = mock.Mock()
        self.script.query_computer_title = mock.Mock()
        self.script.query_account_name = mock.Mock()
        self.script.query_registration_key = mock.Mock()
        self.script.query_proxies = mock.Mock()
        self.script.query_script_plugin = mock.Mock()
        self.script.query_access_group = mock.Mock()
        self.script.query_tags = mock.Mock()
        self.script.run()

        self.script.show_header.assert_called_once_with()
        self.script.query_computer_title.assert_called_once_with()
        self.script.query_account_name.assert_called_once_with()
        self.script.query_registration_key.assert_called_once_with()
        self.script.query_proxies.assert_called_once_with()
        self.script.query_script_plugin.assert_called_once_with()
        self.script.query_access_group.assert_called_once_with()
        self.script.query_tags.assert_called_once_with()


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
        super(ConfigurationFunctionsTest, self).setUp()
        getuid_patcher = mock.patch("os.getuid", return_value=0)
        bootstrap_tree_patcher = mock.patch(
            "landscape.client.configuration.bootstrap_tree")
        self.mock_getuid = getuid_patcher.start()
        self.mock_bootstrap_tree = bootstrap_tree_patcher.start()

        def cleanup():
            getuid_patcher.stop()
            bootstrap_tree_patcher.stop()
        self.addCleanup(cleanup)

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

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.getpass.getpass")
    @mock.patch("landscape.client.configuration.input")
    def test_setup(self, mock_input, mock_getpass, mock_print_text):
        filename = self.makeFile("[client]\n"
                                 "computer_title = Old Title\n"
                                 "account_name = Old Name\n"
                                 "registration_key = Old Password\n"
                                 "http_proxy = http://old.proxy\n"
                                 "https_proxy = https://old.proxy\n"
                                 "url = http://url\n"
                                 "include_manager_plugins = ScriptExecution\n"
                                 "access_group = webservers\n"
                                 "tags = london, server")

        def side_effect_input(prompt):
            fixtures = {
                "[Old Title]": "New Title",
                "[Old Name]": "New Name",
                "[http://old.proxy]": "http://new.proxy",
                "[https://old.proxy]": "https://new.proxy",
                "Enable script execution? [Y/n]": "n",
                "Access group [webservers]: ": u"databases",
                "Tags [london, server]: ": u"glasgow, laptop",
            }
            for key, value in iteritems(fixtures):
                if key in prompt:
                    return value
            raise KeyError("Couldn't find answer for {}".format(prompt))

        def side_effect_getpass(prompt):
            fixtures = {"Account registration key:": "New Password",
                        "Please confirm:": "New Password"}
            for key, value in iteritems(fixtures):
                if key in prompt:
                    return value
            raise KeyError("Couldn't find answer for {}".format(prompt))

        mock_input.side_effect = side_effect_input
        mock_getpass.side_effect = side_effect_getpass

        config = self.get_config(["--no-start", "--config", filename])
        setup(config)
        self.assertEqual(type(config), LandscapeSetupConfiguration)

        # Reload it to ensure it was written down.
        config.reload()

        self.assertEqual(config.computer_title, "New Title")
        self.assertEqual(config.account_name, "New Name")
        self.assertEqual(config.registration_key, "New Password")
        self.assertEqual(config.http_proxy, "http://new.proxy")
        self.assertEqual(config.https_proxy, "https://new.proxy")
        self.assertEqual(config.include_manager_plugins, "")
        self.assertEqual(config.access_group, u"databases")
        self.assertEqual(config.tags, u"glasgow, laptop")

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_silent_setup(self, mock_sysvconfig):
        """
        Only command-line options are used in silent mode and registration is
        attempted.
        """
        config = self.get_config(["--silent", "-a", "account", "-t", "rex"])
        setup(config)
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()
        self.assertConfigEqual(self.get_content(config), """\
[client]
computer_title = rex
data_path = %s
account_name = account
url = https://landscape.canonical.com/message-system
""" % config.data_path)

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_silent_setup_no_register(self, mock_sysvconfig):
        """
        Called with command line options to write a config file but no
        registration or validation of parameters is attempted.
        """
        config = self.get_config(["--silent", "--no-start"])
        setup(config)
        self.assertConfigEqual(self.get_content(config), """\
[client]
data_path = %s
url = https://landscape.canonical.com/message-system
""" % config.data_path)

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_silent_setup_no_register_with_default_preseed_params(
            self, mock_sysvconfig):
        """
        Make sure that the configuration can be used to write the
        configuration file after a fresh install.
        """
        args = ["--silent", "--no-start",
                "--computer-title", "",
                "--account-name", "",
                "--registration-key", "",
                "--url", "https://landscape.canonical.com/message-system",
                "--exchange-interval", "900",
                "--urgent-exchange-interval", "60",
                "--ping-url", "http://landscape.canonical.com/ping",
                "--ping-interval", "30",
                "--http-proxy", "",
                "--https-proxy", "",
                "--tags", ""]
        config = self.get_config(args)
        setup(config)
        self.assertConfigEqual(
            self.get_content(config),
            "[client]\n"
            "http_proxy = \n"
            "tags = \n"
            "data_path = %s\n"
            "registration_key = \n"
            "account_name = \n"
            "computer_title = \n"
            "https_proxy = \n"
            "url = https://landscape.canonical.com/message-system\n"
            "exchange_interval = 900\n"
            "ping_interval = 30\n"
            "ping_url = http://landscape.canonical.com/ping\n"
            "urgent_exchange_interval = 60\n" % config.data_path)

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_silent_setup_without_computer_title(
            self, mock_sysvconfig):
        """A computer title is required."""
        config = self.get_config(["--silent", "-a", "account"])
        self.assertRaises(ConfigurationError, setup, config)

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_silent_setup_without_account_name(
            self, mock_sysvconfig):
        """An account name is required."""
        config = self.get_config(["--silent", "-t", "rex"])
        self.assertRaises(ConfigurationError, setup, config)
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(
            True)

    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_silent_script_users_imply_script_execution_plugin(
            self, mock_sysvconfig, mock_input):
        """
        If C{--script-users} is specified, without C{ScriptExecution} in the
        list of manager plugins, it will be automatically added.
        """
        filename = self.makeFile("""
[client]
url = https://localhost:8080/message-system
bus = session
""")

        config = self.get_config(["--config", filename, "--silent",
                                  "-a", "account", "-t", "rex",
                                  "--script-users", "root, nobody"])
        mock_sysvconfig().restart_landscape.return_value = True
        setup(config)
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(
            True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()
        mock_input.assert_not_called()
        parser = ConfigParser()
        parser.read(filename)
        self.assertEqual(
            {"url": "https://localhost:8080/message-system",
             "bus": "session",
             "computer_title": "rex",
             "include_manager_plugins": "ScriptExecution",
             "script_users": "root, nobody",
             "account_name": "account"},
            dict(parser.items("client")))

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_silent_script_users_with_all_user(self, mock_sysvconfig):
        """
        In silent mode, we shouldn't accept invalid users, it should raise a
        configuration error.
        """
        config = self.get_config(
            ["--script-users", "all",
             "--include-manager-plugins", "ScriptPlugin",
             "-a", "account",
             "-t", "rex",
             "--silent"])
        self.assertRaises(ConfigurationError, setup, config)
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(
            True)

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_silent_setup_with_ping_url(self, mock_sysvconfig):
        mock_sysvconfig().restart_landscape.return_value = True
        filename = self.makeFile("""
[client]
ping_url = http://landscape.canonical.com/ping
registration_key = shared-secret
log_level = debug
random_key = random_value
""")

        config = self.get_config(["--config", filename, "--silent",
                                  "-a", "account", "-t", "rex",
                                  "--ping-url", "http://localhost/ping"])
        setup(config)
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(
            True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()

        parser = ConfigParser()
        parser.read(filename)
        self.assertEqual(
            {"log_level": "debug",
             "registration_key": "shared-secret",
             "ping_url": "http://localhost/ping",
             "random_key": "random_value",
             "computer_title": "rex",
             "account_name": "account"},
            dict(parser.items("client")))

    @mock.patch("landscape.client.configuration.LandscapeSetupScript")
    def test_setup_with_proxies_from_environment(self, mock_setup_script):
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"

        filename = self.makeFile("[client]\n"
                                 "url = http://url\n")

        config = self.get_config(["--no-start", "--config", filename])
        setup(config)

        # Reload it to ensure it was written down.
        config.reload()

        mock_setup_script().run.assert_called_once_with()

        self.assertEqual(config.http_proxy, "http://environ")
        self.assertEqual(config.https_proxy, "https://environ")

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_silent_setup_with_proxies_from_environment(
            self, mock_sysvconfig):
        """
        Only command-line options are used in silent mode and registration is
        attempted.
        """
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"

        filename = self.makeFile("""
[client]
registration_key = shared-secret
""")
        config = self.get_config(["--config", filename, "--silent",
                                  "-a", "account", "-t", "rex"])
        setup(config)
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()
        parser = ConfigParser()
        parser.read(filename)
        self.assertEqual(
            {"registration_key": "shared-secret",
             "http_proxy": "http://environ",
             "https_proxy": "https://environ",
             "computer_title": "rex",
             "account_name": "account"},
            dict(parser.items("client")))

    @mock.patch("landscape.client.configuration.LandscapeSetupScript")
    def test_setup_prefers_proxies_from_config_over_environment(
            self, mock_setup_script):
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"

        filename = self.makeFile("[client]\n"
                                 "http_proxy = http://config\n"
                                 "https_proxy = https://config\n"
                                 "url = http://url\n")

        config = self.get_config(["--no-start", "--config", filename])
        setup(config)
        mock_setup_script().run.assert_called_once_with()

        # Reload it to enusre it was written down.
        config.reload()

        self.assertEqual(config.http_proxy, "http://config")
        self.assertEqual(config.https_proxy, "https://config")

    @mock.patch("landscape.client.configuration.input", return_value="n")
    @mock.patch("landscape.client.configuration.register")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_no_registration(
            self, mock_setup, mock_register, mock_input):
        main(["-c", self.make_working_config()], print=noop_print)
        mock_register.assert_not_called()
        mock_input.assert_called_once_with(
            "\nRequest a new registration for this computer now? [Y/n]: ")

    @mock.patch("landscape.client.configuration.register",
                return_value="success")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_silent(self, mock_setup, mock_register):
        """
        In silent mode, the client should register when the registration
        details are changed/set.
        """
        config_filename = self.makeFile(
            "[client]\n"
            "computer_title = Old Title\n"
            "account_name = Old Name\n"
            "registration_key = Old Password\n"
            )

        exception = self.assertRaises(
            SystemExit, main, ["-c", config_filename, "--silent"],
            print=noop_print)
        self.assertEqual(0, exception.code)
        mock_setup.assert_called_once_with(mock.ANY)
        mock_register.assert_called_once_with(mock.ANY, mock.ANY)

    @mock.patch("landscape.client.configuration.input", return_value="y")
    @mock.patch("landscape.client.configuration.register",
                return_value="success")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_user_interaction_success(
            self, mock_setup, mock_register, mock_input):
        """The successful result of register() is communicated to the user."""
        printed = []

        def faux_print(string, file=sys.stdout):
            printed.append((string, file))

        exception = self.assertRaises(
            SystemExit, main, ["-c", self.make_working_config()],
            print=faux_print)
        self.assertEqual(0, exception.code)
        mock_setup.assert_called_once_with(mock.ANY)
        mock_register.assert_called_once_with(mock.ANY, mock.ANY)
        mock_input.assert_called_once_with(
            "\nRequest a new registration for this computer now? [Y/n]: ")
        self.assertEqual(
            [("Please wait...", sys.stdout),
             ("System successfully registered.", sys.stdout)],
            printed)

    @mock.patch("landscape.client.configuration.input", return_value="y")
    @mock.patch("landscape.client.configuration.register",
                return_value="unknown-account")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_user_interaction_failure(
            self, mock_setup, mock_register, mock_input):
        """The failed result of register() is communicated to the user."""
        printed = []

        def faux_print(string, file=sys.stdout):
            printed.append((string, file))

        exception = self.assertRaises(
            SystemExit, main, ["-c", self.make_working_config()],
            print=faux_print)
        self.assertEqual(2, exception.code)
        mock_setup.assert_called_once_with(mock.ANY)
        mock_register.assert_called_once_with(mock.ANY, mock.ANY)
        mock_input.assert_called_once_with(
            "\nRequest a new registration for this computer now? [Y/n]: ")

        # Note that the error is output via sys.stderr.
        self.assertEqual(
            [("Please wait...", sys.stdout),
             ("Invalid account name or registration key.", sys.stderr)],
            printed)

    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.register",
                return_value="success")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_user_interaction_success_silent(
            self, mock_setup, mock_register, mock_input):
        """A successful result is communicated to the user even with --silent.
        """
        printed = []

        def faux_print(string, file=sys.stdout):
            printed.append((string, file))

        exception = self.assertRaises(
            SystemExit, main, ["--silent", "-c", self.make_working_config()],
            print=faux_print)
        self.assertEqual(0, exception.code)
        mock_setup.assert_called_once_with(mock.ANY)
        mock_register.assert_called_once_with(mock.ANY, mock.ANY)
        mock_input.assert_not_called()

        self.assertEqual(
            [("Please wait...", sys.stdout),
             ("System successfully registered.", sys.stdout)],
            printed)

    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.register",
                return_value="unknown-account")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_user_interaction_failure_silent(
            self, mock_setup, mock_register, mock_input):
        """
        A failure result is communicated to the user even with --silent.
        """
        printed = []

        def faux_print(string, file=sys.stdout):
            printed.append((string, file))

        exception = self.assertRaises(
            SystemExit, main, ["--silent", "-c", self.make_working_config()],
            print=faux_print)
        self.assertEqual(2, exception.code)
        mock_setup.assert_called_once_with(mock.ANY)
        mock_register.assert_called_once_with(mock.ANY, mock.ANY)
        mock_input.assert_not_called()
        # Note that the error is output via sys.stderr.
        self.assertEqual(
            [("Please wait...", sys.stdout),
             ("Invalid account name or registration key.", sys.stderr)],
            printed)

    def make_working_config(self):
        data_path = self.makeFile()
        return self.makeFile("[client]\n"
                             "computer_title = Old Title\n"
                             "account_name = Old Name\n"
                             "registration_key = Old Password\n"
                             "http_proxy = http://old.proxy\n"
                             "https_proxy = https://old.proxy\n"
                             "data_path = {}\n"
                             "url = http://url\n".format(data_path))

    @mock.patch("landscape.client.configuration.input", return_value="")
    @mock.patch("landscape.client.configuration.register")
    @mock.patch("landscape.client.configuration.LandscapeSetupScript")
    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_register(
            self, mock_sysvconfig, mock_setup_script, mock_register,
            mock_input):
        mock_sysvconfig().is_configured_to_run.return_value = False
        self.assertRaises(
            SystemExit, main, ["--config", self.make_working_config()],
            print=noop_print)
        mock_sysvconfig().is_configured_to_run.assert_called_once_with()
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()
        mock_setup_script().run.assert_called_once_with()
        mock_register.assert_called_once_with(mock.ANY, mock.ANY)
        mock_input.assert_any_call(
            "\nThe Landscape client must be started "
            "on boot to operate correctly.\n\n"
            "Start Landscape client on boot? [Y/n]: ")
        mock_input.assert_called_with(
            "\nRequest a new registration for this computer now? [Y/n]: ")

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_errors_from_restart_landscape(
            self, mock_sysvconfig, mock_print_text):
        """
        If a ProcessError exception is raised from restart_landscape (because
        the client failed to be restarted), an informative message is printed
        and the script exits.
        """
        mock_sysvconfig().restart_landscape.side_effect = ProcessError()

        config = self.get_config(["--silent", "-a", "account", "-t", "rex"])
        system_exit = self.assertRaises(SystemExit, setup, config)
        self.assertEqual(system_exit.code, 2)
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()
        mock_print_text.assert_any_call(
            "Couldn't restart the Landscape client.", error=True)
        mock_print_text.assert_called_with(
            "This machine will be registered with the provided details when "
            "the client runs.", error=True)

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_errors_from_restart_landscape_ok_no_register(
            self, mock_sysvconfig, mock_print_text):
        """
        Exit code 0 will be returned if the client fails to be restarted and
        --ok-no-register was passed.
        """
        mock_sysvconfig().restart_landscape.side_effect = ProcessError()

        config = self.get_config(["--silent", "-a", "account", "-t", "rex",
                                  "--ok-no-register"])
        system_exit = self.assertRaises(SystemExit, setup, config)
        self.assertEqual(system_exit.code, 0)
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()
        mock_print_text.assert_any_call(
            "Couldn't restart the Landscape client.", error=True)
        mock_print_text.assert_called_with(
            "This machine will be registered with the provided details when "
            "the client runs.", error=True)

    @mock.patch("landscape.client.configuration.input", return_value="")
    @mock.patch("landscape.client.configuration.register")
    @mock.patch("landscape.client.configuration.setup")
    def test_main_with_register(
            self, mock_setup, mock_register, mock_input):
        self.assertRaises(SystemExit, main, ["-c", self.make_working_config()],
                          print=noop_print)
        mock_setup.assert_called_once_with(mock.ANY)
        mock_register.assert_called_once_with(mock.ANY, mock.ANY)
        mock_input.assert_called_once_with(
            "\nRequest a new registration for this computer now? [Y/n]: ")

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_setup_init_script_and_start_client(
            self, mock_sysvconfig):
        setup_init_script_and_start_client()
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)

    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_setup_init_script_and_start_client_silent(
            self, mock_sysvconfig, mock_input):
        setup_init_script_and_start_client()
        mock_input.assert_not_called()
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)

    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.register")
    @mock.patch("landscape.client.configuration.setup")
    def test_register_silent(
            self, mock_setup, mock_register, mock_input):
        """
        Silent registration uses specified configuration to attempt a
        registration with the server.
        """
        self.assertRaises(
            SystemExit, main, ["--silent", "-c", self.make_working_config()],
            print=noop_print)
        mock_setup.assert_called_once_with(mock.ANY)
        mock_register.assert_called_once_with(mock.ANY, mock.ANY)
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.input")
    @mock.patch("landscape.client.configuration.register")
    @mock.patch(
        "landscape.client.configuration.stop_client_and_disable_init_script")
    def test_disable(
            self, mock_stop_client, mock_register, mock_input):
        main(["--disable", "-c", self.make_working_config()])
        mock_stop_client.assert_called_once_with()
        mock_register.assert_not_called()
        mock_input.assert_not_called()

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_stop_client_and_disable_init_scripts(self, mock_sysvconfig):
        main(["--disable", "-c", self.make_working_config()])
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(False)
        mock_sysvconfig().stop_landscape.assert_called_once_with()

    def test_non_root(self):
        self.mock_getuid.return_value = 1000
        sys_exit = self.assertRaises(SystemExit,
                                     main, ["-c", self.make_working_config()])
        self.mock_getuid.assert_called_once_with()
        self.assertIn("landscape-config must be run as root", str(sys_exit))

    @mock.patch("sys.stdout", new_callable=StringIO)
    def test_main_with_help_and_non_root(self, mock_stdout):
        """It's possible to call 'landscape-config --help' as normal user."""
        self.mock_getuid.return_value = 1000
        self.assertRaises(SystemExit, main, ["--help"])
        self.assertIn(
            "show this help message and exit", mock_stdout.getvalue())

    @mock.patch("sys.stdout", new_callable=StringIO)
    def test_main_with_help_and_non_root_short(self, mock_stdout):
        """It's possible to call 'landscape-config -h' as normal user."""
        self.mock_getuid.return_value = 1000
        self.assertRaises(SystemExit, main, ["-h"])
        self.assertIn(
            "show this help message and exit", mock_stdout.getvalue())

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_import_from_file(self, mock_sysvconfig):
        configuration = (
            "[client]\n"
            "computer_title = New Title\n"
            "account_name = New Name\n"
            "registration_key = New Password\n"
            "http_proxy = http://new.proxy\n"
            "https_proxy = https://new.proxy\n"
            "url = http://new.url\n")

        import_filename = self.makeFile(configuration,
                                        basename="import_config")
        config_filename = self.makeFile("", basename="final_config")

        config = self.get_config(["--config", config_filename, "--silent",
                                  "--import", import_filename])
        setup(config)

        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()

        options = ConfigParser()
        options.read(config_filename)

        self.assertEqual(dict(options.items("client")),
                         {"computer_title": "New Title",
                          "account_name": "New Name",
                          "registration_key": "New Password",
                          "http_proxy": "http://new.proxy",
                          "https_proxy": "https://new.proxy",
                          "url": "http://new.url"})

    def test_import_from_empty_file(self):
        config_filename = self.makeFile("", basename="final_config")
        import_filename = self.makeFile("", basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", import_filename])
        except ImportOptionError as error:
            self.assertEqual(str(error),
                             "Nothing to import at %s." % import_filename)
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_non_existent_file(self):
        config_filename = self.makeFile("", basename="final_config")
        import_filename = self.makeFile(basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", import_filename])
        except ImportOptionError as error:
            self.assertEqual(str(error),
                             "File %s doesn't exist." % import_filename)
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_file_with_empty_client_section(self):
        old_configuration = "[client]\n"

        config_filename = self.makeFile("", old_configuration,
                                        basename="final_config")
        import_filename = self.makeFile("", basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", import_filename])
        except ImportOptionError as error:
            self.assertEqual(str(error),
                             "Nothing to import at %s." % import_filename)
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_bogus_file(self):
        config_filename = self.makeFile("", basename="final_config")
        import_filename = self.makeFile("<strong>BOGUS!</strong>",
                                        basename="import_config")

        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", import_filename])
        except ImportOptionError as error:
            self.assertIn("Nothing to import at %s" % import_filename,
                          str(error))
        else:
            self.fail("ImportOptionError not raised")

    def test_import_from_unreadable_file(self):
        """
        An error is raised when unable to read configuration from the
        specified file.
        """
        import_filename = self.makeFile(
            "[client]\nfoo=bar", basename="import_config")
        # Remove read permissions
        os.chmod(import_filename, os.stat(import_filename).st_mode - 0o444)
        error = self.assertRaises(
            ImportOptionError, self.get_config, ["--import", import_filename])
        expected_message = ("Couldn't read configuration from %s." %
                            import_filename)
        self.assertEqual(str(error), expected_message)

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_import_from_file_preserves_old_options(self, mock_sysvconfig):
        old_configuration = (
            "[client]\n"
            "computer_title = Old Title\n"
            "account_name = Old Name\n"
            "registration_key = Old Password\n"
            "http_proxy = http://old.proxy\n"
            "https_proxy = https://old.proxy\n"
            "url = http://old.url\n")

        new_configuration = (
            "[client]\n"
            "account_name = New Name\n"
            "registration_key = New Password\n"
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

        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()
        options = ConfigParser()
        options.read(config_filename)

        self.assertEqual(dict(options.items("client")),
                         {"computer_title": "Old Title",
                          "account_name": "New Name",
                          "registration_key": "Command Line Password",
                          "http_proxy": "http://old.proxy",
                          "https_proxy": "https://old.proxy",
                          "url": "http://new.url"})

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_import_from_file_may_reset_old_options(self, mock_sysvconfig):
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
            "url = http://old.url\n")

        new_configuration = (
            "[client]\n"
            "registration_key =\n")

        config_filename = self.makeFile(old_configuration,
                                        basename="final_config")
        import_filename = self.makeFile(new_configuration,
                                        basename="import_config")

        config = self.get_config(["--config", config_filename, "--silent",
                                  "--import", import_filename])
        setup(config)
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()

        options = ConfigParser()
        options.read(config_filename)

        self.assertEqual(dict(options.items("client")),
                         {"computer_title": "Old Title",
                          "account_name": "Old Name",
                          "registration_key": "",  # <==
                          "url": "http://old.url"})

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch")
    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_import_from_url(
            self, mock_sysvconfig, mock_fetch, mock_print_text):
        mock_sysvconfig().restart_landscape.return_value = True
        configuration = (
            b"[client]\n"
            b"computer_title = New Title\n"
            b"account_name = New Name\n"
            b"registration_key = New Password\n"
            b"http_proxy = http://new.proxy\n"
            b"https_proxy = https://new.proxy\n"
            b"url = http://new.url\n")

        mock_fetch.return_value = configuration

        config_filename = self.makeFile("", basename="final_config")

        config = self.get_config(["--config", config_filename, "--silent",
                                  "--import", "https://config.url"])
        setup(config)
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...")
        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()

        options = ConfigParser()
        options.read(config_filename)

        self.assertEqual(dict(options.items("client")),
                         {"computer_title": "New Title",
                          "account_name": "New Name",
                          "registration_key": "New Password",
                          "http_proxy": "http://new.proxy",
                          "https_proxy": "https://new.proxy",
                          "url": "http://new.url"})

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch")
    def test_import_from_url_with_http_code_fetch_error(
            self, mock_fetch, mock_print_text):
        mock_fetch.side_effect = HTTPCodeError(501, "")
        config_filename = self.makeFile("", basename="final_config")

        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", "https://config.url"])
        except ImportOptionError as error:
            self.assertEqual(str(error),
                             "Couldn't download configuration from "
                             "https://config.url: Server "
                             "returned HTTP code 501")
        else:
            self.fail("ImportOptionError not raised")
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...")

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch")
    def test_import_from_url_with_pycurl_error(
            self, mock_fetch, mock_print_text):
        mock_fetch.side_effect = PyCurlError(60, "pycurl message")

        config_filename = self.makeFile("", basename="final_config")

        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--import", "https://config.url"])
        except ImportOptionError as error:
            self.assertEqual(str(error),
                             "Couldn't download configuration from "
                             "https://config.url: Error 60: pycurl message")
        else:
            self.fail("ImportOptionError not raised")
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...")

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch", return_value=b"")
    def test_import_from_url_with_empty_content(
            self, mock_fetch, mock_print_text):
        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--silent", "--import", "https://config.url"])
        except ImportOptionError as error:
            self.assertEqual(str(error),
                             "Nothing to import at https://config.url.")
        else:
            self.fail("ImportOptionError not raised")
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...")

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch",
                return_value=b"<strong>BOGUS!</strong>")
    def test_import_from_url_with_bogus_content(
            self, mock_fetch, mock_print_text):
        # Use a command line option as well to test the precedence.
        try:
            self.get_config(["--silent", "--import", "https://config.url"])
        except ImportOptionError as error:
            self.assertEqual("Nothing to import at https://config.url.",
                             str(error))
        else:
            self.fail("ImportOptionError not raised")
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...")

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch",
                side_effect=HTTPCodeError(404, ""))
    def test_import_error_is_handled_nicely_by_main(
            self, mock_fetch, mock_print_text):
        system_exit = self.assertRaises(
            SystemExit, main, ["--import", "https://config.url"])
        self.assertEqual(system_exit.code, 1)
        mock_fetch.assert_called_once_with("https://config.url")
        mock_print_text.assert_any_call(
            "Fetching configuration from https://config.url...")
        mock_print_text.assert_called_with(
            "Couldn't download configuration from https://config.url: "
            "Server returned HTTP code 404", error=True)

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_base64_ssl_public_key_is_exported_to_file(
            self, mock_sysvconfig, mock_print_text):
        mock_sysvconfig().restart_landscape.return_value = True
        data_path = self.makeDir()
        config_filename = self.makeFile("[client]\ndata_path=%s" % data_path)
        key_filename = os.path.join(
            data_path,
            os.path.basename(config_filename) + ".ssl_public_key")

        config = self.get_config(["--silent", "-c", config_filename,
                                  "-u", "url", "-a", "account", "-t", "title",
                                  "--ssl-public-key", "base64:SGkgdGhlcmUh"])
        config.data_path = data_path
        setup(config)

        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()
        mock_print_text.assert_called_once_with(
            "Writing SSL CA certificate to %s..." % key_filename)
        self.assertEqual("Hi there!", open(key_filename, "r").read())

        options = ConfigParser()
        options.read(config_filename)
        self.assertEqual(options.get("client", "ssl_public_key"),
                         key_filename)

    @mock.patch("landscape.client.configuration.SysVConfig")
    def test_normal_ssl_public_key_is_not_exported_to_file(
            self, mock_sysvconfig):
        mock_sysvconfig().restart_landscape.return_value = True
        config_filename = self.makeFile("")

        config = self.get_config(["--silent", "-c", config_filename,
                                  "-u", "url", "-a", "account", "-t", "title",
                                  "--ssl-public-key", "/some/filename"])
        setup(config)

        mock_sysvconfig().set_start_on_boot.assert_called_once_with(True)
        mock_sysvconfig().restart_landscape.assert_called_once_with()
        key_filename = config_filename + ".ssl_public_key"
        self.assertFalse(os.path.isfile(key_filename))

        options = ConfigParser()
        options.read(config_filename)
        self.assertEqual(options.get("client", "ssl_public_key"),
                         "/some/filename")

    # We test them individually since they must work individually.
    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch")
    def test_import_from_url_honors_http_proxy(
            self, mock_fetch, mock_print_text):
        self.ensure_import_from_url_honors_proxy_options(
            "http_proxy", mock_fetch, mock_print_text)

    @mock.patch("landscape.client.configuration.print_text")
    @mock.patch("landscape.client.configuration.fetch")
    def test_import_from_url_honors_https_proxy(
            self, mock_fetch, mock_print_text):
        self.ensure_import_from_url_honors_proxy_options(
            "https_proxy", mock_fetch, mock_print_text)

    def ensure_import_from_url_honors_proxy_options(
            self, proxy_option, mock_fetch, mock_print_text):

        def check_proxy(url):
            self.assertEqual("https://config.url", url)
            self.assertEqual(os.environ.get(proxy_option), "http://proxy")
            # Doesn't matter.  We just want to check the context around it.
            return ""

        mock_fetch.side_effect = check_proxy

        config_filename = self.makeFile("", basename="final_config")

        try:
            self.get_config(["--config", config_filename, "--silent",
                             "--" + proxy_option.replace("_", "-"),
                             "http://proxy",
                             "--import", "https://config.url"])
        except ImportOptionError:
            # The returned content is empty.  We don't really care for
            # this test.
            pass
        mock_print_text.assert_called_once_with(
            "Fetching configuration from https://config.url...")


class FakeConnectorFactory(object):

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


class RegisterRealFunctionTest(LandscapeConfigurationTest):

    helpers = [FakeBrokerServiceHelper]

    def setUp(self):
        super(RegisterRealFunctionTest, self).setUp()
        self.config = LandscapeSetupConfiguration()
        self.config.load(["-c", self.config_filename])

    def test_register_success(self):
        self.reactor.call_later(0, self.reactor.fire, "registration-done")
        connector_factory = FakeConnectorFactory(self.remote)
        result = register(
            self.config, self.reactor, connector_factory, max_retries=99)
        self.assertEqual("success", result)

    def test_register_registration_error(self):
        """
        If we get a registration error, the register() function returns the
        error from the registration response message.
        """
        self.reactor.call_later(0, self.reactor.fire, "registration-failed")

        def fail_register():
            return fail(RegistrationError("max-pending-computers"))

        self.remote.register = fail_register

        connector_factory = FakeConnectorFactory(self.remote)
        result = register(
            config=self.config, reactor=self.reactor,
            connector_factory=connector_factory, max_retries=99)
        self.assertEqual("max-pending-computers", result)


class FauxConnection(object):
    def __init__(self):
        self.callbacks = []
        self.errbacks = []

    def addCallback(self, func, *args, **kws):
        self.callbacks.append(func)

    def addErrback(self, func, *args, **kws):
        self.errbacks.append(func)


class FauxConnector(object):

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


class RegisterFunctionTest(LandscapeConfigurationTest):

    helpers = [RemoteBrokerHelper]

    def setUp(self):
        super(RegisterFunctionTest, self).setUp()
        self.config = LandscapeSetupConfiguration()
        self.config.load(["-c", self.config_filename])

    def test_register(self):
        """Is the async machinery wired up properly?"""

        class FauxFailure(object):
            def getTraceback(self):
                return 'traceback'

        class FauxReactor(object):
            def run(self):
                self.was_run = True

            def stop(self, *args):
                self.was_stopped = True

        reactor = FauxReactor()
        connector = FauxConnector(reactor, self.config)

        def connector_factory(reactor, config):
            return connector

        # We pre-seed a success because no actual result will be generated.
        register(self.config, reactor, connector_factory, max_retries=99,
                 results=['success'])
        self.assertTrue(reactor.was_run)
        # Only a single callback is registered, it does the real work when a
        # connection is established.
        self.assertTrue(1, len(connector.connection.callbacks))
        self.assertEqual(
            'got_connection',
            connector.connection.callbacks[0].func.__name__)
        # Should something go wrong, there is an error handler registered.
        self.assertTrue(1, len(connector.connection.errbacks))
        self.assertEqual(
            'got_error',
            connector.connection.errbacks[0].func.__name__)
        # We ask for retries because networks aren't reliable.
        self.assertEqual(99, connector.max_retries)

    @mock.patch("landscape.client.configuration.LandscapeReactor")
    def test_register_without_reactor(self, mock_reactor):
        """If no reactor is passed, a LandscapeReactor will be instantiated.

        This behaviour is exclusively for compatability with the client charm
        which does not pass in a reactor.
        """

        def connector_factory(reactor, config):
            return FauxConnector(reactor, self.config)

        # We pre-seed a success because no actual result will be generated.
        register(self.config, connector_factory=connector_factory,
                 results=["success"])
        mock_reactor.assert_called_once_with()
        mock_reactor().run.assert_called_once_with()

    def test_got_connection(self):
        """got_connection() adds deferreds and callbacks."""

        def faux_got_connection(add_result, remote, connector, reactor):
            pass

        class FauxRemote(object):
            handlers = None
            deferred = None

            def call_on_event(self, handlers):
                assert not self.handlers, "Called twice"
                self.handlers = handlers
                self.call_on_event_deferred = FauxCallOnEventDeferred()
                return self.call_on_event_deferred

            def register(self):
                assert not self.deferred, "Called twice"
                self.register_deferred = FauxRegisterDeferred()
                return self.register_deferred

        class FauxCallOnEventDeferred(object):
            def __init__(self):
                self.callbacks = []
                self.errbacks = []

            def addCallbacks(self, *funcs, **kws):
                self.callbacks.extend(funcs)

        class FauxRegisterDeferred(object):
            def __init__(self):
                self.callbacks = []
                self.errbacks = []

            def addCallback(self, func):
                assert func.__name__ == "got_connection", "Wrong callback."
                self.callbacks.append(faux_got_connection)
                self.gather_results_deferred = GatherResultsDeferred()
                return self.gather_results_deferred

            def addCallbacks(self, *funcs, **kws):
                self.callbacks.extend(funcs)

            def addErrback(self, func, *args, **kws):
                self.errbacks.append(func)
                return self

        class GatherResultsDeferred(object):
            def __init__(self):
                self.callbacks = []
                self.errbacks = []

            def addCallbacks(self, *funcs, **kws):
                self.callbacks.extend(funcs)

        faux_connector = FauxConnector(self.reactor, self.config)

        status_results = []
        faux_remote = FauxRemote()
        results = got_connection(
            status_results.append, faux_connector, self.reactor, faux_remote)
        # We set up two deferreds, one for the RPC call and one for event
        # handlers.
        self.assertEqual(2, len(results.resultList))
        # Handlers are registered for the events we are interested in.
        self.assertCountEqual(
            ['registration-failed', 'exchange-failed', 'registration-done'],
            faux_remote.handlers.keys())
        self.assertCountEqual(
            ['failure', 'exchange_failure', 'success'],
            [handler.func.__name__
             for handler in faux_remote.handlers.values()])
        # We include a single error handler to react to exchange errors.
        self.assertTrue(1, len(faux_remote.register_deferred.errbacks))
        # the handle_registration_errors is wrapped in a partial()
        self.assertEqual(
            'handle_registration_errors',
            faux_remote.register_deferred.errbacks[0].func.__name__)

    def test_register_with_on_error_and_an_error(self):
        """A caller-provided on_error callable will be called if errors occur.

        The on_error parameter is provided for the client charm which calls
        register() directly and provides on_error as a keyword argument.
        """
        def faux_got_connection(add_result, remote, connector, reactor):
            add_result("something bad")

        on_error_was_called = []

        def on_error(status):
            # A positive number is provided for the status.
            self.assertGreater(status, 0)
            on_error_was_called.append(True)

        self.reactor.call_later(1, self.reactor.stop)
        register(self.config, reactor=self.reactor, on_error=on_error,
                 got_connection=faux_got_connection)
        self.assertTrue(on_error_was_called)

    def test_register_with_on_error_and_no_error(self):
        """A caller-provided on_error callable will not be called if no error.
        """
        def faux_got_connection(add_result, remote, connector, reactor):
            add_result("success")

        on_error_was_called = []

        def on_error(status):
            on_error_was_called.append(True)

        self.reactor.call_later(1, self.reactor.stop)
        register(self.config, reactor=self.reactor, on_error=on_error,
                 got_connection=faux_got_connection)
        self.assertFalse(on_error_was_called)

    def test_register_happy_path(self):
        """A successful result provokes no exceptions."""
        def faux_got_connection(add_result, remote, connector, reactor):
            add_result('success')
        self.reactor.call_later(1, self.reactor.stop)
        self.assertEqual(
            "success",
            register(self.config, reactor=self.reactor,
                     got_connection=faux_got_connection))


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
            os.path.basename(config.get_config_filename()) + ".ssl_public_key")

        self.assertEqual(key_filename,
                         store_public_key_data(config, b"123456789"))
        self.assertEqual(b"123456789", read_binary_file(key_filename))
        mock_print_text.assert_called_once_with(
            "Writing SSL CA certificate to %s..." % key_filename)


class ReportRegistrationOutcomeTest(unittest.TestCase):

    def setUp(self):
        self.result = []
        self.output = []

    def record_result(self, result, file=sys.stdout):
        self.result.append(result)
        self.output.append(file.name)

    def test_success_case(self):
        report_registration_outcome("success", print=self.record_result)
        self.assertIn("System successfully registered.", self.result)
        self.assertIn(sys.stdout.name, self.output)

    def test_unknown_account_case(self):
        """
        If the unknown-account error is found, an appropriate message is
        returned.
        """
        report_registration_outcome(
            "unknown-account", print=self.record_result)
        self.assertIn("Invalid account name or registration key.", self.result)
        self.assertIn(sys.stderr.name, self.output)

    def test_max_pending_computers_case(self):
        """
        If the max-pending-computers error is found, an appropriate message is
        returned.
        """
        report_registration_outcome(
            "max-pending-computers", print=self.record_result)
        messages = (
            "Maximum number of computers pending approval reached. ",
            "Login to your Landscape server account page to manage pending "
            "computer approvals.")
        self.assertIn(messages, self.result)
        self.assertIn(sys.stderr.name, self.output)

    def test_ssl_error_case(self):
        report_registration_outcome("ssl-error", print=self.record_result)
        self.assertIn(
            ("\nThe server's SSL information is incorrect, or fails "
             "signature verification!\n"
             "If the server is using a self-signed certificate, "
             "please ensure you supply it with the --ssl-public-key "
             "parameter."),
            self.result)
        self.assertIn(sys.stderr.name, self.output)

    def test_non_ssl_error_case(self):
        report_registration_outcome("non-ssl-error", print=self.record_result)
        self.assertIn(
            ("\nWe were unable to contact the server.\n"
             "Your internet connection may be down. "
             "The landscape client will continue to try and contact "
             "the server periodically."),
            self.result)
        self.assertIn(sys.stderr.name, self.output)


class DetermineExitCodeTest(unittest.TestCase):

    def test_success_means_exit_code_0(self):
        """
        When passed "success" the determine_exit_code function returns 0.
        """
        result = determine_exit_code("success")
        self.assertEqual(0, result)

    def test_a_failure_means_exit_code_2(self):
        """
        When passed a failure result, the determine_exit_code function returns
        2.
        """
        failure_codes = [
            "unknown-account", "max-computers-count", "ssl-error",
            "non-ssl-error"]
        for code in failure_codes:
            result = determine_exit_code(code)
            self.assertEqual(2, result)


class IsRegisteredTest(LandscapeTest):

    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super(IsRegisteredTest, self).setUp()
        persist_file = os.path.join(self.config.data_path, "broker.bpickle")
        self.persist = Persist(filename=persist_file)

    def test_is_registered_false(self):
        """
        If the client hasn't previouly registered, is_registered returns False.
        """
        self.assertFalse(is_registered(self.config))

    def test_is_registered_true(self):
        """
        If the client has previouly registered, is_registered returns True.
        """
        self.persist.set("registration.secure-id", "super-secure")
        self.persist.save()
        self.assertTrue(is_registered(self.config))
