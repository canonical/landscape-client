"""Interactive configuration support for Landscape.

This module, and specifically L{LandscapeSetupScript}, implements the support
for the C{landscape-config} script.
"""

from __future__ import print_function

from functools import partial
import getpass
import io
import os
import pwd
import sys

from landscape.lib.compat import input
from landscape.lib import base64

from landscape.lib.tag import is_valid_tag

from landscape.client.sysvconfig import SysVConfig, ProcessError
from landscape.lib.amp import MethodCallError
from landscape.lib.twisted_util import gather_results
from landscape.lib.fetch import fetch, FetchError
from landscape.lib.fs import create_binary_file
from landscape.lib.bootstrap import BootstrapList, BootstrapDirectory
from landscape.lib.persist import Persist
from landscape.client.reactor import LandscapeReactor
from landscape.client.broker.registration import RegistrationError
from landscape.client.broker.config import BrokerConfiguration
from landscape.client.broker.amp import RemoteBrokerConnector
from landscape.client.broker.registration import Identity
from landscape.client.broker.service import BrokerService


class ConfigurationError(Exception):
    """Raised when required configuration values are missing."""


class ImportOptionError(ConfigurationError):
    """Raised when there are issues with handling the --import option."""


def print_text(text, end="\n", error=False):
    """Display the given text to the user, using stderr if flagged as an error.
    """
    if error:
        stream = sys.stderr
    else:
        stream = sys.stdout
    stream.write(text + end)
    stream.flush()


def show_help(text):
    """Display help text."""
    lines = text.strip().splitlines()
    print_text("\n" + "".join([line.strip() + "\n" for line in lines]))


def prompt_yes_no(message, default=True):
    """Prompt for a yes/no question and return the answer as bool."""
    default_msg = "[Y/n]" if default else "[y/N]"
    while True:
        value = input("{} {}: ".format(message, default_msg)).lower()
        if value:
            if value.startswith("n"):
                return False
            if value.startswith("y"):
                return True
            show_help("Invalid input.")
        else:
            return default


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

    def _load_external_options(self):
        """Handle the --import parameter.

        Imported options behave as if they were passed in the
        command line, with precedence being given to real command
        line options.
        """
        if self.import_from:
            parser = None

            try:
                if "://" in self.import_from:
                    # If it's from a URL, download it now.
                    if self.http_proxy:
                        os.environ["http_proxy"] = self.http_proxy
                    if self.https_proxy:
                        os.environ["https_proxy"] = self.https_proxy
                    content = self.fetch_import_url(self.import_from)
                    parser = self._get_config_object(
                        alternative_config=io.StringIO(
                            content.decode("utf-8")))
                elif not os.path.isfile(self.import_from):
                    raise ImportOptionError("File %s doesn't exist." %
                                            self.import_from)
                else:
                    try:
                        parser = self._get_config_object(
                            alternative_config=self.import_from)
                    except Exception:
                        raise ImportOptionError(
                            "Couldn't read configuration from %s." %
                            self.import_from)
            except Exception as error:
                raise ImportOptionError(str(error))

            # But real command line options have precedence.
            options = None
            if parser and self.config_section in parser:
                options = parser[self.config_section]
            if not options:
                raise ImportOptionError("Nothing to import at %s." %
                                        self.import_from)
            options.update(self._command_line_options)
            self._command_line_options = options

    def fetch_import_url(self, url):
        """Handle fetching of URLs passed to --url."""

        print_text("Fetching configuration from %s..." % url)
        error_message = None
        try:
            content = fetch(url)
        except FetchError as error:
            error_message = str(error)
        if error_message is not None:
            raise ImportOptionError(
                "Couldn't download configuration from %s: %s" %
                (url, error_message))
        return content

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
        parser.add_option("--init", action="store_true", default=False,
                          help="Set up the client directories structure "
                               "and exit.")
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

    def prompt_get_input(self, msg, required):
        """Prompt the user on the terminal for a value

        @param msg: Message to prompt user with
        @param required: True if value must be entered
        """
        while True:
            value = input(msg)
            if value:
                return value
            elif not required:
                break
            show_help("This option is required to configure Landscape.")

    def prompt(self, option, msg, required=False):
        """Prompt the user on the terminal for a value.

        @param option: The attribute of C{self.config} that contains the
            default and which the value will be assigned to.
        @param msg: The message to prompt the user with (via C{input}).
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
        @param msg: The message to prompt the user with (via C{input}).
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
                    show_help("Keys must match.")
                else:
                    setattr(self.config, option, value)
                    break
            elif default or not required:
                break
            else:
                show_help("This option is required to configure Landscape.")

    def query_computer_title(self):
        if "computer_title" in self.config.get_command_line_options():
            return

        show_help(
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

        show_help(
            """
            You must now specify the name of the Landscape account you
            want to register this computer with. Your account name is shown
            under 'Account name' at https://landscape.canonical.com .
            """)

        self.prompt("account_name", "Account name", True)

    def query_registration_key(self):
        command_line_options = self.config.get_command_line_options()
        if "registration_key" in command_line_options:
            return

        show_help(
            """
            A registration key may be associated with your Landscape
            account to prevent unauthorized registration attempts.  This
            is not your personal login password.  It is optional, and unless
            explicitly set on the server, it may be skipped here.

            If you don't remember the registration key you can find it
            at https://landscape.canonical.com/account/%s
            """ % self.config.account_name)

        self.password_prompt("registration_key",
                             "Account registration key")

    def query_proxies(self):
        options = self.config.get_command_line_options()
        if "http_proxy" in options and "https_proxy" in options:
            return

        show_help(
            """
            The Landscape client communicates with the server over HTTP and
            HTTPS.  If your network requires you to use a proxy to access HTTP
            and/or HTTPS web sites, please provide the address of these
            proxies now.  If you don't use a proxy, leave these fields empty.
            """)

        if "http_proxy" not in options:
            self.prompt("http_proxy", "HTTP proxy URL")
        if "https_proxy" not in options:
            self.prompt("https_proxy", "HTTPS proxy URL")

    def query_script_plugin(self):
        options = self.config.get_command_line_options()
        if "include_manager_plugins" in options and "script_users" in options:
            invalid_users = get_invalid_users(options["script_users"])
            if invalid_users:
                raise ConfigurationError("Unknown system users: %s" %
                                         ", ".join(invalid_users))
            return
        show_help(
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
        if prompt_yes_no(msg, default=default):
            if "ScriptExecution" not in included_plugins:
                included_plugins.append("ScriptExecution")
            show_help(
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
                    show_help("Unknown system users: {}".format(
                        ",".join(invalid_users)))
                    self.config.script_users = None
        else:
            if "ScriptExecution" in included_plugins:
                included_plugins.remove("ScriptExecution")
        self.config.include_manager_plugins = ", ".join(included_plugins)

    def query_access_group(self):
        """Query access group from the user."""
        options = self.config.get_command_line_options()
        if "access_group" in options:
            return  # an access group is already provided, don't ask for one

        show_help(
            "You may provide an access group for this computer "
            "e.g. webservers.")
        self.prompt("access_group", "Access group", False)

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

        show_help(
            "You may provide tags for this computer e.g. server,precise.")
        while True:
            self.prompt("tags", "Tags", False)
            if self._get_invalid_tags(self.config.tags):
                show_help(
                    "Tag names may only contain alphanumeric characters.")
                self.config.tags = None  # Reset for the next prompt
            else:
                break

    def show_header(self):
        show_help(
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
        self.query_registration_key()
        self.query_proxies()
        self.query_script_plugin()
        self.query_access_group()
        self.query_tags()


def setup_init_script_and_start_client():
    "Configure the init script to start the client on boot."
    # XXX This function is misnamed; it doesn't start the client.
    sysvconfig = SysVConfig()
    sysvconfig.set_start_on_boot(True)


def stop_client_and_disable_init_script():
    """
    Stop landscape-client and change configuration to prevent starting
    landscape-client on boot.
    """
    sysvconfig = SysVConfig()
    sysvconfig.stop_landscape()
    sysvconfig.set_start_on_boot(False)


def setup_http_proxy(config):
    """
    If a http_proxy and a https_proxy value are not set then copy the values,
    if any, from the environment variables L{http_proxy} and L{https_proxy}.
    """
    if config.http_proxy is None and os.environ.get("http_proxy"):
        config.http_proxy = os.environ["http_proxy"]
    if config.https_proxy is None and os.environ.get("https_proxy"):
        config.https_proxy = os.environ["https_proxy"]


def check_account_name_and_password(config):
    """
    Ensure that silent configurations which plan to start landscape-client are
    have both an account_name and computer title.
    """
    if config.silent and not config.no_start:
        if not (config.get("account_name") and config.get("computer_title")):
            raise ConfigurationError("An account name and computer title are "
                                     "required.")


def check_script_users(config):
    """
    If the configuration allows for script execution ensure that the configured
    users are valid for that purpose.
    """
    if config.get("script_users"):
        invalid_users = get_invalid_users(config.get("script_users"))
        if invalid_users:
            raise ConfigurationError("Unknown system users: %s" %
                                     ", ".join(invalid_users))
        if not config.include_manager_plugins:
            config.include_manager_plugins = "ScriptExecution"


def decode_base64_ssl_public_certificate(config):
    """
    Decode base64 encoded SSL certificate and push that back into place in the
    config object.
    """
    # WARNING: ssl_public_certificate is misnamed, it's not the key of the
    # certificate, but the actual certificate itself.
    if config.ssl_public_key and config.ssl_public_key.startswith("base64:"):
        decoded_cert = base64.decodebytes(
            config.ssl_public_key[7:].encode("ascii"))
        config.ssl_public_key = store_public_key_data(
            config, decoded_cert)


def setup(config):
    """
    Perform steps to ensure that landscape-client is correctly configured
    before we attempt to register it with a landscape server.

    If we are not configured to be silent then interrogate the user to provide
    necessary details for registration.
    """
    bootstrap_tree(config)

    sysvconfig = SysVConfig()
    if not config.no_start:
        if config.silent:
            setup_init_script_and_start_client()
        elif not sysvconfig.is_configured_to_run():
            answer = prompt_yes_no(
                "\nThe Landscape client must be started "
                "on boot to operate correctly.\n\n"
                "Start Landscape client on boot?")
            if answer:
                setup_init_script_and_start_client()
            else:
                sys.exit("Aborting Landscape configuration")

    setup_http_proxy(config)
    check_account_name_and_password(config)
    if config.silent:
        check_script_users(config)
    else:
        script = LandscapeSetupScript(config)
        script.run()
    decode_base64_ssl_public_certificate(config)
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


def bootstrap_tree(config):
    """Create the client directories tree."""
    bootstrap_list = [
        BootstrapDirectory("$data_path", "landscape", "root", 0o755),
        BootstrapDirectory("$annotations_path", "landscape", "landscape",
                           0o755)]
    BootstrapList(bootstrap_list).bootstrap(
        data_path=config.data_path, annotations_path=config.annotations_path)


def store_public_key_data(config, certificate_data):
    """
    Write out the data from the SSL certificate provided to us, either from a
    bootstrap.conf file, or from EC2-style user-data.

    @param config:  The L{BrokerConfiguration} object in use.
    @param certificate_data: a string of data that represents the contents of
    the file to be written.
    @return the L{BrokerConfiguration} object that was passed in, updated to
    reflect the path of the ssl_public_key file.
    """
    key_filename = os.path.join(
        config.data_path,
        os.path.basename(config.get_config_filename() + ".ssl_public_key"))
    print_text("Writing SSL CA certificate to %s..." % key_filename)
    create_binary_file(key_filename, certificate_data)
    return key_filename


def failure(add_result, reason=None):
    """Handle a failed communication by recording the kind of failure."""
    if reason:
        add_result(reason)


def exchange_failure(add_result, ssl_error=False):
    """Handle a failed call by recording if the failure was SSL-related."""
    if ssl_error:
        add_result("ssl-error")
    else:
        add_result("non-ssl-error")


def handle_registration_errors(add_result, failure, connector):
    """Handle registration errors.

    The connection to the broker succeeded but the registration itself
    failed, because of invalid credentials or excessive pending computers.
    We need to trap the exceptions so they don't stacktrace (we know what is
    going on), and try to cleanly disconnect from the broker.

    Note: "results" contains a failure indication already (or will shortly)
    since the registration-failed signal will fire."""
    error = failure.trap(RegistrationError, MethodCallError)
    if error is RegistrationError:
        add_result(str(failure.value))
    connector.disconnect()


def success(add_result):
    """Handle a successful communication by recording the fact."""
    add_result("success")


def done(ignored_result, connector, reactor):
    """Clean up after communicating with the server."""
    connector.disconnect()
    reactor.stop()


def got_connection(add_result, connector, reactor, remote):
    """Handle becomming connected to a broker."""
    handlers = {"registration-done": partial(success, add_result),
                "registration-failed": partial(failure, add_result),
                "exchange-failed": partial(exchange_failure, add_result)}
    deferreds = [
        remote.call_on_event(handlers),
        remote.register().addErrback(
            partial(handle_registration_errors, add_result), connector)]
    results = gather_results(deferreds)
    results.addCallback(done, connector, reactor)
    return results


def got_error(failure, reactor, add_result, print=print):
    """Handle errors contacting broker."""
    print(failure.getTraceback(), file=sys.stderr)
    # Can't just raise SystemExit; it would be ignored by the reactor.
    add_result(SystemExit())
    reactor.stop()


def register(config, reactor=None, connector_factory=RemoteBrokerConnector,
             got_connection=got_connection, max_retries=14, on_error=None,
             results=None):
    """Instruct the Landscape Broker to register the client.

    The broker will be instructed to reload its configuration and then to
    attempt a registration.

    @param reactor: The reactor to use.  This parameter is optional because
        the client charm does not pass it.
    @param connector_factory: A callable that accepts a reactor and a
        configuration object and returns a new remote broker connection.  Used
        primarily for dependency injection.
    @param got_connection: The handler to trigger when the remote broker
        connects.  Used primarily for dependency injection.
    @param max_retries: The number of times to retry connecting to the
        landscape client service.  The delay between retries is calculated
        by Twisted and increases geometrically.
    @param on_error: A callable that will be passed a non-zero positive
        integer argument in the case that some error occurs.  This is a legacy
        API provided for use by the client charm.
    @param results: This parameter provides a mechanism to pre-seed the result
        of registering.  Used for testing.
    """
    if reactor is None:
        reactor = LandscapeReactor()

    if results is None:
        results = []
    add_result = results.append

    connector = connector_factory(reactor, config)
    connection = connector.connect(max_retries=max_retries, quiet=True)
    connection.addCallback(
        partial(got_connection, add_result, connector, reactor))
    connection.addErrback(
        partial(got_error, reactor=reactor, add_result=add_result))
    reactor.run()

    assert len(results) == 1, "We expect exactly one result."
    # Results will be things like "success" or "ssl-error".
    result = results[0]

    if isinstance(result, SystemExit):
        raise result

    # If there was an error and the caller requested that errors be reported
    # to the on_error callable, then do so.
    if result != "success" and on_error is not None:
        on_error(1)
    return result


def report_registration_outcome(what_happened, print=print):
    """Report the registration interaction outcome to the user in human-readable
    form.
    """
    messages = {
        "success": "System successfully registered.",
        "unknown-account": "Invalid account name or registration key.",
        "max-pending-computers": (
            "Maximum number of computers pending approval reached. ",
            "Login to your Landscape server account page to manage "
            "pending computer approvals."),
        "ssl-error": (
            "\nThe server's SSL information is incorrect, or fails "
            "signature verification!\n"
            "If the server is using a self-signed certificate, "
            "please ensure you supply it with the --ssl-public-key "
            "parameter."),
        "non-ssl-error": (
            "\nWe were unable to contact the server.\n"
            "Your internet connection may be down. "
            "The landscape client will continue to try and contact "
            "the server periodically.")
    }
    message = messages.get(what_happened)
    if message:
        fd = sys.stdout if what_happened == "success" else sys.stderr
        print(message, file=fd)


def determine_exit_code(what_happened):
    """Return what the application's exit code should be depending on the
    registration result.
    """
    if what_happened == "success":
        return 0
    else:
        return 2  # An error happened


def is_registered(config):
    """Return whether the client is already registered."""
    persist_filename = os.path.join(
        config.data_path, "{}.bpickle".format(BrokerService.service_name))
    persist = Persist(filename=persist_filename)
    identity = Identity(config, persist)
    return bool(identity.secure_id)


def main(args, print=print):
    """Interact with the user and the server to set up client configuration."""

    config = LandscapeSetupConfiguration()
    try:
        config.load(args)
    except ImportOptionError as error:
        print_text(str(error), error=True)
        sys.exit(1)

    if os.getuid() != 0:
        sys.exit("landscape-config must be run as root.")

    if config.init:
        bootstrap_tree(config)
        sys.exit(0)

    # Disable startup on boot and stop the client, if one is running.
    if config.disable:
        stop_client_and_disable_init_script()
        return

    # Setup client configuration.
    try:
        setup(config)
    except Exception as e:
        print_text(str(e))
        sys.exit("Aborting Landscape configuration")

    print("Please wait...")

    # Attempt to register the client.
    reactor = LandscapeReactor()
    if config.silent:
        result = register(config, reactor)
        report_registration_outcome(result, print=print)
        sys.exit(determine_exit_code(result))
    else:
        default_answer = not is_registered(config)
        answer = prompt_yes_no(
            "\nRequest a new registration for this computer now?",
            default=default_answer)
        if answer:
            result = register(config, reactor)
            report_registration_outcome(result, print=print)
            sys.exit(determine_exit_code(result))
