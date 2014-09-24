import os
import sys

from configobj import ConfigObj, ConfigObjError

from logging import (getLevelName, getLogger,
                     FileHandler, StreamHandler, Formatter)

from optparse import OptionParser, SUPPRESS_HELP

from landscape import VERSION
from landscape.lib.persist import Persist

from landscape.upgraders import UPGRADE_MANAGERS


def init_logging(configuration, program_name):
    """Given a basic configuration, set up logging."""
    handlers = []
    if not os.path.exists(configuration.log_dir):
        os.makedirs(configuration.log_dir)
    log_filename = os.path.join(configuration.log_dir, program_name + ".log")
    handlers.append(FileHandler(log_filename))
    if not configuration.quiet:
        handlers.append(StreamHandler(sys.stdout))
    getLogger().setLevel(getLevelName(configuration.log_level.upper()))
    for handler in handlers:
        getLogger().addHandler(handler)
        format = ("%(asctime)s %(levelname)-8s [%(threadName)-10s] "
                  "%(message)s")
        handler.setFormatter(Formatter(format))


class ConfigSpecOptionParser(OptionParser):

    _config_spec_definitions = {}

    def __init__(self, unsaved_options=None):
        OptionParser.__init__(self, unsaved_options)

    def add_option(self, *args, **kwargs):
        option = OptionParser.add_option(self, *args, **kwargs)
        print dir(option)
        print option.get_opt_string()
        return option


class BaseConfiguration(object):
    """Base class for configuration implementations.

    @cvar required_options: Optionally, a sequence of key names to require when
        reading or writing a configuration.
    @cvar unsaved_options: Optionally, a sequence of key names to never write
        to the configuration file.  This is useful when you want to provide
        command-line options that should never end up in a configuration file.
    @cvar default_config_filenames: A sequence of filenames to check when
        reading or writing a configuration.

    Default values for supported options are set as in L{make_parser}.
    """

    required_options = ()
    unsaved_options = ()
    default_config_filenames = ["/etc/landscape/client.conf"]
    if (os.path.dirname(os.path.abspath(sys.argv[0]))
        == os.path.abspath("scripts")):
        default_config_filenames.insert(0, "landscape-client.conf")
    default_config_filenames = tuple(default_config_filenames)
    config_section = "client"

    def __init__(self):
        self._set_options = {}
        self._command_line_args = []
        self._command_line_options = {}
        self._config_filename = None
        self._config_file_options = {}
        self._parser = self.make_parser()
        self._command_line_defaults = self._parser.defaults.copy()
        # We don't want them mixed with explicitly given options,
        # otherwise we can't define the precedence properly.
        self._parser.defaults.clear()

    def __getattr__(self, name):
        """Find and return the value of the given configuration parameter.

        The following sources will be searched:
          - The attributes that were explicitly set on this object,
          - The parameters specified on the command line,
          - The parameters specified in the configuration file, and
          - The defaults.

        If no values are found and the parameter does exist as a possible
        parameter, C{None} is returned.

        Otherwise C{AttributeError} is raised.
        """
        for options in [self._set_options,
                        self._command_line_options,
                        self._config_file_options,
                        self._command_line_defaults]:
            if name in options:
                value = options[name]
                break
        else:
            if self._parser.has_option("--" + name.replace("_", "-")):
                value = None
            else:
                raise AttributeError(name)
        if isinstance(value, basestring):
            option = self._parser.get_option("--" + name.replace("_", "-"))
            if option is not None:
                value = option.convert_value(None, value)
        return value

    def clone(self):
        """
        Return a new configuration object, with the same settings as this one.
        """
        config = self.__class__()
        config._set_options = self._set_options.copy()
        config._command_line_options = self._command_line_options.copy()
        config._config_filename = self._config_filename
        config._config_file_options = self._config_file_options.copy()
        return config

    def get(self, name, default=None):
        """Return the value of the C{name} option or C{default}."""
        try:
            return self.__getattr__(name)
        except AttributeError:
            return default

    def __setattr__(self, name, value):
        """Set a configuration parameter.

        If the name begins with C{_}, it will only be set on this object and
        not stored in the configuration file.
        """
        if name.startswith("_"):
            super(BaseConfiguration, self).__setattr__(name, value)
        else:
            self._set_options[name] = value

    def reload(self):
        """Reload options using the configured command line arguments.

        @see: L{load_command_line}
        """
        self.load(self._command_line_args)

    def load(self, args, accept_nonexistent_default_config=False):
        """
        Load configuration data from command line arguments and a config file.

        @param accept_nonexistent_default_config: If True, don't complain if
            default configuration files aren't found

        @raise: A SystemExit if the arguments are bad.

        """
        self.load_command_line(args)

        if self.config:
            config_filenames = [self.config]
            allow_missing = False
        else:
            config_filenames = self.default_config_filenames
            allow_missing = accept_nonexistent_default_config
        # Parse configuration file, if found.
        for config_filename in config_filenames:
            if (os.path.isfile(config_filename)
                and os.access(config_filename, os.R_OK)):

                self.load_configuration_file(config_filename)
                break

        else:
            if not allow_missing:
                if len(config_filenames) == 1:
                    message = (
                        "error: config file %s can't be read" %
                        config_filenames[0])
                else:
                    message = "error: no config file could be read"
                sys.exit(message)

        self._load_external_options()

        # Check that all needed options were given.
        for option in self.required_options:
            if not getattr(self, option):
                sys.exit("error: must specify --%s "
                         "or the '%s' directive in the config file."
                         % (option.replace('_', '-'), option))

    def _load_external_options(self):
        """Hook for loading options from elsewhere (e.g. for --import)."""

    def load_command_line(self, args):
        """Load configuration data from the given command line."""
        self._command_line_args = args
        values = self._parser.parse_args(args)[0]
        self._command_line_options = vars(values)

    def load_configuration_file(self, filename):
        """Load configuration data from the given file name.

        If any data has already been set on this configuration object,
        then the old data will take precedence.
        """
        self._config_filename = filename
        config_obj = self._get_config_object()
        try:
            self._config_file_options = config_obj[self.config_section]
        except KeyError:
            pass

    def _get_config_object(self, alternative_config=None):
        """Create a L{ConfigObj} consistent with our preferences.

        @param config_source: Optional readable source to read from instead of
            the default configuration file.
        """
        config_source = alternative_config or self.get_config_filename()
        # Setting list_values to False prevents ConfigObj from being "smart"
        # about lists (it now treats them as strings). See bug #1228301 for
        # more context.
        # Setting raise_errors to False causes ConfigObj to batch all parsing
        # errors into one ConfigObjError raised at the end of the parse instead
        # of raising the first one and then exiting.  This also allows us to
        # recover the good config values in the error handler below.
        # Setting write_empty_values to True prevents configObj writes
        # from writing "" as an empty value, which get_plugins interprets as
        # '""' which search for a plugin named "".  See bug #1241821.
        try:
            config_obj = ConfigObj(config_source, list_values=False,
                                   raise_errors=False, write_empty_values=True)
        except ConfigObjError, e:
            logger = getLogger()
            logger.warn(str(e))
            # Good configuration values are recovered here
            config_obj = e.config
        return config_obj

    def write(self):
        """Write back configuration to the configuration file.

        Values which match the default option in the parser won't be saved.

        Options are considered in the following precedence:

          1. Manually set options (C{config.option = value})
          2. Options passed in the command line
          3. Previously existent options in the configuration file

        The filename picked for saving configuration options is the one
        returned by L{get_config_filename}.
        """

        # The filename we'll write to
        filename = self.get_config_filename()

        # Make sure we read the old values from the config file so that we
        # don't remove *unrelated* values.
        config_obj = self._get_config_object()
        if not self.config_section in config_obj:
            config_obj[self.config_section] = {}
        all_options = self._config_file_options.copy()
        all_options.update(self._command_line_options)
        all_options.update(self._set_options)
        section = config_obj[self.config_section]
        for name, value in all_options.items():
            if name != "config" and name not in self.unsaved_options:
                if (value == self._command_line_defaults.get(name) and
                    name not in self._config_file_options and
                    name not in self._command_line_options):
                    # We don't want to write this value to the config file
                    # as it is default value and as not present in the
                    # config file
                    if name in config_obj[self.config_section]:
                        del config_obj[self.config_section][name]
                else:
                    section[name] = value
        config_obj[self.config_section] = section
        config_obj.filename = filename
        config_obj.write()

    def make_parser(self):
        """Parser factory for supported options

        @return: An L{OptionParser} preset with options that all
            landscape-related programs accept. These include
              - C{config} (C{None})
              - C{data_path} (C{"/var/lib/landscape/client/"})
        """
        parser = OptionParser(version=VERSION)
        parser.add_option("-c", "--config", metavar="FILE",
                          help="Use config from this file (any command line "
                               "options override settings from the file) "
                               "(default: '/etc/landscape/client.conf').")
        parser.add_option("-d", "--data-path", metavar="PATH",
                          default="/var/lib/landscape/client/",
                          help="The directory to store data files in "
                               "(default: '/var/lib/landscape/client/').")
        return parser

    def get_config_filename(self):
        """Pick the proper configuration file.

        The picked filename is:
          1. C{self.config}, if defined
          2. The last loaded configuration file, if any
          3. The first filename in C{self.default_config_filenames}
        """
        if self.config:
            return self.config
        if self._config_filename:
            return self._config_filename
        if self.default_config_filenames:
            for potential_config_file in self.default_config_filenames:
                if os.access(potential_config_file, os.R_OK):
                    return potential_config_file
            return self.default_config_filenames[0]
        return None

    def get_command_line_options(self):
        """Get currently loaded command line options.

        @see: L{load_command_line}
        """
        return self._command_line_options


class Configuration(BaseConfiguration):
    """Configuration data for Landscape client.

    This contains all simple data, some of it calculated.
    """

    DEFAULT_URL = "https://landscape.canonical.com/message-system"

    def make_parser(self):
        """Parser factory for supported options.

        @return: An L{OptionParser} preset for all options
            from L{BaseConfiguration.make_parser} plus:
              - C{quiet} (C{False})
              - C{log_dir} (C{"/var/log/landscape"})
              - C{log_level} (C{"info"})
              - C{url} (C{"http://landscape.canonical.com/message-system"})
              - C{ping_url} (C{"http://landscape.canonical.com/ping"})
              - C{ssl_public_key}
              - C{ignore_sigint} (C{False})
        """
        parser = super(Configuration, self).make_parser()
        parser.add_option("-q", "--quiet", default=False, action="store_true",
                          help="Do not log to the standard output.")
        parser.add_option("-l", "--log-dir", metavar="FILE",
                          help="The directory to write log files to "
                               "(default: '/var/log/landscape').",
                          default="/var/log/landscape")
        parser.add_option("--log-level", default="info",
                          help="One of debug, info, warning, error or "
                               "critical.")
        parser.add_option("-u", "--url", default=self.DEFAULT_URL,
                          help="The server URL to connect to.")
        parser.add_option("--ping-url",
                          help="The URL to perform lightweight exchange "
                               "initiation with.",
                          default="http://landscape.canonical.com/ping")
        parser.add_option("-k", "--ssl-public-key",
                          help="The public SSL key to verify the server. "
                               "Only used if the given URL is https.")
        parser.add_option("--ignore-sigint", action="store_true",
                          default=False, help="Ignore interrupt signals.")
        parser.add_option("--ignore-sigusr1", action="store_true",
                          default=False, help="Ignore SIGUSR1 signal to "
                                              "rotate logs.")
        parser.add_option("--package-monitor-interval", default=30 * 60,
                          type="int",
                          help="The interval between package monitor runs "
                               "(default: 1800).")
        parser.add_option("--apt-update-interval", default=6 * 60 * 60,
                          type="int",
                          help="The interval between apt update runs "
                               "(default: 21600).")
        parser.add_option("--flush-interval", default=5 * 60, type="int",
                          metavar="INTERVAL",
                          help="The number of seconds between flushes to disk "
                               "for persistent data.")

        # Hidden options, used for load-testing to run in-process clones
        parser.add_option("--clones", default=0, type=int, help=SUPPRESS_HELP)
        parser.add_option("--start-clones-over", default=25 * 60, type=int,
                          help=SUPPRESS_HELP)

        return parser

    @property
    def sockets_path(self):
        """Return the path to the directory where Unix sockets are created."""
        return os.path.join(self.data_path, "sockets")

    @property
    def annotations_path(self):
        """
        Return the path to the directory where additional annotation files can
        be stored.
        """
        return os.path.join(self.data_path, "annotations.d")

    @property
    def juju_filename(self):
        """The path to the previously sinlge juju-info file for
        backwards-compatibility."""
        return os.path.join(self.data_path, "juju-info.json")


def get_versioned_persist(service):
    """Get a L{Persist} database with upgrade rules applied.

    Load a L{Persist} database for the given C{service} and upgrade or
    mark as current, as necessary.
    """
    persist = Persist(filename=service.persist_filename)
    upgrade_manager = UPGRADE_MANAGERS[service.service_name]
    if os.path.exists(service.persist_filename):
        upgrade_manager.apply(persist)
    else:
        upgrade_manager.initialize(persist)
    persist.save(service.persist_filename)
    return persist
