import threading


class ConfigControllerLockError(Exception):
    pass


class ConfigController(object):
    """
    L{ConfigContoller} defines actions to take against a configuration object,
    providing starting values from the file, allowing them to be changed
    transiently, reverted or committed.
    """

    HOSTED_HOST_NAME = "landscape.canonical.com"
    DEFAULT_SERVER_HOST_NAME = "landscape.localdomain"
    DEFAULT_DEDICATED_ACCOUNT_NAME = "standalone"

    def __init__(self, configuration):
        self._lock_out = True
        self._lock = threading.Lock()
        self._initial_server_host_name = self.DEFAULT_SERVER_HOST_NAME
        self._initial_account_name = self.DEFAULT_DEDICATED_ACCOUNT_NAME
        self._configuration = configuration
        self._configuration
        self._configuration.load([])
        self._load_data_from_config()
        self._modified = False
        self.unlock()

    def default_dedicated(self):
        """
        Set L{server_host_name} to something sane when switching from hosted to
        dedicated
        """
        self._account_name = self.DEFAULT_DEDICATED_ACCOUNT_NAME
        if self._initial_server_host_name != self.HOSTED_HOST_NAME:
            self._server_host_name = self._initial_server_host_name
        else:
            self._server_host_name = self.DEFAULT_SERVER_HOST_NAME
            self._url = self._derive_url_from_host_name(
                self._server_host_name)
            self._ping_url = self._derive_ping_url_from_host_name(
                self._server_host_name)
            
        self._modified = True

    def default_hosted(self):
        """
        Set L{server_host_name} in a recoverable fashion when switching from 
        dedicated to hosted.
        """
        if self._server_host_name != self.HOSTED_HOST_NAME:
            self._server_host_name = self.HOSTED_HOST_NAME
        self._url = self._derive_url_from_host_name(
            self._server_host_name)
        self._ping_url = self._derive_ping_url_from_host_name(
            self._server_host_name)
        self._account_name = self._initial_account_name
        self._modified = True

    def _load_data_from_config(self):
        """
        Pull in data set from configuration class.
        """
        with self._lock:
            self._data_path = self._configuration.data_path
            self._http_proxy = self._configuration.http_proxy
            self._tags = self._configuration.tags
            self._url = self._configuration.url
            self._ping_url = self._configuration.ping_url
            self._account_name = self._configuration.account_name
            self._initial_account_name = self._account_name
            self._registration_password = \
                self._configuration.registration_password
            self._computer_title = self._configuration.computer_title
            self._https_proxy = self._configuration.https_proxy
            self._ping_url = self._configuration.ping_url
            if self._url:
                self._server_host_name = \
                    self._derive_server_host_name_from_url(self._url)
            else:
                self._server_host_name = self.HOSTED_HOST_NAME
            self._initial_server_host_name = self._server_host_name
            self._modified = False

    def lock(self):
        "Block updates to the data set"
        with self._lock:
            self._lock_out = True

    def unlock(self):
        "Allow updates to the data set"
        with self._lock:
            self._lock_out = False

    def is_locked(self):
        "Check if updates are locked out"
        with self._lock:
            return self._lock_out

    def _derive_server_host_name_from_url(self, url):
        "Extract the hostname part from a url"
        try:
            without_protocol = url[url.index("://") + 3:]
        except ValueError:
            without_protocol = url
        try:
            return without_protocol[:without_protocol.index("/")]
        except ValueError:
            return without_protocol

    def _derive_url_from_host_name(self, host_name):
        "Extrapolate a url from a host name"
        #Reuse this code to make sure it's a proper host name
        host_name = self._derive_server_host_name_from_url(host_name)
        return "https://" + host_name + "/message-system"

    def _derive_ping_url_from_host_name(self, host_name):
        "Extrapolate a ping_url from a host name"
        #Reuse this code to make sure it's a proper host name
        host_name = self._derive_server_host_name_from_url(host_name)
        return "http://" + host_name + "/ping"

    @property
    def server_host_name(self):
        return self._server_host_name

    @server_host_name.setter
    def server_host_name(self, value):
        with self._lock:
            if self._lock_out:
                raise ConfigControllerLockError
            else:
                if value != self.HOSTED_HOST_NAME:
                    self._initial_server_host_name = value
                self._server_host_name = value
                self._url = self._derive_url_from_host_name(
                    self._server_host_name)
                self._ping_url = self._derive_ping_url_from_host_name(
                    self._server_host_name)
                self._modified = True

    @property
    def data_path(self):
        return self._data_path

    @property
    def url(self):
        return self._url

    @property
    def http_proxy(self):
        return self._http_proxy

    @property
    def tags(self):
        return self._tags

    @property
    def account_name(self):
        return self._account_name

    @account_name.setter
    def account_name(self, value):
        with self._lock:
            if self._lock_out:
                raise ConfigControllerLockError
            else:
                self._account_name = value
                self._initial_account_name = value
                self._modified = True

    @property
    def registration_password(self):
        return self._registration_password

    @registration_password.setter
    def registration_password(self, value):
        with self._lock:
            if self._lock_out:
                raise ConfigControllerLockError
            else:
                self._registration_password = value
                self._modified = True

    @property
    def computer_title(self):
        return self._computer_title

    @property
    def https_proxy(self):
        return self._https_proxy

    @property
    def ping_url(self):
        return self._ping_url

    @property
    def hosted(self):
        return self.server_host_name == self.HOSTED_HOST_NAME

    @property
    def is_modified(self):
        return self._modified

    def revert(self):
        "Revert settings to those the configuration object originally found."
        self._configuration.reload()
        self._load_data_from_config()

    def commit(self):
        "Persist settings via the configuration object"
        self._configuration.data_path = self._data_path
        self._configuration.http_proxy = self._http_proxy
        self._configuration.tags = self._tags
        self._configuration.url = self._url
        self._configuration.ping_url = self._ping_url
        self._configuration.account_name = self._account_name
        self._configuration.registration_password = \
            self._registration_password
        self._configuration.computer_title = self._computer_title
        self._configuration.https_proxy = self._https_proxy
        self._configuration.ping_url = self._ping_url
        self._configuration.write()
        self._modified = False
