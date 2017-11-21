from __future__ import absolute_import

import logging

from .format import format_object


class PluginConfigError(Exception):
    """There was an error registering or configuring a plugin."""


class PluginRegistry(object):
    """A central integration point for plugins."""

    def __init__(self):
        self._plugins = []
        self._plugin_names = {}

    def add(self, plugin):
        """Register a plugin.

        The plugin's C{register} method will be called with this registry as
        its argument.

        If the plugin has a C{plugin_name} attribute, it will be possible to
        look up the plugin later with L{get_plugin}.
        """
        logging.info("Registering plugin %s.", format_object(plugin))
        self._plugins.append(plugin)
        if hasattr(plugin, "plugin_name"):
            self._plugin_names[plugin.plugin_name] = plugin
        plugin.register(self)

    def get_plugins(self):
        """Get the list of plugins."""
        return self._plugins

    def get_plugin(self, name):
        """Get a particular plugin by name."""
        return self._plugin_names[name]


class Plugin(object):
    """A convenience for writing plugins.

    This provides a register method which will set up a bunch of
    reactor handlers in the idiomatic way.

    If C{run} is defined on subclasses, it will be called every C{run_interval}
    seconds after being registered.

    @cvar run_interval: The interval, in seconds, to execute the
    C{run} method. If set to C{None}, then C{run} will not be
    scheduled.
    """

    run_interval = 5

    def register(self, registry):
        self.registry = registry
        if hasattr(self, "run") and self.run_interval is not None:
            registry.reactor.call_every(self.run_interval, self.run)
