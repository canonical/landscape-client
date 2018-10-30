import logging
import os
import re

from landscape.lib.plugin import PluginConfigError
from landscape.client.monitor.plugin import MonitorPlugin


class ProcessorInfo(MonitorPlugin):
    """Plugin captures information about the processor(s) in this machine.

    This plugin runs once per client session.  When processor
    information is retrieved it's compared against the last known
    processor information, which is saved in persistent storage.  A
    message is only put on the message queue if the latest processor
    information differs from the last known processor information.

    The information available from /proc/cpuinfo varies per platform.
    For example, an Apple PowerMac Dual G5 doesn't contain a vendor ID
    and provides the processor name in the 'cpu' field, as opposed to
    the 'model name' field used on x86-based hardware.  For reasons
    such as this, the schema of the data reported by this plugin is
    flexible.  Only 'processor-id' and 'model' are guaranteed to be
    present.

    In order to deal with the vagaries of parsing /proc/cpu
    information on the various platforms we support, message
    generation is deferred to per-platform message factories.

    @param delay: Set the starting delay.
    @param machine_name: The machine name to report.
    @param source_filename: The filesystem path to read information from.
    """

    persist_name = "processor-info"
    scope = "cpu"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, delay=2, machine_name=None,
                 source_filename="/proc/cpuinfo"):
        self._delay = delay
        self._source_filename = source_filename

        if machine_name is None:
            machine_name = os.uname()[4]

        self._cpu_info_reader = self._create_cpu_info_reader(machine_name,
                                                             source_filename)

    def _create_cpu_info_reader(self, machine_name, source_filename):
        """Return a message factory suitable for the specified machine name."""
        for pair in message_factories:
            regexp = re.compile(pair[0])

            if regexp.match(machine_name):
                return pair[1](source_filename)

        raise PluginConfigError("A processor info reader for '%s' is not "
                                "available." % machine_name)

    def register(self, registry):
        """Register this plugin with the specified plugin registry."""
        super(ProcessorInfo, self).register(registry)
        self.registry.reactor.call_later(self._delay, self.run)
        self.call_on_accepted("processor-info", self.send_message, True)

    def create_message(self):
        """Retrieve processor information and generate a message."""
        return {"type": "processor-info",
                "processors": self._cpu_info_reader.create_message()}

    def send_message(self, urgent=False):
        dirty = False
        message = self.create_message()

        for processor in message["processors"]:
            key = ("processor", str(processor["processor-id"]))
            cached_processor = self._persist.get(key)
            if cached_processor is None:
                cached_processor = {}
                self._update(cached_processor, processor)
                dirty = True
            else:
                if self._has_changed(cached_processor, processor):
                    self._update(cached_processor, processor)
                    dirty = True

        if dirty:
            logging.info("Queueing message with updated processor info.")
            self.registry.broker.send_message(
                message, self._session_id, urgent=urgent)

    def run(self, urgent=False):
        """Create a message and put it on the message queue."""
        self.registry.broker.call_if_accepted("processor-info",
                                              self.send_message, urgent)

    def _has_changed(self, processor, message):
        """Returns true if processor details changed since the last read."""
        if processor["model"] != message["model"]:
            return True

        if processor["vendor"] != message.get("vendor", ""):
            return True

        if processor["cache_size"] != message.get("cache-size", -1):
            return True

        return False

    def _update(self, processor, message):
        """Update the processor details with current values."""
        processor["id"] = message["processor-id"]
        processor["model"] = message["model"]
        processor["cache_size"] = message.get("cache-size", -1)
        processor["vendor"] = message.get("vendor", "")
        self._persist.set(("processor", str(message["processor-id"])),
                          processor)


class PowerPCMessageFactory:
    """Factory for ppc-based processors provides processor information.

    @param source_filename: The file name of the data source.
    """

    def __init__(self, source_filename):
        self._source_filename = source_filename

    def create_message(self):
        """Returns a list containing information about each processor."""
        processors = []
        file = open(self._source_filename)

        try:
            current = None

            for line in file:
                parts = line.split(":", 1)
                key = parts[0].strip()

                if key == "processor":
                    current = {"processor-id": int(parts[1].strip())}
                    processors.append(current)
                elif key == "cpu":
                    current["model"] = parts[1].strip()
        finally:
            file.close()

        return processors


class ARMMessageFactory:
    """Factory for arm-based processors provides processor information.

    @param source_filename: The file name of the data source.
    """

    def __init__(self, source_filename):
        self._source_filename = source_filename

    def create_message(self):
        """Returns a list containing information about each processor."""
        processors = []
        file = open(self._source_filename)

        try:
            regexp = re.compile(r"(?P<key>.*?)\s*:\s*(?P<value>.*)")
            current = {}

            for line in file:
                match = regexp.match(line.strip())
                if match:
                    key = match.group("key")
                    value = match.group("value")

                    if key == "Processor":
                        # ARM doesn't support SMP, thus no processor-id in
                        # the cpuinfo
                        current["processor-id"] = 0
                        current["model"] = value
                    elif key == "Cache size":
                        current["cache-size"] = int(value)

            if current:
                processors.append(current)
        finally:
            file.close()

        return processors


class SparcMessageFactory:
    """Factory for sparc-based processors provides processor information.

    @param source_filename: The file name of the data source.
    """

    def __init__(self, source_filename):
        self._source_filename = source_filename

    def create_message(self):
        """Returns a list containing information about each processor."""
        processors = []
        model = None
        file = open(self._source_filename)

        try:
            regexp = re.compile(r"CPU(\d{1})+")

            for line in file:
                parts = line.split(":", 1)
                key = parts[0].strip()

                if key == "cpu":
                    model = parts[1].strip()
                elif regexp.match(key):
                    start, end = re.compile(r"\d+").search(key).span()
                    message = {"processor-id": int(key[start:end]),
                               "model": model}
                    processors.append(message)
        finally:
            file.close()

        return processors


class X86MessageFactory:
    """Factory for x86-based processors provides processor information.

    @param source_filename: The file name of the data source.
    """

    def __init__(self, source_filename):
        self._source_filename = source_filename

    def create_message(self):
        """Returns a list containing information about each processor."""
        processors = []
        file = open(self._source_filename)

        try:
            current = None

            for line in file:
                parts = line.split(":", 1)
                key = parts[0].strip()

                if key == "processor":
                    current = {"processor-id": int(parts[1].strip())}
                    processors.append(current)
                elif key == "vendor_id":
                    current["vendor"] = parts[1].strip()
                elif key == "model name":
                    current["model"] = parts[1].strip()
                elif key == "cache size":
                    value_parts = parts[1].split()
                    current["cache-size"] = int(value_parts[0].strip())
        finally:
            file.close()

        return processors


class S390XMessageFactory:
    """Factory for s390x-based processors provides processor information.

    @param source_filename: The file name of the data source.
    """

    def __init__(self, source_filename):
        self._source_filename = source_filename

    def create_message(self):
        """Returns a list containing information about each processor."""
        processors = []
        vendor = None
        cache_size = 0
        file = open(self._source_filename)

        try:
            current = None

            for line in file:
                parts = line.split(":", 1)
                key = parts[0].strip()

                if key == "vendor_id":
                    vendor = parts[1].strip()
                    continue

                if key.startswith("cache"):
                    for word in parts[1].split():
                        if word.startswith("size="):
                            cache_size = int(word[5:-1])
                            continue

                if key.startswith("processor "):
                    id = int(key.split()[1])
                    model = parts[1].split()[-1]
                    current = {
                        "processor-id": id,
                        "model": model,
                        "vendor": vendor,
                        "cache-size": cache_size,
                    }
                    processors.append(current)
                    continue
        finally:
            file.close()

        return processors


message_factories = [("(arm*|aarch64)", ARMMessageFactory),
                     ("ppc(64)?", PowerPCMessageFactory),
                     ("sparc[64]", SparcMessageFactory),
                     ("i[3-7]86|x86_64", X86MessageFactory),
                     ("s390x", S390XMessageFactory)]
