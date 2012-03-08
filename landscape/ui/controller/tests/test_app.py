import sys

from landscape.ui.tests.helpers import (
    ConfigurationProxyHelper, dbus_test_should_skip, dbus_skip_message,
    got_gobject_introspection, gobject_skip_message, FakeGSettings)

if got_gobject_introspection:
    from gi.repository import Gtk
    from landscape.ui.controller.app import SettingsApplicationController
    from landscape.ui.controller.configuration import ConfigController
    from landscape.ui.view.configuration import ClientSettingsDialog
    from landscape.ui.model.configuration.uisettings import UISettings
else:
    SettingsApplicationController = object

from landscape.tests.helpers import LandscapeTest


class ConnectionRecordingSettingsApplicationController(
    SettingsApplicationController):
    _connections = set()
    _connection_args = {}
    _connection_kwargs = {}

    def __init__(self, get_config=None, get_uisettings=None):
        super(ConnectionRecordingSettingsApplicationController,
              self).__init__()
        if get_config:
            self.get_config = get_config
        if get_uisettings:
            self.get_uisettings = get_uisettings

    def _make_connection_name(self, signal, func):
        return signal + ">" + func.__name__

    def _record_connection(self, signal, func, *args, **kwargs):
        connection_name = self._make_connection_name(signal, func)
        self._connections.add(connection_name)
        signal_connection_args = self._connection_args.get(
            connection_name, [])
        signal_connection_args.append(repr(args))
        self._connection_args = signal_connection_args
        signal_connection_kwargs = self._connection_kwargs.get(
            connection_name, [])
        signal_connection_kwargs.append(repr(kwargs))
        self._connection_kwargs = signal_connection_kwargs

    def is_connected(self, signal, func):
        connection_name = self._make_connection_name(signal, func)
        return self._connections.issuperset(set([connection_name]))

    def connect(self, signal, func, *args, **kwargs):
        self._record_connection(signal, func)


class SettingsApplicationControllerInitTest(LandscapeTest):

    def setUp(self):
        super(SettingsApplicationControllerInitTest, self).setUp()

    def test_init(self):
        """
        Test we connect activate to something useful on application
        initialisation.
        """
        app = ConnectionRecordingSettingsApplicationController()
        self.assertTrue(app.is_connected("activate", app.setup_ui))

    if not got_gobject_introspection:
        skip = gobject_skip_message


class SettingsApplicationControllerUISetupTest(LandscapeTest):

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.config_string = "\n".join(
            ["[client]",
             "data_path = %s" % sys.path[0],
             "http_proxy = http://proxy.localdomain:3192",
             "tags = a_tag",
             "url = https://landscape.canonical.com/message-system",
             "account_name = foo",
             "registration_password = bar",
             "computer_title = baz",
             "https_proxy = https://proxy.localdomain:6192",
             "ping_url = http://landscape.canonical.com/ping"])
        self.default_data = {"management-type": "not",
                             "computer-title": "",
                             "hosted-landscape-host": "",
                             "hosted-account-name": "",
                             "hosted-password": "",
                             "local-landscape-host": "",
                             "local-account-name": "",
                             "local-password": ""}
        super(SettingsApplicationControllerUISetupTest, self).setUp()

        def fake_run(obj):
            """
            Retard X11 mapping.
            """
            pass

        self._real_run = Gtk.Dialog.run
        Gtk.Dialog.run = fake_run

        def get_config():
            return self.proxy

        def get_uisettings():
            settings = FakeGSettings(data=self.default_data)
            return UISettings(settings)

        self.app = ConnectionRecordingSettingsApplicationController(
            get_config=get_config, get_uisettings=get_uisettings)

    def tearDown(self):
        Gtk.Dialog.run = self._real_run
        super(
            SettingsApplicationControllerUISetupTest, self).tearDown()

    def test_setup_ui(self):
        """
        Test that we correctly setup the L{ClientSettingsDialog} with
        the config object and correct data
        """
        self.app.setup_ui(data=None, asynchronous=False)
        self.assertIsInstance(self.app.settings_dialog, ClientSettingsDialog)
        self.assertIsInstance(self.app.settings_dialog.controller,
                              ConfigController)

    if not got_gobject_introspection:
        skip = gobject_skip_message
    elif dbus_test_should_skip:
        skip = dbus_skip_message
