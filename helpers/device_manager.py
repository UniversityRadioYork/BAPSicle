from typing import Any, Dict
import sounddevice as sd
from helpers.os_environment import isMacOS


class DeviceManager():

    @classmethod
    def _isOutput(cls, device:Dict[str,Any]) -> bool:
        return device["max_output_channels"] > 0

    @classmethod
    def _getDevices(cls) -> sd.DeviceList:
        # To update the list of devices
        # Sadly this doesn't work on MacOS.
        if not isMacOS():
            sd._terminate()
            sd._initialize()
        devices: sd.DeviceList = sd.query_devices()
        return devices

    @classmethod
    def getOutputs(cls) -> sd.DeviceList:
        outputs: sd.DeviceList = filter(cls._isOutput, cls._getDevices())

        return outputs
