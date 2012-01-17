"""
This module contains a class, L{ConfigurationProxy} which pretends to be a
L{landscape.configuration.LandscapeSetupConfiguration} but actually directs
it's calls via DBus to the L{ConfigurationMechanism}.
"""

import dbus

from landscape.ui.model.configuration.mechanism import (
    SERVICE_NAME, INTERFACE_NAME, OBJECT_PATH)


class ConfigurationProxy(object):

    def __init__(self, bus=None):
        self._iface = None
        self._setup_iface(bus)

    def _setup_iface(self, bus):
        if bus is None:
            self._bus = dbus.SystemBus()
        else:
            self._bus = bus
        self._remote_object = self._bus.get_object(SERVICE_NAME,
                                                   OBJECT_PATH)
        self._iface = dbus.Interface(self._remote_object, INTERFACE_NAME)

    def load(self, args):
        self._iface.load(args)

    def reload(self):
        self._iface.reload()

    def write(self):
        self._iface.write()
        
    def _get_account_name(self):
        return self._iface.get_account_name()
    def _set_account_name(self, value):
        self._iface.set_account_name(value)
    account_name = property(_get_account_name, _set_account_name)
        
    def _get_computer_title(self):
        return self._iface.get_computer_title()
    def _set_computer_title(self, value):
        self._iface.set_computer_title(value)
    computer_title = property(_get_computer_title, _set_computer_title)

    def _get_data_path(self):
        return self._iface.get_data_path()
    def _set_data_path(self, value):
        self._iface.set_data_path(value)
    data_path = property(_get_data_path, _set_data_path)

    def _get_http_proxy(self):
        return self._iface.get_http_proxy()
    def _set_http_proxy(self, value):
        self._iface.set_http_proxy(value)
    http_proxy = property(_get_http_proxy, _set_http_proxy)

    def _get_https_proxy(self):
        return self._iface.get_https_proxy()
    def _set_https_proxy(self, value):
        self._iface.set_https_proxy(value)
    https_proxy = property(_get_https_proxy, _set_https_proxy)
    
    def _get_ping_url(self):
        return self._iface.get_ping_url()
    def _set_ping_url(self, value):
        self._iface.set_ping_url(value)
    ping_url = property(_get_ping_url, _set_ping_url)

    def _get_registration_password(self):
        return self._iface.get_registration_password()
    def _set_registration_password(self, value):
        self._iface.set_registration_password(value)
    registration_password = property(_get_registration_password,
                                     _set_registration_password)
    
    def _get_tags(self):
        return self._iface.get_tags()
    def _set_tags(self, value):
        self._iface.set_tags(value)
    tags = property(_get_tags, _set_tags)

    def _get_url(self):
        return self._iface.get_url()
    def _set_url(self, value):
        self._iface.set_url(value)
    url = property(_get_url, _set_url)




    # def get_account_name(self):
    #     self._iface.get_account_name()
    # def set_account_name(self, value):
    #     self._iface.set_account_name
            
        
