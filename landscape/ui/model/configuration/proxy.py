"""
This module contains a class, L{ConfigurationProxy} which pretends to be a
L{landscape.configuration.LandscapeSetupConfiguration} but actually directs
it's calls via DBus to the L{ConfigurationMechanism}.
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
        # if arglist is None or len(arglist) == 0:
        #     arglist = dbus.Array([], "s")
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

    def _get_account_name(self):
        return self._interface.get_account_name()

    def _set_account_name(self, value):
        self._interface.set_account_name(value)
    account_name = property(_get_account_name, _set_account_name)

    def _get_computer_title(self):
        return self._interface.get_computer_title()

    def _set_computer_title(self, value):
        self._interface.set_computer_title(value)
    computer_title = property(_get_computer_title, _set_computer_title)

    def _get_data_path(self):
        data_p = self._interface.get_data_path()
        return data_p

    def _set_data_path(self, value):
        self._interface.set_data_path(value)
    data_path = property(_get_data_path, _set_data_path)

    def _get_http_proxy(self):
        return self._interface.get_http_proxy()

    def _set_http_proxy(self, value):
        self._interface.set_http_proxy(value)
    http_proxy = property(_get_http_proxy, _set_http_proxy)

    def _get_https_proxy(self):
        return self._interface.get_https_proxy()

    def _set_https_proxy(self, value):
        self._interface.set_https_proxy(value)
    https_proxy = property(_get_https_proxy, _set_https_proxy)

    def _get_ping_url(self):
        return self._interface.get_ping_url()

    def _set_ping_url(self, value):
        self._interface.set_ping_url(value)
    ping_url = property(_get_ping_url, _set_ping_url)

    def _get_registration_password(self):
        return self._interface.get_registration_password()

    def _set_registration_password(self, value):
        self._interface.set_registration_password(value)
    registration_password = property(_get_registration_password,
                                     _set_registration_password)

    def _get_tags(self):
        return self._interface.get_tags()

    def _set_tags(self, value):
        self._interface.set_tags(value)
    tags = property(_get_tags, _set_tags)

    def _get_url(self):
        return self._interface.get_url()

    def _set_url(self, value):
        self._interface.set_url(value)
    url = property(_get_url, _set_url)
