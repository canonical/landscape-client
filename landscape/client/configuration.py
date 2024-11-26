"""Interactive configuration support for Landscape.

This module, and specifically L{LandscapeSetupScript}, implements the support
for the C{landscape-config} script.
"""
import getpass
import io
import logging
import os
import pwd
import re
import shlex
import sys
import textwrap
from urllib.parse import urlparse

from landscape.client import GROUP
from landscape.client import IS_SNAP
from landscape.client import USER
from landscape.client.broker.config import BrokerConfiguration
from landscape.client.broker.registration import Identity
from landscape.client.broker.service import BrokerService
from landscape.client.registration import ClientRegistrationInfo
from landscape.client.registration import register
from landscape.client.registration import RegistrationException
from landscape.client.serviceconfig import ServiceConfig
from landscape.client.serviceconfig import ServiceConfigException
from landscape.lib import base64
from landscape.lib.bootstrap import BootstrapDirectory
from landscape.lib.bootstrap import BootstrapList
from landscape.lib.compat import input
from landscape.lib.fetch import fetch
from landscape.lib.fetch import FetchError
from landscape.lib.fs import create_binary_file
from landscape.lib.logging import init_app_logging
from landscape.lib.network import get_fqdn
from landscape.lib.persist import Persist
from landscape.lib.tag import is_valid_tag


EXIT_NOT_REGISTERED = 5


class ConfigurationError(Exception):
    """Raised when required configuration values are missing."""


class ImportOptionError(ConfigurationError):
    """Raised when there are issues with handling the --import option."""


def print_text(text, end="\n", error=False):
    """Display the given text to the user, using stderr
    if flagged as an error."""
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
        value = input(f"{message} {default_msg}: ").lower()
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
                    "Extra users specified with ALL users",
                )
            user_list.remove("ALL")
        invalid_users = []
        for user in user_list:
            try:
                pwd.getpwnam(user)
            except KeyError:
                invalid_users.append(user)
        return invalid_users


class LandscapeSetupConfiguration(BrokerConfiguration):

    unsaved_options = (
        "no_start",
        "disable",
        "silent",
        "ok_no_register",
        "import_from",
        "skip_registration",
        "force_registration",
        "register_if_needed",
    )

    encoding = "utf-8"

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
                            content.decode("utf-8"),
                        ),
                    )
                elif not os.path.isfile(self.import_from):
                    raise ImportOptionError(
                        f"File {self.import_from} doesn't exist.",
                    )
                else:
                    try:
                        parser = self._get_config_object(
                            alternative_config=self.import_from,
                        )
                    except Exception:
                        raise ImportOptionError(
                            "Couldn't read configuration "
                            f"from {self.import_from}.",
                        )
            except Exception as error:
                raise ImportOptionError(str(error))

            # But real command line options have precedence.
            options = None
            if parser and self.config_section in parser:
                options = parser[self.config_section]
            if not options:
                raise ImportOptionError(
                    f"Nothing to import at {self.import_from}.",
                )
            options.update(self._command_line_options)
            self._command_line_options = options

    def fetch_import_url(self, url):
        """Handle fetching of URLs passed to --url."""

        print_text(f"Fetching configuration from {url}...")
        error_message = None
        try:
            content = fetch(url)
        except FetchError as error:
            error_message = str(error)
        if error_message is not None:
            raise ImportOptionError(
                f"Couldn't download configuration from {url}: {error_message}",
            )
        return content

    def make_parser(self):
        """
        Specialize the parser, adding configure-specific options.
        """
        parser = super().make_parser()

        parser.add_argument(
            "--import",
            dest="import_from",
            metavar="FILENAME_OR_URL",
            help="Filename or URL to import configuration from. "
            "Imported options behave as if they were "
            "passed in the command line, with precedence "
            "being given to real command line options.",
        )
        parser.add_argument(
            "--script-users",
            metavar="USERS",
            help="A comma-separated list of users to allow "
            "scripts to run. To allow scripts to be run "
            "by any user, enter: ALL",
        )
        parser.add_argument(
            "--include-manager-plugins",
            metavar="PLUGINS",
            default="",
            help="A comma-separated list of manager plugins "
            "to enable in addition to the defaults.",
        )
        parser.add_argument(
            "--manage-sources-list-d",
            nargs="?",
            default="true",
            const="true",
            help="Repository profiles manage the files in "
            "’etc/apt/sources.list.d'. (default: true)",
        )
        parser.add_argument(
            "-n",
            "--no-start",
            action="store_true",
            help="Don't start the client automatically.",
        )
        parser.add_argument(
            "--ok-no-register",
            action="store_true",
            help="Return exit code 0 instead of 2 if the client "
            "can't be registered.",
        )
        parser.add_argument(
            "--silent",
            action="store_true",
            default=False,
            help="Run without manual interaction.",
        )
        parser.add_argument(
            "--disable",
            action="store_true",
            default=False,
            help="Stop running clients and disable start at boot.",
        )
        parser.add_argument(
            "--init",
            action="store_true",
            default=False,
            help="Set up the client directories structure and exit.",
        )
        parser.add_argument(
            "--is-registered",
            action="store_true",
            help="Exit with code 0 (success) if client is "
            "registered else returns {}. Displays "
            "registration info.".format(EXIT_NOT_REGISTERED),
        )
        parser.add_argument(
            "--skip-registration",
            action="store_true",
            help="Don't send a new registration request",
        )
        parser.add_argument(
            "--force-registration",
            action="store_true",
            help="Force sending a new registration request",
        )
        parser.add_argument(
            "--register-if-needed",
            action="store_true",
            help=(
                "Send a new registration request only if one has not been sent"
            ),
        )
        parser.add_argument(
            "--actively-registered",
            action="store_true",
            help="Exit with code 0 (success) if client is "
            "registered else returns {}. Displays "
            "registration info.".format(EXIT_NOT_REGISTERED),
        )
        parser.add_argument(
            "--registration-sent",
            action="store_true",
            help="Exit with code 0 (success) if client is "
            "registered else returns {}. Displays "
            "registration info.".format(EXIT_NOT_REGISTERED),
        )
        return parser


class LandscapeSetupScript:
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
        self.landscape_domain = None

    def get_domain(self):
        domain = self.landscape_domain
        if domain:
            return domain
        url = self.config.url
        if url:
            return urlparse(url).netloc
        return "landscape.canonical.com"

    def prompt_get_input(self, msg, required):
        """Prompt the user on the terminal for a value

        @param msg: Message to prompt user with
        @param required: True if value must be entered
        """
        while True:
            value = input(msg).strip()
            if value:
                return value
            elif not required:
                break
            show_help("This option is required to configure Landscape.")

    def prompt(self, option, msg, required=False, default=None):
        """Prompt the user on the terminal for a value.

        @param option: The attribute of C{self.config} that contains the
            default and which the value will be assigned to.
        @param msg: The message to prompt the user with (via C{input}).
        @param required: If True, the user will be required to enter a value
            before continuing.
        @param default: Default only if set and no current value present
        """
        cur_value = getattr(self.config, option, None)
        if cur_value:
            default = cur_value
        if default:
            msg += f" [{default}]: "
        else:
            msg += ": "
        required = required and not (bool(default))
        result = self.prompt_get_input(msg, required)
        if result:
            setattr(self.config, option, result)
        elif default:
            setattr(self.config, option, default)

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
            computer in the Landscape dashboard.
            """,
        )
        self.prompt(
            "computer_title",
            "This computer's title",
            False,
            default=get_fqdn(),
        )

    def query_account_name(self):
        if "account_name" in self.config.get_command_line_options():
            return

        if not self.landscape_domain:
            show_help(
                """
                You must now specify the name of the Landscape account you
                want to register this computer with. Your account name is shown
                under 'Account name' at https://landscape.canonical.com .
                """,
            )
            self.prompt("account_name", "Account name", True)
        else:
            self.config.account_name = "standalone"

    def query_registration_key(self):
        command_line_options = self.config.get_command_line_options()
        if "registration_key" in command_line_options:
            return

        show_help(
            f"""
            A Registration Key prevents unauthorized registration attempts.

            Provide the Registration Key found at:
            https://{self.get_domain()}/account/{self.config.account_name}
            """,  # noqa: E501
        )

        self.password_prompt("registration_key", "(Optional) Registration Key")

    def query_proxies(self):
        options = self.config.get_command_line_options()
        if "http_proxy" in options and "https_proxy" in options:
            return

        show_help(
            """
            If your network requires you to use a proxy, provide the address of
            these proxies now.
            """,
        )

        if "http_proxy" not in options:
            self.prompt("http_proxy", "HTTP proxy URL")
        if "https_proxy" not in options:
            self.prompt("https_proxy", "HTTPS proxy URL")

    def query_script_plugin(self):
        options = self.config.get_command_line_options()
        if "include_manager_plugins" in options and "script_users" in options:
            invalid_users = get_invalid_users(options["script_users"])
            if invalid_users:
                raise ConfigurationError(
                    "Unknown system users: {}".format(
                        ", ".join(invalid_users),
                    ),
                )
            return

    def query_access_group(self):
        """Query access group from the user."""
        options = self.config.get_command_line_options()
        if "access_group" in options:
            return  # an access group is already provided, don't ask for one

        show_help(
            "You may provide an access group for this computer "
            "e.g. webservers.",
        )
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
                raise ConfigurationError(
                    "Invalid tags: {}".format(", ".join(invalid_tags)),
                )
            return

    def query_landscape_edition(self):
        show_help(
            "Manage this machine with Landscape "
            "(https://ubuntu.com/landscape):\n",
        )
        options = self.config.get_command_line_options()
        if "ping_url" in options and "url" in options:
            return
        if prompt_yes_no(
            "Will you be using your own Self-Hosted Landscape installation?",
            default=False,
        ):
            show_help(
                "Provide the fully qualified domain name "
                "of your Landscape Server e.g. "
                "landscape.example.com",
            )
            self.landscape_domain = self.prompt_get_input(
                "Landscape Domain: ",
                True,
            ).strip("/")
            self.landscape_domain = re.sub(
                r"^https?://",
                "",
                self.landscape_domain,
            )
            self.config.ping_url = f"http://{self.landscape_domain}/ping"
            self.config.url = f"https://{self.landscape_domain}/message-system"
        else:
            self.landscape_domain = ""
            self.config.ping_url = self.config._command_line_defaults[
                "ping_url"
            ]
            self.config.url = self.config._command_line_defaults["url"]
            if self.config.account_name == "standalone":
                self.config.account_name = ""

    def show_summary(self):

        tx = f"""A summary of the provided information:
            Computer's Title: {self.config.computer_title}
            Account Name: {self.config.account_name}
            Landscape FQDN: {self.get_domain()}
            Registration Key: {True if self.config.registration_key else False}
            """
        show_help(tx)
        if self.config.http_proxy or self.config.https_proxy:
            show_help(
                f"""HTTPS Proxy: {self.config.https_proxy}
                    HTTP  Proxy: {self.config.http_proxy}""",
            )

        params = (
            "account_name",
            "url",
            "ping_url",
            "registration_key",
            "https_proxy",
            "http_proxy",
        )
        cmd = [
            "sudo",
            "landscape-client.config" if IS_SNAP else "landscape-config",
        ]
        for param in params:
            value = self.config.get(param)
            if value:
                if param in self.config._command_line_defaults:
                    if value == self.config._command_line_defaults[param]:
                        continue
                cmd.append("--" + param.replace("_", "-"))
                if param == "registration_key":
                    cmd.append("HIDDEN")
                else:
                    cmd.append(shlex.quote(value))
        show_help(
            "The landscape config parameters to repeat this registration"
            " on another machine are:",
        )
        show_help(" ".join(cmd))

    def run(self):
        """Kick off the interactive process which prompts the user for data.

        Data will be saved to C{self.config}.
        """
        self.query_landscape_edition()
        self.query_computer_title()
        self.query_account_name()
        self.query_registration_key()
        self.query_proxies()
        self.query_script_plugin()
        self.query_tags()
        self.show_summary()


def stop_client_and_disable_init_script():
    """
    Stop landscape-client and change configuration to prevent starting
    landscape-client on boot.
    """
    ServiceConfig.stop_landscape()
    ServiceConfig.set_start_on_boot(False)


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
            raise ConfigurationError(
                "An account name and computer title are required.",
            )


def check_script_users(config):
    """
    If the configuration allows for script execution ensure that the configured
    users are valid for that purpose.
    """
    if config.get("script_users"):
        invalid_users = get_invalid_users(config.get("script_users"))
        if invalid_users:
            raise ConfigurationError(
                "Unknown system users: {}".format(", ".join(invalid_users)),
            )
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
            config.ssl_public_key[7:].encode("ascii"),
        )
        config.ssl_public_key = store_public_key_data(config, decoded_cert)


def setup(config) -> Identity:
    """
    Perform steps to ensure that landscape-client is correctly configured
    before we attempt to register it with a landscape server.

    If we are not configured to be silent then interrogate the user to provide
    necessary details for registration.

    :returns: a registration identity representing the configuration.
    """
    bootstrap_tree(config)

    if not config.no_start:
        if config.silent:
            ServiceConfig.set_start_on_boot(True)
        elif not ServiceConfig.is_configured_to_run():
            ServiceConfig.set_start_on_boot(True)

    setup_http_proxy(config)
    check_account_name_and_password(config)
    if config.silent:
        check_script_users(config)
    else:
        script = LandscapeSetupScript(config)
        script.run()
    decode_base64_ssl_public_certificate(config)
    config.write()

    persist = Persist(
        filename=os.path.join(
            config.data_path,
            f"{BrokerService.service_name}.bpickle",
        ),
        user=USER,
        group=GROUP,
    )

    return Identity(config, persist)


def restart_client(config):
    """Restart the client to ensure that it's using the new configuration."""
    if not config.no_start:
        try:
            secure_id = get_secure_id(config)
            if not secure_id:
                set_secure_id(config, "registering")
            ServiceConfig.restart_landscape()
        except ServiceConfigException as exc:
            print_text(str(exc), error=True)
            exit_code = 2
            if config.ok_no_register:
                exit_code = 0
            sys.exit(exit_code)


def bootstrap_tree(config):
    """Create the client directories tree."""
    bootstrap_list = [
        BootstrapDirectory("$data_path", USER, GROUP, 0o755),
        BootstrapDirectory("$annotations_path", USER, GROUP, 0o755),
    ]
    BootstrapList(bootstrap_list).bootstrap(
        data_path=config.data_path,
        annotations_path=config.annotations_path,
    )


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
        os.path.basename(config.get_config_filename() + ".ssl_public_key"),
    )
    print_text(f"Writing SSL CA certificate to {key_filename}...")
    create_binary_file(key_filename, certificate_data)
    return key_filename


def attempt_registration(
    identity: Identity,
    config: LandscapeSetupConfiguration,
    retries: int = 14,
) -> int:
    """Attempts to send a registration message, reporting the result to stdout
    or stderr. Retries `retries` times.

    :returns: an exit code based on the registration result.
    """

    client_info = ClientRegistrationInfo.from_identity(identity)

    for retry in range(retries):
        if retry > 0:
            print(f"Retrying... (attempt {retry + 1} of {retries})")

        try:
            # We pass the cainfo in the case where a
            # self-signed certificate is used.
            registration_info = register(
                client_info,
                config.url,
                cainfo=config.ssl_public_key,
            )

            break
        except RegistrationException as e:
            # This is unlikely to be resolved by the time we retry, so we fail
            # immediately.
            logging.error(f"Registration failed: {e}")
            return 2
        except Exception:
            # Retrying...
            logging.exception("Registration failed")
    else:
        # We're finished retrying and haven't succeeded yet.
        return 2

    set_secure_id(
        config,
        registration_info.secure_id,
        registration_info.insecure_id,
    )

    print("Registration request sent successfully")
    restart_client(config)

    return 0


def registration_sent(config):
    """
    Return whether the client has sent a registration request to the server.
    For now does same thing as is_registered as to make function name more
    clear with what is performed. This is the legacy behaviour of
    --is-registered and the name will be changed in a future release.
    """
    persist_filename = os.path.join(
        config.data_path,
        f"{BrokerService.service_name}.bpickle",
    )
    persist = Persist(filename=persist_filename, user=USER, group=GROUP)
    identity = Identity(config, persist)
    return bool(identity.secure_id)


def actively_registered(config):
    """Return whether or not the client is currently registered with server"""
    persist_filename = os.path.join(
        config.data_path,
        f"{BrokerService.service_name}.bpickle",
    )
    persist = Persist(filename=persist_filename, user=USER, group=GROUP)
    accepted_types = persist.get("message-store.accepted-types")
    if accepted_types is not None:
        return len(accepted_types) > 1 and "register" not in accepted_types
    return False


def registration_info_text(config, registration_status):
    """
    A simple output displaying whether the client is registered or not, the
    account name, and config and data paths
    """

    config_path = os.path.abspath(config._config_filename)

    text = textwrap.dedent(
        """
                           Registered:    {}
                           Config Path:   {}
                           Data Path      {}""".format(
            registration_status,
            config_path,
            config.data_path,
        ),
    )
    if registration_status:
        text += f"\nAccount Name:  {config.account_name}"

    return text


def set_secure_id(config, new_id, insecure_id=None):
    """Persists a secure id in the identity data file. This is used to indicate
    whether we are currently in the process of registering.
    """
    persist = Persist(
        filename=os.path.join(
            config.data_path,
            f"{BrokerService.service_name}.bpickle",
        ),
        user=USER,
        group=GROUP,
    )
    identity = Identity(config, persist)
    identity.secure_id = new_id
    if insecure_id is not None:
        identity.insecure_id = insecure_id
    persist.save()


def get_secure_id(config):
    persist = Persist(
        filename=os.path.join(
            config.data_path,
            f"{BrokerService.service_name}.bpickle",
        ),
        user=USER,
        group=GROUP,
    )
    identity = Identity(config, persist)
    return identity.secure_id


def main(args, print=print):  # noqa: C901
    """Interact with the user and the server to set up client configuration."""
    config = LandscapeSetupConfiguration()
    try:
        config.load(args)
    except ImportOptionError as error:
        print_text(str(error), error=True)
        sys.exit(1)

    init_app_logging(
        config.log_dir,
        config.log_level,
        "landscape-config",
        config.quiet,
    )

    if config.skip_registration and config.force_registration:
        sys.exit(
            "Do not set both skip registration "
            "and force registration together.",
        )

    already_registered = registration_sent(config)

    if config.is_registered or config.registration_sent:

        registration_status = already_registered

        info_text = registration_info_text(config, registration_status)
        print(info_text)

        if registration_status:
            sys.exit(0)
        else:
            sys.exit(EXIT_NOT_REGISTERED)

    if config.actively_registered:
        currently_registered = actively_registered(config)

        info_text = registration_info_text(config, currently_registered)
        print(info_text)

        if currently_registered:
            sys.exit(0)
        else:
            sys.exit(EXIT_NOT_REGISTERED)

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
        identity = setup(config)
    except Exception as e:
        print_text(str(e))
        sys.exit("Aborting Landscape configuration")

    if config.skip_registration:
        print("Registration skipped.")
        return

    should_register = False

    if config.force_registration:
        should_register = True
    elif config.silent and not config.register_if_needed:
        should_register = True
    elif config.register_if_needed:
        should_register = not already_registered
    else:
        default_answer = not already_registered
        should_register = prompt_yes_no(
            "\nRequest a new registration for this computer now?",
            default=default_answer,
        )

    exit_code = 0

    if should_register:
        exit_code = attempt_registration(identity, config)
        restart_client(config)
    elif config.silent:
        restart_client(config)
    else:
        print("Registration skipped.")

    sys.exit(exit_code)
