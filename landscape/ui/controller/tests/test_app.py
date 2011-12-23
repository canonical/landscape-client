from landscape.tests.helpers import LandscapeTest
from landscape.ui.controller.app import LandscapeSettingsApplicationController


class ConnectionRecordingLandscapeSettingsApplicationController(
    LandscapeSettingsApplicationController):

    __connections = set()
    __connection_args = {}
    __connection_kwargs = {}

    def init(self, passthrough_connect=False):
        super(ConnectionRecordingLandscapeSettingsApplicationController,
              self).__init__()

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
        super(LandscapeSettingsApplicationControllerTest, self).setUp()

    def test_init(self):
        """
        Test we connect activate to something useful on application
        initialisation.
        """
        app = ConnectionRecordingLandscapeSettingsApplicationController()
        self.assertTrue(app.is_connected("activate", app.setup_ui))


        

        
        



        
