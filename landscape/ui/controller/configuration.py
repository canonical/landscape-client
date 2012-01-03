import threading


class ConfigControllerLockError(Exception):
    pass


class ConfigController(object):
    """
    L{ConfigContoller} defines actions to take against a configfuration object,
    providing starting values from the file, allowing them to be changed
    transiently, reverted or committed.
    """

    HOSTED_HOST_NAME = "landscape.canonical.com"
    DEFAULT_SERVER_HOST_NAME = "landscape.localdomain"

    def __init__(self, configuration):
        self.__lock_out = True
        self.__lock = threading.Lock()
        self.__initial_server_host_name = self.DEFAULT_SERVER_HOST_NAME
        self.__configuration = configuration
        self.__configuration
        self.__configuration.load([])
        self.__load_data_from_config()
        self.__modified = False
        self.unlock()

    def default_dedicated(self):
        """
        Set L{server_host_name} to something sane when switching from hosted to
        dedicated
        """
        if self.__initial_server_host_name != self.HOSTED_HOST_NAME:
            self.__server_host_name = self.__initial_server_host_name
        else:
            self.__server_host_name = self.DEFAULT_SERVER_HOST_NAME
            self.__url = self.__derive_url_from_host_name(
                self.__server_host_name)
            self.__ping_url = self.__derive_ping_url_from_host_name(
                self.__server_host_name)
        self.__modified = True

    def default_hosted(self):
        """
        Set L{server_host_name} in a recoverable fashion when switching from
        dedicated to hosted.
        """
        if self.__server_host_name != self.HOSTED_HOST_NAME:
            self.__server_host_name = self.HOSTED_HOST_NAME
        self.__url = self.__derive_url_from_host_name(
            self.__server_host_name)
        self.__ping_url = self.__derive_ping_url_from_host_name(
            self.__server_host_name)
        self.__modified = True

    def __load_data_from_config(self):
        """
        Pull in data set from configuration class.
        """
        with self.__lock:
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
            if self.__url:
                self.__server_host_name = \
                    self.__derive_server_host_name_from_url(self.__url)
            else:
                self.__server_host_name = self.HOSTED_HOST_NAME
            self.__initial_server_host_name = self.__server_host_name
            self.__modified = False

    def lock(self):
        "Block updates to the data set"
        with self.__lock:
            self.__lock_out = True

    def unlock(self):
        "Allow updates to the data set"
        with self.__lock:
            self.__lock_out = False

    def is_locked(self):
        "Check if updates are locked out"
        with self.__lock:
            return self.__lock_out

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
        with self.__lock:
            if self.__lock_out:
                raise ConfigControllerLockError
            else:
                if value != self.HOSTED_HOST_NAME:
                    self.__initial_server_host_name = value
                self.__server_host_name = value
                self.__url = self.__derive_url_from_host_name(
                    self.__server_host_name)
                self.__ping_url = self.__derive_ping_url_from_host_name(
                    self.__server_host_name)
                self.__modified = True

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

    @account_name.setter
    def account_name(self, value):
        with self.__lock:
            if self.__lock_out:
                raise ConfigControllerLockError
            else:
                self.__account_name = value
                self.__modified = True

    @property
    def registration_password(self):
        return self.__registration_password

    @registration_password.setter
    def registration_password(self, value):
        with self.__lock:
            if self.__lock_out:
                raise ConfigControllerLockError
            else:
                self.__registration_password = value
                self.__modified = True

    @property
    def computer_title(self):
        return self.__computer_title

    @property
    def https_proxy(self):
        return self.__https_proxy

    @property
    def ping_url(self):
        return self.__ping_url

    @property
    def hosted(self):
        return self.server_host_name == self.HOSTED_HOST_NAME

    @property
    def is_modified(self):
        return self.__modified

    def revert(self):
        "Revert settings to those the configuration object originally found."
        self.__configuration.reload()
        self.__load_data_from_config()

    def commit(self):
        "Persist settings via the configuration object"
        self.__configuration.data_path = self.__data_path
        self.__configuration.http_proxy = self.__http_proxy
        self.__configuration.tags = self.__tags
        self.__configuration.url = self.__url
        self.__configuration.ping_url = self.__ping_url
        self.__configuration.account_name = self.__account_name
        self.__configuration.registration_password = \
            self.__registration_password
        self.__configuration.computer_title = self.__computer_title
        self.__configuration.https_proxy = self.__https_proxy
        self.__configuration.ping_url = self.__ping_url
        self.__configuration.write()
        self.__modified = False
