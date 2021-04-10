from typing import Any, Dict, List, Optional
import sounddevice as sd
from helpers.os_environment import isLinux, isMacOS, isWindows
import glob


class DeviceManager:
    @classmethod
    def _isOutput(cls, device: Dict[str, Any]) -> bool:
        return device["max_output_channels"] > 0

    @classmethod
    def _getAudioDevices(cls) -> sd.DeviceList:
        # To update the list of devices
        # Sadly this doesn't work on MacOS.
        if not isMacOS():
            sd._terminate()
            sd._initialize()
        devices: sd.DeviceList = sd.query_devices()
        return devices

    @classmethod
    def getAudioOutputs(cls) -> List[Dict]:
        outputs: List[Dict] = list(filter(cls._isOutput, cls._getAudioDevices()))
        outputs = sorted(outputs, key=lambda k: k["name"])
        return [{"name": None}] + outputs

    @classmethod
    def getSerialPorts(cls) -> List[Optional[str]]:
        """Lists serial port names

        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of the serial ports available on the system
        """
        # TODO: Get list of COM ports properly. (Can't use )
        if isWindows():
            ports = ["COM%s" % (i + 1) for i in range(8)]
        elif isLinux():
            # this excludes your current terminal "/dev/tty"
            ports = glob.glob("/dev/tty[A-Za-z]*")
        elif isMacOS():
            ports = glob.glob("/dev/tty.*")
        else:
            raise EnvironmentError("Unsupported platform")

        valid: List[str] = ports

        result: List[Optional[str]] = []

        if len(valid) > 0:
            valid.sort()

        result.append(None)  # Add the None option
        result.extend(valid)

        return result
