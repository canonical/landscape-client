"""Interactive configuration support for Landscape.

This module, and specifically L{LandscapeSetupScript}, implements the support
for the C{landscape-config} script.
"""

import base64
import time
import sys
import os
import getpass
import pwd
from ConfigParser import ConfigParser, Error as ConfigParserError
from StringIO import StringIO

from landscape.lib.tag import is_valid_tag

from landscape.sysvconfig import SysVConfig, ProcessError
from landscape.lib.amp import MethodCallError
from landscape.lib.twisted_util import gather_results
from landscape.lib.fetch import fetch, FetchError
from landscape.reactor import TwistedReactor
from landscape.broker.registration import InvalidCredentialsError
from landscape.broker.config import BrokerConfiguration
from landscape.broker.amp import RemoteBrokerConnector


class ConfigurationError(Exception):
    """Raised when required configuration values are missing."""


class ImportOptionError(ConfigurationError):
    """Raised when there are issues with handling the --import option."""


def print_text(text, end="\n", error=False):
    if error:
        stream = sys.stderr
    else:
        stream = sys.stdout
    stream.write(text + end)
    stream.flush()


def get_invalid_users(users):
    """
    Process a string with a list of comma separated usernames, this returns
    any usernames not known to the underlying user database.
    """
    if users is not None:
        user_list = [user.strip() for user in users.split(",")]
        if "ALL" in user_list:
            if len(user_list) > 1:
                raise ConfigurationError(
                    "Extra users specified with ALL users")
            user_list.remove("ALL")
        invalid_users = []
        for user in user_list:
            try:
                pwd.getpwnam(user)
            except KeyError:
                invalid_users.append(user)
        return invalid_users


class LandscapeSetupConfiguration(BrokerConfiguration):

    unsaved_options = ("no_start", "disable", "silent", "ok_no_register",
                       "import_from")

    def __init__(self, fetch_import_url):
        super(LandscapeSetupConfiguration, self).__init__()
        self._fetch_import_url = fetch_import_url

    def _load_external_options(self):
        """Handle the --import parameter.

        Imported options behave as if they were passed in the
        command line, with precedence being given to real command
        line options.
        """
        if self.import_from:
            parser = ConfigParser()

            try:
                if "://" in self.import_from:
                    # If it's from a URL, download it now.
                    if self.http_proxy:
                        os.environ["http_proxy"] = self.http_proxy
                    if self.https_proxy:
                        os.environ["https_proxy"] = self.https_proxy
                    content = self._fetch_import_url(self.import_from)
                    parser.readfp(StringIO(content))
                elif not os.path.isfile(self.import_from):
                    raise ImportOptionError("File %s doesn't exist." %
                                            self.import_from)
                else:
                    parser.read(self.import_from)
            except ConfigParserError, error:
                raise ImportOptionError(str(error))

            # But real command line options have precedence.
            options = None
            if parser.has_section(self.config_section):
                options = dict(parser.items(self.config_section))
            if not options:
                raise ImportOptionError("Nothing to import at %s." %
                                        self.import_from)
            options.update(self._command_line_options)
            self._command_line_options = options

    def make_parser(self):
        """
        Specialize the parser, adding configure-specific options.
        """
        parser = super(LandscapeSetupConfiguration, self).make_parser()

        parser.add_option("--import", dest="import_from",
                          metavar="FILENAME_OR_URL",
                          help="Filename or URL to import configuration from. "
                               "Imported options behave as if they were "
                               "passed in the command line, with precedence "
                               "being given to real command line options.")
        parser.add_option("--script-users", metavar="USERS",
                          help="A comma-separated list of users to allow "
                               "scripts to run.  To allow scripts to be run "
                               "by any user, enter: ALL")
        parser.add_option("--include-manager-plugins", metavar="PLUGINS",
                          default="",
                          help="A comma-separated list of manager plugins to "
                               "load.")
        parser.add_option("-n", "--no-start", action="store_true",
                          help="Don't start the client automatically.")
        parser.add_option("--ok-no-register", action="store_true",
                          help="Return exit code 0 instead of 2 if the client "
                          "can't be registered.")
        parser.add_option("--silent", action="store_true", default=False,
                          help="Run without manual interaction.")
        parser.add_option("--disable", action="store_true", default=False,
                          help="Stop running clients and disable start at "
                               "boot.")
        return parser


class LandscapeSetupScript(object):
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
        print_text("\n" + "".join([line.strip() + "\n" for line in lines]))

    def prompt_get_input(self, msg, required):
        """Prompt the user on the terminal for a value

        @param msg: Message to prompt user with
        @param required: True if value must be entered
        """
        while True:
            value = raw_input(msg)
            if value:
                return value
            elif not required:
                break
            self.show_help("This option is required to configure Landscape.")

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
        required = required and not (bool(default))
        result = self.prompt_get_input(msg, required)
        if result:
            setattr(self.config, option, result)

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
            invalid_users = get_invalid_users(options["script_users"])
            if invalid_users:
                raise ConfigurationError("Unknown system users: %s" %
                                         ", ".join(invalid_users))
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
        included_plugins = [
            p.strip() for p in self.config.include_manager_plugins.split(",")]
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
            while True:
                self.prompt("script_users", "Script users")
                invalid_users = get_invalid_users(
                    self.config.script_users)
                if not invalid_users:
                    break
                else:
                    self.show_help("Unknown system users: %s" %
                                   ",".join(invalid_users))
                    self.config.script_users = None
        else:
            if "ScriptExecution" in included_plugins:
                included_plugins.remove("ScriptExecution")
        self.config.include_manager_plugins = ", ".join(included_plugins)

    def _get_invalid_tags(self, tagnames):
        """
        Splits a string on , and checks the validity of each tag, returns any
        invalid tags.
        """
        invalid_tags = []
        if tagnames:
            tags = [tag.strip() for tag in tagnames.split(",")]
            invalid_tags = [tag for tag in tags if not is_valid_tag(tag)]
        return invalid_tags

    def query_tags(self):
        """Query tags from the user."""
        options = self.config.get_command_line_options()
        if "tags" in options:
            invalid_tags = self._get_invalid_tags(options["tags"])
            if invalid_tags:
                raise ConfigurationError("Invalid tags: %s" %
                                         ", ".join(invalid_tags))
            return

        self.show_help("You may provide tags for this computer e.g. "
                       "server,hardy.")
        while True:
            self.prompt("tags", "Tags", False)
            if self._get_invalid_tags(self.config.tags):
                self.show_help("Tag names may only contain alphanumeric "
                              "characters.")
                self.config.tags = None # Reset for the next prompt
            else:
                break

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
        self.query_tags()


def setup_init_script_and_start_client():
    # XXX This function is misnamed; it doesn't start the client.
    sysvconfig = SysVConfig()
    sysvconfig.set_start_on_boot(True)


def stop_client_and_disable_init_script():
    sysvconfig = SysVConfig()
    sysvconfig.stop_landscape()
    sysvconfig.set_start_on_boot(False)


def setup(config):
    sysvconfig = SysVConfig()
    if not config.no_start:
        if config.silent:
            setup_init_script_and_start_client()
        elif not sysvconfig.is_configured_to_run():
            answer = raw_input("\nThe Landscape client must be started "
                               "on boot to operate correctly.\n\n"
                               "Start Landscape client on boot? (Y/n): ")
            if not answer.upper().startswith("N"):
                setup_init_script_and_start_client()
            else:
                sys.exit("Aborting Landscape configuration")

    if config.http_proxy is None and os.environ.get("http_proxy"):
        config.http_proxy = os.environ["http_proxy"]
    if config.https_proxy is None and os.environ.get("https_proxy"):
        config.https_proxy = os.environ["https_proxy"]

    if config.silent:
        if not config.get("account_name") or not config.get("computer_title"):
            raise ConfigurationError("An account name and computer title are "
                                     "required.")
        if config.get("script_users"):
            invalid_users = get_invalid_users(config.get("script_users"))
            if invalid_users:
                raise ConfigurationError("Unknown system users: %s" %
                                         ", ".join(invalid_users))
            if not config.include_manager_plugins:
                config.include_manager_plugins = "ScriptExecution"
    else:
        script = LandscapeSetupScript(config)
        script.run()

    # WARNING: ssl_public_key is misnamed, it's not the key of the certificate,
    # but the actual certificate itself.
    if config.ssl_public_key and config.ssl_public_key.startswith("base64:"):
        decoded_cert = base64.decodestring(config.ssl_public_key[7:])
        config.ssl_public_key = store_public_key_data(
            config, decoded_cert)

    config.write()
    # Restart the client to ensure that it's using the new configuration.
    if not config.no_start:
        try:
            sysvconfig.restart_landscape()
        except ProcessError:
            print_text("Couldn't restart the Landscape client.", error=True)
            print_text("This machine will be registered with the provided "
                       "details when the client runs.", error=True)
            exit_code = 2
            if config.ok_no_register:
                exit_code = 0
            sys.exit(exit_code)


def store_public_key_data(config, certificate_data):
    """
    Write out the data from the SSL certificate provided to us, either from a
    bootstrap.conf file, or from EC2-style user-data.

    @param config_filename:  This filename is used to generate the filename
        we write the certificate data to.
    @param certificate_data: a string of data that represents the contents of
    the file to be written.
    @return the L{BrokerConfiguration} object that was passed in, updated to
    reflect the path of the ssl_public_key file.
    """
    key_filename = os.path.join(config.data_path,
        os.path.basename(config.get_config_filename() + ".ssl_public_key"))
    print_text("Writing SSL CA certificate to %s..." % key_filename)
    key_file = open(key_filename, "w")
    key_file.write(certificate_data)
    key_file.close()
    return key_filename


def register(config, reactor=None):
    """Instruct the Landscape Broker to register the client.

    The broker will be instructed to reload its configuration and then to
    attempt a registration.

    @param reactor: The reactor to use.  Please only pass reactor when you
        have totally mangled everything with mocker.  Otherwise bad things
        will happen.
    """
    reactor = TwistedReactor()
    exit_with_error = []

    # XXX: many of these reactor.stop() calls should also specify a non-0 exit
    # code, unless ok-no-register is passed.

    def stop():
        connector.disconnect()
        reactor.stop()

    def failure():
        print_text("Invalid account name or "
                   "registration password.", error=True)
        stop()

    def success():
        print_text("System successfully registered.")
        stop()

    def exchange_failure():
        print_text("We were unable to contact the server. "
                   "Your internet connection may be down. "
                   "The landscape client will continue to try and contact "
                   "the server periodically.",
                   error=True)
        stop()

    def handle_registration_errors(failure):
        # We'll get invalid credentials through the signal.
        failure.trap(InvalidCredentialsError, MethodCallError)
        connector.disconnect()

    def catch_all(failure):
        # We catch SecurityError here too, because on some DBUS configurations
        # if you try to connect to a dbus name that doesn't have a listener,
        # it'll try auto-starting the service, but then the StartServiceByName
        # call can raise a SecurityError.
        print_text(failure.getTraceback(), error=True)
        print_text("Unknown error occurred.", error=True)
        stop()

    print_text("Please wait... ", "")

    time.sleep(2)

    def got_connection(remote):
        handlers = {"registration-done": success,
                    "registration-failed": failure,
                    "exchange-failed": exchange_failure}
        deferreds = [
            remote.reload_configuration(),
            remote.call_on_event(handlers),
            remote.register().addErrback(handle_registration_errors)]
        # We consume errors here to ignore errors after the first one.
        # catch_all will be called for the very first deferred that fails.
        results = gather_results(deferreds, consume_errors=True)
        return results.addErrback(catch_all)

    def got_error(failure):
        print_text("There was an error communicating with the Landscape "
                   "client.", error=True)
        print_text("This machine will be registered with the provided "
                   "details when the client runs.", error=True)
        if not config.ok_no_register:
            exit_with_error.append(2)
        stop()

    connector = RemoteBrokerConnector(reactor, config)
    result = connector.connect(max_retries=0, quiet=True)
    result.addCallback(got_connection)
    result.addErrback(got_error)

    reactor.run()

    if exit_with_error:
        sys.exit(exit_with_error[0])

    return result


def fetch_import_url(url):
    """Handle fetching of URLs passed to --url.

    This is done out of LandscapeSetupConfiguration since it has to deal
    with interaction with the user and downloading of files.
    """

    print_text("Fetching configuration from %s..." % url)
    error_message = None
    try:
        content = fetch(url)
    except FetchError, error:
        error_message = str(error)
    if error_message is not None:
        raise ImportOptionError(
            "Couldn't download configuration from %s: %s" %
            (url, error_message))
    return content


def main(args):
    if os.getuid() != 0:
        sys.exit("landscape-config must be run as root.")

    config = LandscapeSetupConfiguration(fetch_import_url)
    try:
        config.load(args)
    except ImportOptionError, error:
        print_text(str(error), error=True)
        sys.exit(1)

    # Disable startup on boot and stop the client, if one is running.
    if config.disable:
        stop_client_and_disable_init_script()
        return

    # Setup client configuration.
    try:
        setup(config)
    except Exception, e:
        print_text(str(e))
        sys.exit("Aborting Landscape configuration")

    # Attempt to register the client.
    if config.silent:
        register(config)
    else:
        answer = raw_input("\nRequest a new registration for "
                           "this computer now? (Y/n): ")
        if not answer.upper().startswith("N"):
            register(config)
