import socket
import threading

from landscape.ui.model.registration import ObservableRegistration


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

    def __init__(self, configuration, args=[]):
        self._observers = []
        self._initial_server_host_name = self.DEFAULT_SERVER_HOST_NAME
        self._initial_account_name = self.DEFAULT_DEDICATED_ACCOUNT_NAME
        self._configuration = configuration
        self._args = args
        self._lock_out = False
        self._lock = threading.Lock()

    def register_observer(self, fun):
        self._observers.append(fun)

    def notify_observers(self, modified):
        for fun in self._observers:
            fun(modified)

    def modify(self):
        self._modified = True
        self.notify_observers(True)

    def unmodify(self):
        self._modified = False
        self.notify_observers(False)

    def load(self):
        "Load the initial data from the configuration"
        self.lock()
        self._configuration.load(self._args)
        self._pull_data_from_config()
        self.default_machine()
        self.unmodify()
        self.unlock()

    def default_machine(self):
        """
        Default machine name to FQDN.
        """
        if self._computer_title is None:
            self._computer_title = socket.getfqdn()

    def default_dedicated(self):
        """
        Set L{server_host_name} to something sane when switching from hosted to
        dedicated.
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
        self.modify()

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
        self.modify()

    def _pull_data_from_config(self):
        """
        Pull in data set from configuration class.
        """
        self._lock.acquire()
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
        self.unmodify()
        self._lock.release()

    def lock(self):
        "Block updates to the data set."
        self._lock.acquire()
        self._lock_out = True
        self._lock.release()

    def unlock(self):
        "Allow updates to the data set."
        self._lock.acquire()
        self._lock_out = False
        self._lock.release()

    def is_locked(self):
        "Check if updates are locked out."
        self._lock.acquire()
        lock_state = self._lock_out
        self._lock.release()
        return lock_state

    def _derive_server_host_name_from_url(self, url):
        "Extract the hostname part from a URL."
        try:
            without_protocol = url[url.index("://") + 3:]
        except ValueError:
            without_protocol = url
        try:
            return without_protocol[:without_protocol.index("/")]
        except ValueError:
            return without_protocol

    def _derive_url_from_host_name(self, host_name):
        "Extrapolate a url from a host name."
        #Reuse this code to make sure it's a proper host name
        host_name = self._derive_server_host_name_from_url(host_name)
        return "https://" + host_name + "/message-system"

    def _derive_ping_url_from_host_name(self, host_name):
        "Extrapolate a ping_url from a host name."
        #Reuse this code to make sure it's a proper host name
        host_name = self._derive_server_host_name_from_url(host_name)
        return "http://" + host_name + "/ping"

    def _get_server_host_name(self):
        return self._server_host_name

    def _set_server_host_name(self, value):
        self._lock.acquire()
        if self._lock_out:
            self._lock.release()
            raise ConfigControllerLockError
        else:
            if value != self.HOSTED_HOST_NAME:
                self._initial_server_host_name = value
            self._server_host_name = value
            self._url = self._derive_url_from_host_name(
                self._server_host_name)
            self._ping_url = self._derive_ping_url_from_host_name(
                self._server_host_name)
            self.modify()
            self._lock.release()
    server_host_name = property(_get_server_host_name, _set_server_host_name)

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

    def _get_account_name(self):
        return self._account_name

    def _set_account_name(self, value):
        self._lock.acquire()
        if self._lock_out:
            self._lock.release()
            raise ConfigControllerLockError
        else:
            self._account_name = value
            self.modify()
            self._lock.release()
    account_name = property(_get_account_name, _set_account_name)

    def _get_registration_password(self):
        return self._registration_password

    def _set_registration_password(self, value):
        self._lock.acquire()
        if self._lock_out:
            self._lock.release()
            raise ConfigControllerLockError
        else:
            self._registration_password = value
            self.modify()
            self._lock.release()
    registration_password = property(_get_registration_password,
                                     _set_registration_password)

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
        self._pull_data_from_config()

    def commit(self):
        "Persist settings via the configuration object."
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
        self.unmodify()

    def register(self, notify_f, error_f, success_f, failure_f, idle_f):
        idle_f()
        registration = ObservableRegistration(idle_f)
        idle_f()
        self.commit()
        idle_f()
        registration.register_notification_observer(notify_f)
        idle_f()
        registration.register_error_observer(error_f)
        idle_f()
        registration.register_succeed_observer(success_f)
        idle_f()
        registration.register_fail_observer(failure_f)
        idle_f()
        registration.register(self._configuration)
