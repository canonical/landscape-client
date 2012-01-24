"""
This module contains a class, L{ConfigurationProxy} which pretends to be a
L{landscape.configuration.LandscapeSetupConfiguration} but actually directs
its calls via DBus to the L{ConfigurationMechanism}.
"""

import dbus

from landscape.ui.model.configuration.mechanism import (
    SERVICE_NAME, INTERFACE_NAME, OBJECT_PATH)
from landscape.configuration import LandscapeSetupConfiguration


class ConfigurationProxy(object):
    """
    L{ConfigurationProxy} attempts to be a drop-in replacement for
    L{LandscapeSetupConfiguration} allowing applications run by user accounts
    with the correct rights (as defined by a PolicyKit policy file) to interact
    with the landscape client configuration via a DBus service.  This is the
    RightThing(TM) for PolicyKit and therefore for GNOME/Unity.

    The canonical case for this is L{landscape-client-settings-ui}.
    """

    def __init__(self, bus=None):
        self._interface = None
        self._setup_interface(bus)

    def _setup_interface(self, bus):
        """
        Redefining L{_setup_interface} allows us to bypass DBus for more
        convenient testing in some instances.
        """
        if bus is None:
            self._bus = dbus.SystemBus()
        else:
            self._bus = bus
        self._remote_object = self._bus.get_object(SERVICE_NAME, OBJECT_PATH)
        self._interface = dbus.Interface(self._remote_object, INTERFACE_NAME)

    def load(self, arglist):
        if arglist is None or len(arglist) == 0:
            al = ""
        else:
            al = chr(0x1e).join(arglist)
        self._interface.load(al)

    load.__doc__ = LandscapeSetupConfiguration.load.__doc__

    def reload(self):
        self._interface.reload()
    reload.__doc__ = LandscapeSetupConfiguration.reload.__doc__

    def write(self):
        self._interface.write()
    write.__doc__ = LandscapeSetupConfiguration.write.__doc__

    def get_config_filename(self):
        return self._interface.get_config_filename()
    get_config_filename.__doc__ = \
        LandscapeSetupConfiguration.get_config_filename.__doc__

    def _delegate_to_interface(field):

        def get(self):
            return self._interface.get(field)

        def set(self, value):
            self._interface.set(field, value)

        return get, set

    account_name = property(*_delegate_to_interface("account_name"))
    computer_title = property(*_delegate_to_interface("computer_title"))
    data_path = property(*_delegate_to_interface("data_path"))
    http_proxy = property(*_delegate_to_interface("http_proxy"))
    https_proxy = property(*_delegate_to_interface("https_proxy"))
    ping_url = property(*_delegate_to_interface("ping_url"))
    registration_password = property(
        *_delegate_to_interface("registration_password"))
    tags = property(*_delegate_to_interface("tags"))
    url = property(*_delegate_to_interface("url"))
