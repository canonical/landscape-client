from twisted.internet.defer import succeed

from landscape.lib.sysstats import get_thermal_zones


class Temperature(object):

    def __init__(self, thermal_zone_path=None):
        self._thermal_zone_path = thermal_zone_path

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        temperature = None
        max_value = None
        for zone in get_thermal_zones(self._thermal_zone_path):
            if (zone.temperature_value is not None and
                (max_value is None or zone.temperature_value > max_value)
                ):

                temperature = zone.temperature
                max_value = zone.temperature_value
        if temperature is not None:
            self._sysinfo.add_header("Temperature", temperature)
        return succeed(None)
