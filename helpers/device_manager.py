import sounddevice as sd
import importlib
from helpers.os_environment import isMacOS


class DeviceManager():

    @classmethod
    def _isOutput(self, device):
        return device["max_output_channels"] > 0

    @classmethod
    def _getDevices(self):
        # To update the list of devices
        # Sadly this doesn't work on MacOS.
        if not isMacOS():
            sd._terminate()
            sd._initialize()
        devices = sd.query_devices()
        return devices

    @classmethod
    def getOutputs(self):
        outputs = filter(self._isOutput, self._getDevices())

        return outputs

    # TODO: Maybe some hotplug event triggers support for the players?
