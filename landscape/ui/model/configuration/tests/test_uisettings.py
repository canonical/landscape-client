import os

from gi.repository import Gio
from lxml import etree

from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.configuration.uisettings import ObservableUISettings



class FakeGSettings(object):

    calls = {}

    def __init__(self, data={}):
        self.set_data(data)
        tree = etree.parse(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "../../../../../", 
                "glib-2.0/schemas/",
                "com.canonical.landscape-client-settings.gschema.xml"))
        root = tree.getroot()
        self.schema = root.find("schema")
        assert(self.schema.attrib["id"] == \
                   "com.canonical.landscape-client-settings")
        self.keys = {}
        for key in self.schema.findall("key"):
            self.keys[key.attrib["name"]] = key.attrib["type"]
        

    def get_value(self, name, gstype):
        if self.keys.has_key(name):
            if self.keys[name] == gstype:
                return self.data[name]
            else:
                raise ValueError, "The GSchema file says %s is a %s, " + \
                    "but you asked for a %s" % (name, self.keys[name], gstype)
        else:
            raise KeyError, "Can't find %s in the GSchema file!" % name

    def set_data(self, data):
        self.data = data
        
    def _call(self, name, *args):
        [count, arglist] = self.calls.get(name, (0, []))
        count += 1
        arglist.append(self._args_to_string(*args))
        self.calls[name] = [count, arglist]

    def _args_to_string(self, *args):
        return "|".join([str(arg) for arg in args])
        
    def new(self, key):
        self._call("new", key)
        return self

    def connect(self, signal, callback, *args):
        self._call("connect", signal, callback, *args)

    def get_boolean(self, name):
        self._call("get_boolean", name)
        return self.get_value(name, "b")

    def get_string(self, name):
        self._call("get_string", name)
        return self.get_value(name, "s")
    
    def was_called(self, name):
        return self.calls.haskey(name)

    def was_called_with_args(self, name, *args):
        try:
            [count, arglist] = self.calls.get(name, (0,[]))
        except KeyError:
            return False
        
        expected_args = self._args_to_string(*args)
        return expected_args in arglist
        

class ObservableUISettingsTest(LandscapeTest):
    
    def test_load_data_from_ui_settings(self):
        settings = FakeGSettings(data={"is-hosted": True,
                                       "hosted-landscape-host":
                                           "landscape.canonical.com"})
        uisettings = ObservableUISettings(settings)
        self.assertTrue(settings.was_called_with_args(
                "new", ObservableUISettings.BASE_KEY))
        self.assertTrue(settings.was_called_with_args(
                "connect",
                "changed::is-hosted", uisettings._on_is_hosted_changed))
        self.assertTrue(settings.was_called_with_args(
                "connect",
                "changed::hosted-landscape-host",
                uisettings._on_hosted_landscape_host_changed))
        self.assertTrue(uisettings.get_is_hosted())
        self.assertEqual("landscape.canonical.com", 
                         uisettings.get_hosted_landscape_host())
        
