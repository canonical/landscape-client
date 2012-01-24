import logging
import types
import sys

from smart.interface import Interface
from smart.const import ERROR, WARNING, INFO, DEBUG

import smart.interfaces


class LandscapeInterface(Interface):

    __output = ""
    __failed = False

    def reset_for_landscape(self):
        """Reset output and failed flag."""
        self.__failed = False
        self.__output = u""

    def get_output_for_landscape(self):
        """showOutput() is cached, and returned by this method."""
        return self.__output

    def has_failed_for_landscape(self):
        """Return true if any error() messages were logged."""
        return self.__failed

    def error(self, msg):
        self.__failed = True
        # Calling these logging.* functions here instead of message()
        # below will output the message or not depending on the debug
        # level set in landscape-client, rather than the one set in
        # Smart's configuration.
        logging.error("[Smart] %s", msg)
        super(LandscapeInterface, self).error(msg)

    def warning(self, msg):
        logging.warning("[Smart] %s", msg)
        super(LandscapeInterface, self).warning(msg)

    def info(self, msg):
        logging.info("[Smart] %s", msg)
        super(LandscapeInterface, self).info(msg)

    def debug(self, msg):
        logging.debug("[Smart] %s", msg)
        super(LandscapeInterface, self).debug(msg)

    def message(self, level, msg):
        prefix = {ERROR: "ERROR", WARNING: "WARNING",
                  INFO: "INFO", DEBUG: "DEBUG"}.get(level)
        self.showOutput("%s: %s\n" % (prefix, msg))

    def showOutput(self, output):
        if not isinstance(output, unicode):
            try:
                output = output.decode("utf-8")
            except UnicodeDecodeError:
                output = output.decode("ascii", "replace")
        self.__output += output


class LandscapeInterfaceModule(types.ModuleType):

    def __init__(self):
        super(LandscapeInterfaceModule, self).__init__("landscape")

    def create(self, ctrl, command=None, argv=None):
        return LandscapeInterface(ctrl)


def install_landscape_interface():
    if "smart.interfaces.landscape" not in sys.modules:
        # Plug the interface in a place Smart will recognize.
        smart.interfaces.landscape = LandscapeInterfaceModule()
        sys.modules["smart.interfaces.landscape"] = smart.interfaces.landscape


def uninstall_landscape_interface():
    sys.modules.pop("smart.interfaces.landscape", None)
