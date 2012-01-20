import dbus
import dbus.service

from landscape.ui.lib.polkit import PolicyKitMechanism


SERVICE_NAME = "com.canonical.LandscapeClientSettings"
POLICY_NAME = SERVICE_NAME + ".configure"
INTERFACE_NAME = "com.canonical.LandscapeClientSettings.ConfigurationInterface"
OBJECT_PATH = "/com/canonical/LandscapeClientSettings/ConfigurationInterface"


class PermissionDeniedByPolicy(dbus.DBusException):
    _dbus_error_name = \
        "com.canonical.LandscapeClientSettings.PermissionDeniedByPolicy"


class ConfigurationMechanism(PolicyKitMechanism):
    """
    L{ConfigurationMechanism} provides access to the
    L{LandscapeSetupConfiguration} object via DBus with access control
    implemented via PolicyKit policy.  The use of DBus results from the use of
    PolicyKit, not the other way around, and is done that way because that is
    considered to be the Right Thing for Ubuntu Desktop circa January 2012.
    """

    def __init__(self, config, bus_name, bypass=False, conn=None):
        super(ConfigurationMechanism, self).__init__(
            OBJECT_PATH, bus_name, PermissionDeniedByPolicy,
            bypass=bypass, conn=conn)
        self.config = config

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="as",
                         out_signature="",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def load(self, arglist, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            if len(arglist) > 0:
                self.config.load(arglist.split(chr(0x1e)))
            else:
                self.config.load([])
        return

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def reload(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.reload()

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def write(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.write()

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def get_config_filename(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            return self.config.get_config_filename()

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender", connection_keyword="conn")
    def get_account_name(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            try:
                return self.config.account_name
            except AttributeError:
                return ""

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def set_account_name(self, account_name, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.account_name = account_name

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender", connection_keyword="conn")
    def get_computer_title(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            try:
                return self.config.computer_title
            except AttributeError:
                return ""

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def set_computer_title(self, computer_title, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.computer_title = computer_title

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender", connection_keyword="conn")
    def get_data_path(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            try:
                return str(self.config.data_path)
            except AttributeError:
                return ""

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def set_data_path(self, data_path, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.data_path = data_path

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender", connection_keyword="conn")
    def get_http_proxy(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            try:
                return self.config.http_proxy
            except AttributeError:
                return ""

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def set_http_proxy(self, http_proxy, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.http_proxy = http_proxy

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender", connection_keyword="conn")
    def get_ping_url(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            try:
                return self.config.ping_url
            except AttributeError:
                return ""

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def set_ping_url(self, ping_url, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.ping_url = ping_url

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender", connection_keyword="conn")
    def get_registration_password(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            try:
                return self.config.registration_password
            except AttributeError:
                return ""

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s",
                         out_signature="",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def set_registration_password(self, registration_password, sender=None,
                                  conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.registration_password = registration_password

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender", connection_keyword="conn")
    def get_tags(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            try:
                return self.config.tags
            except AttributeError:
                return ""

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def set_tags(self, tags, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.tags = tags

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender", connection_keyword="conn")
    def get_url(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            try:
                return self.config.url
            except AttributeError:
                return ""

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def set_url(self, url, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.url = url

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender", connection_keyword="conn")
    def get_https_proxy(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            try:
                return self.config.https_proxy
            except AttributeError:
                return ""

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def set_https_proxy(self, https_proxy, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self.config.https_proxy = https_proxy
