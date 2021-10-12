from typing import Any, Dict, List, Optional, Tuple
import sounddevice as sd
from helpers.os_environment import isLinux, isMacOS, isWindows
import glob

if isWindows():
    from serial.tools.list_ports_windows import comports

# TODO: https://wiki.libsdl.org/FAQUsingSDL maybe try setting some of these env variables for choosing different host APIs?
WINDOWS_APIS = ["Windows DirectSound"]


class DeviceManager:
    @classmethod
    def _isOutput(cls, device: Dict[str, Any]) -> bool:
        return device["max_output_channels"] > 0

    @classmethod
    def _isHostAPI(cls, host_api) -> bool:
        return host_api

    @classmethod
    def _getSDAudioDevices(cls):
        # To update the list of devices
        # Sadly this only works on Windows. Linux hangs, MacOS crashes.
        if isWindows():
            sd._terminate()
            sd._initialize()
        devices: sd.DeviceList = sd.query_devices()
        return devices

    @classmethod
    def getAudioOutputs(cls) -> Tuple[List[Dict]]:

        host_apis = list(sd.query_hostapis())
        devices: sd.DeviceList = cls._getSDAudioDevices()

        for host_api_id in range(len(host_apis)):
            # Linux SDL uses PortAudio, which SoundDevice doesn't find. So mark all as unsable.
            if (isWindows() and host_apis[host_api_id]["name"] not in WINDOWS_APIS) or (isLinux()):
                host_apis[host_api_id]["usable"] = False
            else:
                host_apis[host_api_id]["usable"] = True

            host_api_devices = (
                device for device in devices if device["hostapi"] == host_api_id
            )

            outputs: List[Dict] = list(filter(cls._isOutput, host_api_devices))
            outputs = sorted(outputs, key=lambda k: k["name"])

            host_apis[host_api_id]["output_devices"] = outputs

        return host_apis

    @classmethod
    def getSerialPorts(cls) -> List[Optional[str]]:
        """Lists serial port names

        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of the serial ports available on the system
        """
        if isWindows():
            ports = [port.device for port in comports()]
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
