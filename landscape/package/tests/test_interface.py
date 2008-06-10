# -*- encoding: utf-8 -*-
from landscape.package.interface import LandscapeInterface

from landscape.tests.helpers import LandscapeTest
from landscape.package.tests.helpers import SmartFacadeHelper


class LandscapeInterfaceTest(LandscapeTest):

    helpers = [SmartFacadeHelper]

    def setUp(self):
        super(LandscapeInterfaceTest, self).setUp()
        self.facade.reload_channels()
        self.iface = LandscapeInterface(None)

    def test_message_with_unicode_and_utf8(self):
        self.iface.info(u"áéíóú")
        self.iface.info("áéíóú")
        self.assertEquals(self.iface.get_output_for_landscape(),
                          u"INFO: áéíóú\nINFO: áéíóú\n")

    def test_message_with_unicode_and_unknown_encoding(self):
        self.iface.info(u"áéíóú")
        self.iface.info("aeíou\xc3") # UTF-8 expects a byte after \xc3
        c = u"\N{REPLACEMENT CHARACTER}"
        self.assertEquals(self.iface.get_output_for_landscape(),
                          u"INFO: áéíóú\nINFO: ae%s%sou%s\n" % (c, c, c))

    def test_output_with_unicode_and_utf8(self):
        self.iface.showOutput(u"áéíóú")
        self.iface.showOutput("áéíóú")
        self.assertEquals(self.iface.get_output_for_landscape(),
                          u"áéíóúáéíóú")
