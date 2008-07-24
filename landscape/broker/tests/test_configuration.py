import os
from getpass import getpass

from twisted.internet.defer import Deferred, succeed, fail
from twisted.internet import reactor

from landscape.reactor import FakeReactor
from landscape.broker.configuration import (
    print_text, BrokerConfigurationScript, register, setup, main,
    setup_init_script)
from landscape.broker.deployment import BrokerConfiguration
from landscape.broker.registration import InvalidCredentialsError
from landscape.sysvconfig import SysVConfig
from landscape.tests.helpers import (LandscapeTest, LandscapeIsolatedTest,
                                     RemoteBrokerHelper, EnvironSaverHelper)
from landscape.tests.mocker import ARGS, KWARGS, ANY, MATCH, CONTAINS, expect


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


class BrokerConfigurationScriptTest(LandscapeTest):

    def setUp(self):
        super(BrokerConfigurationScriptTest, self).setUp()
        self.config_filename = self.makeFile()
        class MyBrokerConfiguration(BrokerConfiguration):
            default_config_filenames = [self.config_filename]
        self.config = MyBrokerConfiguration()
        self.script = BrokerConfigurationScript(self.config)

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

    def test_query_account_name(self):
        help_snippet = "You must now specify the name of the Landscape account"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt("account_name", "Account name", True)
        self.mocker.replay()

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

    def test_query_proxies(self):
        help_snippet = "The Landscape client communicates"
        self.mocker.order()
        script_mock = self.mocker.patch(self.script)
        script_mock.show_help(self.get_matcher(help_snippet))
        script_mock.prompt("http_proxy", "HTTP proxy URL")
        script_mock.prompt("https_proxy", "HTTPS proxy URL")
        self.mocker.replay()
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
        self.mocker.replay()

        self.script.run()


class ConfigurationFunctionsTest(LandscapeTest):

    helpers = [EnvironSaverHelper]

    def test_setup(self):
        filename = self.makeFile("[client]\n"
                                 "computer_title = Old Title\n"
                                 "account_name = Old Name\n"
                                 "registration_password = Old Password\n"
                                 "http_proxy = http://old.proxy\n"
                                 "https_proxy = https://old.proxy\n"
                                 "url = http://url\n"
                                 "include_manager_plugins = ScriptExecution"
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

        # Negative assertion.  We don't want it called in any other way.
        expect(raw_input(ANY)).count(0)

        # We don't care about these here, but don't show any output please.
        print_text_mock = self.mocker.replace(print_text)
        expect(print_text_mock(ANY)).count(0, None)

        self.mocker.replay()

        args = ["--no-start", "--config", filename]

        config = setup(args)

        self.assertEquals(type(config), BrokerConfiguration)

        # Reload it to enusre it was written down.
        config.reload()

        self.assertEquals(config.computer_title, "New Title")
        self.assertEquals(config.account_name, "New Name")
        self.assertEquals(config.registration_password, "New Password")
        self.assertEquals(config.http_proxy, "http://new.proxy")
        self.assertEquals(config.https_proxy, "https://new.proxy")
        self.assertEquals(config.include_manager_plugins, "")

    def test_setup_with_proxies_from_environment(self):
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"

        script_mock = self.mocker.patch(BrokerConfigurationScript)
        script_mock.run()

        filename = self.makeFile("[client]\n"
                                 "url = http://url\n")

        self.mocker.replay()

        args = ["--no-start", "--config", filename]

        config = setup(args)

        # Reload it to ensure it was written down.
        config.reload()

        self.assertEquals(config.http_proxy, "http://environ")
        self.assertEquals(config.https_proxy, "https://environ")

    def test_setup_prefers_proxies_from_config_over_environment(self):
        os.environ["http_proxy"] = "http://environ"
        os.environ["https_proxy"] = "https://environ"

        script_mock = self.mocker.patch(BrokerConfigurationScript)
        script_mock.run()

        filename = self.makeFile("[client]\n"
                                 "http_proxy = http://config\n"
                                 "https_proxy = https://config\n"
                                 "url = http://url\n")

        self.mocker.replay()

        args = ["--no-start", "--config", filename]

        config = setup(args)

        # Reload it to enusre it was written down.
        config.reload()

        self.assertEquals(config.http_proxy, "http://config")
        self.assertEquals(config.https_proxy, "https://config")

    def test_main_no_registration(self):
        setup_mock = self.mocker.replace(setup)
        setup_mock(["args"])

        raw_input_mock = self.mocker.replace(raw_input)
        raw_input_mock("\nRequest a new registration for "
                       "this computer now? (Y/n): ")
        self.mocker.result("n")

        # This must not be called.
        register_mock = self.mocker.replace(register, passthrough=False)
        register_mock()
        self.mocker.count(0)

        self.mocker.replay()

        main(["args"])

    def make_working_config(self):
        return self.makeFile("[client]\n"
                             "computer_title = Old Title\n"
                             "account_name = Old Name\n"
                             "registration_password = Old Password\n"
                             "http_proxy = http://old.proxy\n"
                             "https_proxy = https://old.proxy\n"
                             "url = http://url\n")


    def test_main_with_failing_client_start(self):
        system_mock = self.mocker.replace("os.system")
        system_mock("/etc/init.d/landscape-client start")
        self.mocker.result(-1)

        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.is_configured_to_run()
        self.mocker.result(False)
        sysvconfig_mock.set_start_on_boot(True)

        print_text_mock = self.mocker.replace(print_text)
        print_text_mock("Error starting client cannot continue.")

        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        raw_input_mock("\nThe Landscape client must be started "
                       "on boot to operate correctly.\n\n"
                       "Start Landscape client on boot? (Y/n): ")
        self.mocker.result("")
        self.mocker.replay()

        self.assertRaises(SystemExit, main, ["--config",
                                             self.make_working_config()])

    def test_register(self):
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.is_configured_to_run()
        self.mocker.result(False)
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.start_landscape()

        script_mock = self.mocker.patch(BrokerConfigurationScript)
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

    def test_main_with_register(self): 
         setup_mock = self.mocker.replace(setup)
         setup_mock("DUMMY ARGS")
         self.mocker.result("DUMMY CONFIG")
         raw_input_mock = self.mocker.replace(raw_input)
         raw_input_mock("\nRequest a new registration for "
                        "this computer now? (Y/n): ")
         self.mocker.result("")
 
         register_mock = self.mocker.replace(register, passthrough=False)
         register_mock("DUMMY CONFIG")

         self.mocker.replay()
         main("DUMMY ARGS")

    def test_setup_init_script(self):
        system_mock = self.mocker.replace("os.system")
        system_mock("/etc/init.d/landscape-client start")
        self.mocker.result(0)

        sysvconfig_mock = self.mocker.patch(SysVConfig)
        sysvconfig_mock.is_configured_to_run()
        self.mocker.result(False)
        sysvconfig_mock.set_start_on_boot(True)

        raw_input_mock = self.mocker.replace(raw_input, passthrough=False)
        raw_input_mock("\nThe Landscape client must be started "
                       "on boot to operate correctly.\n\n"
                       "Start Landscape client on boot? (Y/n): ")
        self.mocker.result("")
        self.mocker.replay()
        setup_init_script()


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
        install_mock = self.mocker.replace("twisted.internet."
                                           "glib2reactor.install")

        # This must necessarily happen in the following order.
        self.mocker.order()

        install_mock()

        # This very informative message is printed out.
        print_text_mock("Please wait... ", "")

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
        install_mock = self.mocker.replace("twisted.internet."
                                           "glib2reactor.install")

        # This must necessarily happen in the following order.
        self.mocker.order()

        install_mock()

        # This very informative message is printed out.
        print_text_mock("Please wait... ", "")

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
        install_mock = self.mocker.replace("twisted.internet."
                                           "glib2reactor.install")

        # This must necessarily happen in the following order.
        self.mocker.order()

        install_mock()

        # This very informative message is printed out.
        print_text_mock("Please wait... ", "")

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
        install_mock = self.mocker.replace("twisted.internet."
                                           "glib2reactor.install")

        # This must necessarily happen in the following order.
        self.mocker.order()

        install_mock()

        # This very informative message is printed out.
        print_text_mock("Please wait... ", "")

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


class RegisterFunctionNoServiceTest(LandscapeIsolatedTest):

    def setUp(self):
        super(RegisterFunctionNoServiceTest, self).setUp()
        self.configuration = BrokerConfiguration()
        # Let's not mess about with the system bus
        self.configuration.load_command_line(["--bus", "session"])

    def test_register_dbus_error(self):
        """
        When registration fails because of a DBUS error, a message is printed
        and the program exits.
        """
        print_text_mock = self.mocker.replace(print_text)
        reactor_mock = self.mocker.proxy("twisted.internet.reactor")
        install_mock = self.mocker.replace("twisted.internet."
                                           "glib2reactor.install")

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
        install_mock = self.mocker.replace("twisted.internet."
                                           "glib2reactor.install")
        # This is unordered. It's just way too much of a pain.

        install_mock()
        print_text_mock("Please wait... ", "")

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

