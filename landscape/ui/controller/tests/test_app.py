from landscape.tests.helpers import LandscapeTest
from landscape.ui.controller.app import LandscapeSettingsApplicationController
from landscape.ui.controller.configuration import ConfigController
from landscape.ui.view.configuration import LandscapeClientSettingsDialog
from landscape.configuration import LandscapeSetupConfiguration


class ConnectionRecordingLandscapeSettingsApplicationController(
    LandscapeSettingsApplicationController):

    __connections = set()
    __connection_args = {}
    __connection_kwargs = {}

    def __init__(self, get_config_f=None):
        super(ConnectionRecordingLandscapeSettingsApplicationController,
              self).__init__()
        if get_config_f:
            self.get_config = get_config_f

    def __make_connection_name(self, signal, func):
        return signal + ">" + func.__name__

    def __record_connection(self, signal, func, *args, **kwargs):
        connection_name = self.__make_connection_name(signal, func)
        self.__connections.add(connection_name)
        signal_connection_args = self.__connection_args.get(
            connection_name, [])
        signal_connection_args.append(repr(args))
        self.__connection_args = signal_connection_args
        signal_connection_kwargs = self.__connection_kwargs.get(
            connection_name, [])
        signal_connection_kwargs.append(repr(kwargs))
        self.__connection_kwargs = signal_connection_kwargs
        
    def is_connected(self, signal, func):
        connection_name = self.__make_connection_name(signal, func)
        return self.__connections.issuperset(set([connection_name]))
        
    def connect(self, signal, func, *args, **kwargs):
        self.__record_connection(signal, func)
        
        

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


class LandscapeSettingsApplicationControllerUISetupTest(LandscapeTest):


    def setUp(self):
        super(LandscapeSettingsApplicationControllerUISetupTest, self).setUp()
        def get_config():
            configdata = """
[client]
data_path = /var/lib/landscape/client
http_proxy = http://proxy.localdomain:3192
tags = a_tag
url = https://landscape.canonical.com/message-system
account_name = foo
registration_password = bar
computer_title = baz
https_proxy = https://proxy.localdomain:6192
ping_url = http://landscape.canonical.com/ping

"""
            config_filename = self.makeFile(configdata)
            class MyLandscapeSetupConfiguration(LandscapeSetupConfiguration):
                default_config_filenames = [config_filename]
            config = MyLandscapeSetupConfiguration(None)
            return config
        self.app = ConnectionRecordingLandscapeSettingsApplicationController(
            get_config_f=get_config)
        
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
        
        


        
