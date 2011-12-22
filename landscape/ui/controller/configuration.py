from landscape.configuration import (
    LandscapeSetupConfiguration, fetch_import_url)
 
 
class ConfigController(object):

    def __init__(self, configuration):
        self.__configuration = configuration
        self.__configuration.load([])
        self.__load_data_from_config()

    def __load_data_from_config(self):
        self.__data_path = self.__configuration.data_path
        self.__http_proxy = self.__configuration.http_proxy
        self.__tags = self.__configuration.tags
        self.__url = self.__configuration.url
        self.__ping_url = self.__configuration.ping_url
        self.__account_name = self.__configuration.account_name
        self.__registration_password = \
            self.__configuration.registration_password
        self.__computer_title = self.__configuration.computer_title
        self.__https_proxy = self.__configuration.https_proxy
        self.__ping_url = self.__configuration.ping_url
        
    @property 
    def data_path(self):
        return self.__data_path

    @property
    def url(self):
        return self.__url

    @property
    def http_proxy(self):
        return self.__http_proxy
    
    @property
    def tags(self):
        return self.__tags

    @property
    def account_name(self):
        return self.__account_name

    @property
    def registration_password(self):
        return self.__registration_password

    @property
    def computer_title(self):
        return self.__computer_title

    @property
    def https_proxy(self):
        return self.__https_proxy

    @property
    def ping_url(self):
        return self.__ping_url
