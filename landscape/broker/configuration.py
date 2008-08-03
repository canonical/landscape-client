"""Interactive configuration support for Landscape.

This module, and specifically L{BrokerConfigurationScript}, implements the
support for the C{landscape-config} script.
"""

import sys
import os
import getpass

from landscape.sysvconfig import SysVConfig, ProcessError
from landscape.lib.dbus_util import (
    get_bus, NoReplyError, ServiceUnknownError, SecurityError)
from landscape.lib.twisted_util import gather_results

from landscape.broker.registration import InvalidCredentialsError
from landscape.broker.deployment import BrokerConfiguration
from landscape.broker.remote import RemoteBroker


class ConfigurationError(Exception):
    """Raised when required configuration values are missing."""


def print_text(text, end="\n", error=False):
    if error:
        stream = sys.stderr
    else:
        stream = sys.stdout
    stream.write(text+end)
    stream.flush()


class BrokerConfigurationScript(object):
    """
    An interactive procedure which manages the prompting and temporary storage
    of configuration parameters.

    Various attributes on this object will be set on C{config} after L{run} is
    called.

    @ivar config: The L{BrokerConfiguration} object to read and set values from
        and to.
    """

    def __init__(self, config):
        self.config = config

    def show_help(self, text):
        lines = text.strip().splitlines()
        print_text("\n"+"".join([line.strip()+"\n" for line in lines]))

    def prompt(self, option, msg, required=False):
        """Prompt the user on the terminal for a value.

        @param option: The attribute of C{self.config} that contains the
            default and which the value will be assigned to.
        @param msg: The message to prompt the user with (via C{raw_input}).
        @param required: If True, the user will be required to enter a value
            before continuing.
        """
        default = getattr(self.config, option, None)
        if default:
            msg += " [%s]: " % default
        else:
            msg += ": "
        while True:
            value = raw_input(msg)
            if value:
                setattr(self.config, option, value)
                break
            elif default or not required:
                break
            self.show_help("This option is required to configure Landscape.")

    def password_prompt(self, option, msg, required=False):
        """Prompt the user on the terminal for a password and mask the value.

        This also prompts the user twice and errors if both values don't match.

        @param option: The attribute of C{self.config} that contains the
            default and which the value will be assigned to.
        @param msg: The message to prompt the user with (via C{raw_input}).
        @param required: If True, the user will be required to enter a value
            before continuing.
        """
        default = getattr(self.config, option, None)
        msg += ": "
        while True:
            value = getpass.getpass(msg)
            if value:
                value2 = getpass.getpass("Please confirm: ")
            if value:
                if value != value2:
                   self.show_help("Passwords must match.")
                else:
                    setattr(self.config, option, value)
                    break
            elif default or not required:
                break
            else:
                self.show_help("This option is required to configure "
                               "Landscape.")

    def prompt_yes_no(self, message, default=True):
        if default:
            default_msg = " [Y/n]"
        else:
            default_msg = " [y/N]"
        while True:
            value = raw_input(message + default_msg).lower()
            if value:
                if value.startswith("n"):
                    return False
                if value.startswith("y"):
                    return True
                self.show_help("Invalid input.")
            else:
                return default

    def query_computer_title(self):
        if "computer_title" in self.config.get_command_line_options():
            return

        self.show_help(
            """
            The computer title you provide will be used to represent this
            computer in the Landscape user interface. It's important to use
            a title that will allow the system to be easily recognized when
            it appears on the pending computers page.
            """)

        self.prompt("computer_title", "This computer's title", True)

    def query_account_name(self):
        if "account_name" in self.config.get_command_line_options():
            return

        self.show_help(
            """
            You must now specify the name of the Landscape account you
            want to register this computer with.  You can verify the
            names of the accounts you manage on your dashboard at
            https://landscape.canonical.com/dashboard
            """)

        self.prompt("account_name", "Account name", True)

    def query_registration_password(self):
        if "registration_password" in self.config.get_command_line_options():
            return

        self.show_help(
            """
            A registration password may be associated with your Landscape
            account to prevent unauthorized registration attempts.  This
            is not your personal login password.  It is optional, and unless
            explicitly set on the server, it may be skipped here.

            If you don't remember the registration password you can find it
            at https://landscape.canonical.com/account/%s
            """ % self.config.account_name)

        self.password_prompt("registration_password",
                             "Account registration password")

    def query_proxies(self):
        options = self.config.get_command_line_options()
        if "http_proxy" in options and "https_proxy" in options:
            return

        self.show_help(
            """
            The Landscape client communicates with the server over HTTP and
            HTTPS.  If your network requires you to use a proxy to access HTTP
            and/or HTTPS web sites, please provide the address of these
            proxies now.  If you don't use a proxy, leave these fields empty.
            """)

        if not "http_proxy" in options:
            self.prompt("http_proxy", "HTTP proxy URL")
        if not "https_proxy" in options:
            self.prompt("https_proxy", "HTTPS proxy URL")

    def query_script_plugin(self):
        options = self.config.get_command_line_options()
        if "include_manager_plugins" in options and "script_users" in options:
            return

        self.show_help(
            """
            Landscape has a feature which enables administrators to run
            arbitrary scripts on machines under their control. By default this
            feature is disabled in the client, disallowing any arbitrary script
            execution. If enabled, the set of users that scripts may run as is
            also configurable.
            """)
        msg = "Enable script execution?"
        included_plugins = getattr(self.config, "include_manager_plugins")
        if not included_plugins:
            included_plugins = ""
        included_plugins = [x.strip() for x in included_plugins.split(",")]
        if included_plugins == [""]:
            included_plugins = []
        default = "ScriptExecution" in included_plugins
        if self.prompt_yes_no(msg, default=default):
            if "ScriptExecution" not in included_plugins:
                included_plugins.append("ScriptExecution")
            self.show_help(
                """
                By default, scripts are restricted to the 'landscape' and
                'nobody' users. Please enter a comma-delimited list of users
                that scripts will be restricted to. To allow scripts to be run
                by any user, enter "ALL".
                """)
            if not "script_users" in options:
                self.prompt("script_users", "Script users")
        else:
            if "ScriptExecution" in included_plugins:
                included_plugins.remove("ScriptExecution")
        self.config.include_manager_plugins = ', '.join(included_plugins)

    def show_header(self):
        self.show_help(
            """
            This script will interactively set up the Landscape client. It will
            ask you a few questions about this computer and your Landscape
            account, and will submit that information to the Landscape server.
            After this computer is registered it will need to be approved by an
            account administrator on the pending computers page.

            Please see https://landscape.canonical.com for more information.
            """)

    def run(self):
        """Kick off the interactive process which prompts the user for data.

        Data will be saved to C{self.config}.
        """
        self.show_header()
        self.query_computer_title()
        self.query_account_name()
        self.query_registration_password()
        self.query_proxies()
        self.query_script_plugin()


def setup_init_script(silent=False):
    sysvconfig = SysVConfig()
    if not sysvconfig.is_configured_to_run():
        if silent:
            answer = "Y"
        else:
            answer = raw_input("\nThe Landscape client must be started "
                               "on boot to operate correctly.\n\n"
                               "Start Landscape client on boot? (Y/n): ")
        if not answer.upper().startswith("N"):
            sysvconfig.set_start_on_boot(True)
            try:
                sysvconfig.start_landscape()
            except ProcessError:
                print_text("Error starting client cannot continue.")
                sys.exit(-1)
        else:
            sys.exit("Aborting Landscape configuration")


def disable_init_script():
    sysvconfig = SysVConfig()
    if sysvconfig.is_configured_to_run():
        sysvconfig.set_start_on_boot(False)
        sysvconfig.stop_landscape()


def setup(args, silent=False):
    """Prompt the user for config data and write out a configuration file."""
    config = BrokerConfiguration()
    config.load(args)
    if not config.no_start:
        setup_init_script(silent=silent)

    if silent:
        # Clear existing configuration, keeping only required values and
        # values provided on the command line.
        bus = config.get("bus")
        url = config.get("url")
        ping_url = config.get("ping_url")
        config.clear()
        config.bus = bus
        config.url = url
        config.write()
        config.load(args)
        if ping_url and not config.get("ping_url"):
            config.ping_url = ping_url
        if not config.get("account_name") or not config.get("computer_title"):
            raise ConfigurationError("An account name and computer title are "
                                     "required.")
        if config.get("script_users") and not config.include_manager_plugins:
            config.include_manager_plugins = "ScriptExecution"

    if config.http_proxy is None and os.environ.get("http_proxy"):
        config.http_proxy = os.environ["http_proxy"]
    if config.https_proxy is None and os.environ.get("https_proxy"):
        config.https_proxy = os.environ["https_proxy"]

    if not silent:
        script = BrokerConfigurationScript(config)
        script.run()

    config.write()
    return config


def register(config, reactor=None):
    """Instruct the Landscape Broker to register the client.

    The broker will be instructed to reload its configuration and then to
    attempt a registration.

    @param reactor: The reactor to use.  Please only pass reactor when you
        have totally mangled everything with mocker.  Otherwise bad things
        will happen.
    """
    from twisted.internet.glib2reactor import install
    install()
    if reactor is None:
        from twisted.internet import reactor

    def failure():
        print_text("Invalid account name or "
                   "registration password.", error=True)
        reactor.stop()

    def success():
        print_text("System successfully registered.")
        reactor.stop()

    def exchange_failure():
        print_text("We were unable to contact the server. "
                   "Your internet connection may be down. "
                   "The landscape client will continue to try and contact "
                   "the server periodically.",
                   error=True)
        reactor.stop()

    def handle_registration_errors(failure):
        # We'll get invalid credentials through the signal.
        error = failure.trap(InvalidCredentialsError, NoReplyError)
        # This event is fired here so we can catch this case where
        # there is no reply in a test.  In the normal case when
        # running the client there is no trigger added for this event
        # and it is essentially a noop.
        reactor.fireSystemEvent("landscape-registration-error")

    def catch_all(failure):
        # We catch SecurityError here too, because on some DBUS configurations
        # if you try to connect to a dbus name that doesn't have a listener,
        # it'll try auto-starting the service, but then the StartServiceByName
        # call can raise a SecurityError.
        if failure.check(ServiceUnknownError, SecurityError):
            print_text("Error occurred contacting Landscape Client. "
                       "Is it running?", error=True)
        else:
            print_text(failure.getTraceback(), error=True)
            print_text("Unknown error occurred.", error=True)
        reactor.callLater(0, reactor.stop)


    print_text("Please wait... ", "")

    remote = RemoteBroker(get_bus(config.bus), retry_timeout=0)
    # This is a bit unfortunate. Every method of remote returns a deferred,
    # even stuff like connect_to_signal, because the fetching of the DBus
    # object itself is asynchronous. We can *mostly* fire-and-forget these
    # things, except that if the object isn't found, *all* of the deferreds
    # will fail. To prevent unhandled errors, we need to collect them all up
    # and add an errback.
    deferreds = [
        remote.reload_configuration(),
        remote.connect_to_signal("registration_done", success),
        remote.connect_to_signal("registration_failed", failure),
        remote.connect_to_signal("exchange_failed", exchange_failure),
        remote.register().addErrback(handle_registration_errors)]
    # We consume errors here to ignore errors after the first one. catch_all
    # will be called for the very first deferred that fails.
    gather_results(deferreds, consume_errors=True).addErrback(catch_all)
    reactor.run()


def pop_argument(args, option):
    try:
        args.pop(args.index(option))
    except ValueError:
        return False
    return True


def main(args):
    # If --disable is specified disable startup on boot and stop the client,
    # if one is running.
    if pop_argument(args, "--disable"):
        disable_init_script()
        return

    # Setup client configuration.
    silent = pop_argument(args, "--silent")
    try:
        config = setup(args, silent=silent)
    except ConfigurationError, e:
        print_text(str(e))
        sys.exit("Aborting Landscape configuration")

    # Attempt to register the client.
    if silent:
        answer = "Y"
    else:
        answer = raw_input("\nRequest a new registration for "
                           "this computer now? (Y/n): ")
    if not answer.upper().startswith("N"):
        register(config)
