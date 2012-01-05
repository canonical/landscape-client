import sys

try:
    from gi.repository import Gtk
    got_gobject_introspection = True
except ImportError:
    got_gobject_introspection = False
    gobject_skip_message = "GObject Introspection module unavailable"


from landscape.tests.helpers import LandscapeTest
from landscape.ui.controller.app import LandscapeSettingsApplicationController
from landscape.ui.controller.configuration import ConfigController
from landscape.ui.view.configuration import LandscapeClientSettingsDialog
from landscape.ui.model.configuration import LandscapeSettingsConfiguration


class ConnectionRecordingLandscapeSettingsApplicationController(
    LandscapeSettingsApplicationController):

    _connections = set()
    _connection_args = {}
    _connection_kwargs = {}

    def __init__(self, get_config_f=None):
        super(ConnectionRecordingLandscapeSettingsApplicationController,
              self).__init__()
        if get_config_f:
            self.get_config = get_config_f

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


class LandscapeSettingsApplicationControllerInitTest(LandscapeTest):

    def setUp(self):
        super(LandscapeSettingsApplicationControllerInitTest, self).setUp()

    def test_init(self):
        """
        Test we connect activate to something useful on application
        initialisation.
        """
        app = ConnectionRecordingLandscapeSettingsApplicationController()
        self.assertTrue(app.is_connected("activate", app.setup_ui))

    if not got_gobject_introspection:
        test_init.skip = gobject_skip_message


class LandscapeSettingsApplicationControllerUISetupTest(LandscapeTest):

    def setUp(self):
        super(LandscapeSettingsApplicationControllerUISetupTest, self).setUp()

        def fake_run(obj):
            """
            Retard X11 mapping.
            """
            pass
        self._real_run = Gtk.Dialog.run
        Gtk.Dialog.run = fake_run

        def get_config():
            configdata = "[client]\n"
            configdata += "data_path = %s\n" % sys.path[0]
            configdata += "http_proxy = http://proxy.localdomain:3192\n"
            configdata += "tags = a_tag\n"
            configdata += \
                "url = https://landscape.canonical.com/message-system\n"
            configdata += "account_name = foo\n"
            configdata += "registration_password = bar\n"
            configdata += "computer_title = baz\n"
            configdata += "https_proxy = https://proxy.localdomain:6192\n"
            configdata += "ping_url = http://landscape.canonical.com/ping\n"
            config_filename = self.makeFile(configdata)

            class MyLandscapeSettingsConfiguration(
                LandscapeSettingsConfiguration):
                default_config_filenames = [config_filename]

            config = MyLandscapeSettingsConfiguration()
            return config

        self.app = ConnectionRecordingLandscapeSettingsApplicationController(
            get_config_f=get_config)

    def tearDown(self):
        Gtk.Dialog.run = self._real_run
        super(
            LandscapeSettingsApplicationControllerUISetupTest, self).tearDown()

    def test_setup_ui(self):
        """
        Test that we correctly setup the L{LandscapeClientSettingsDialog} with
        the config object and correct data
        """
        self.app.setup_ui(data=None)
        self.assertIsInstance(self.app.settings_dialog,
                              LandscapeClientSettingsDialog)
        self.assertIsInstance(self.app.settings_dialog.controller,
                              ConfigController)

    if not got_gobject_introspection:
        test_setup_ui.skip = gobject_skip_message
