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
        self.__server_host_name = self.__derive_server_host_name_from_url(
            self.__url)

    def __derive_server_host_name_from_url(self, url):
        "Extract the hostname part from a url"
        try:
            without_protocol = url[url.index("://") + 3:]
        except ValueError:
            without_protocol = url
        try:
            return without_protocol[:without_protocol.index("/")]
        except ValueError:
            return without_protocol

    # def is_valid_host_name(self, host_name):
    #     valid_section = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    #     def is_valid_host_name_section(host_name_section):
    #         return valid_section.match(host_name_section)

    #     return (len(host_name) > 255 && 
    #             all(is_valid_host_name_section(section)
    #                 for section in host_name.split(".")))


    def __derive_url_from_host_name(self, host_name):
        "Extrapolate a url from a host name"
        #Reuse this code to make sure it's a proper host name
        host_name = self.__derive_server_host_name_from_url(host_name)
        return "https://" + host_name + "/message-system"

    def __derive_ping_url_from_host_name(self, host_name):
        "Extrapolate a ping_url from a host name"
        #Reuse this code to make sure it's a proper host name
        host_name = self.__derive_server_host_name_from_url(host_name)
        return "http://" + host_name + "/ping"

    @property
    def server_host_name(self):
        return self.__server_host_name

    @server_host_name.setter
    def server_host_name(self, value):
        self.__server_host_name = value
        self.__url = self.__derive_url_from_host_name(self.__server_host_name)
        self.__ping_url = self.__derive_ping_url_from_host_name(
            self.__server_host_name)
        
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
