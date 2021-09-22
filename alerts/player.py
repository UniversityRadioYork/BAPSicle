# Any alerts produced by the player.py instances.
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from helpers.os_environment import resolve_external_file_path
from helpers.alert_manager import AlertProvider
from baps_types.alert import CRITICAL, WARNING, Alert
from baps_types.happytime import happytime

MODULE = "Player"  # This should match the log file, so the UI will link to the logs page.


class PlayerAlertProvider(AlertProvider):

    _server_state: Dict[str, Any]
    _states: List[Optional[Dict[str, Any]]] = []
    _player_count: int

    def __init__(self):
        # Player count only changes after server restart, may as well just load this once.
        with open(resolve_external_file_path("state/BAPSicleServer.json")) as file:
            self._server_state = json.loads(file.read())

        self._player_count = int(self._server_state["num_channels"])
        self._states = [None] * self._player_count

    # To simplify monitoring (and allow detection of things going super
    # weird), we are going to read from the state file to work out the alerts.
    def get_alerts(self):
        for channel in range(self._player_count):
            with open(resolve_external_file_path("state/Player{}.json".format(channel))) as file:
                self._states[channel] = json.loads(file.read())

        funcs = [self._channel_count, self._initialised, self._start_time]

        alerts: List[Alert] = []

        for func in funcs:
            func_alerts = func()
            if func_alerts:
                alerts.extend(func_alerts)

        return alerts

    def _channel_count(self):
        if self._player_count <= 0:
            return [Alert({
                "start_time": -1,  # Now
                "id": "no_channels",
                "title": "There are no players configured.",
                "description": "The number of channels configured is {}. \
                  Please set to at least 1 on the 'Server Config' page."
                .format(self._player_count),
                "module": MODULE+"Handler",
                "severity": CRITICAL
            })]

    def _initialised(self):
        alerts: List[Alert] = []
        for channel in range(self._player_count):
            if self._states[channel] and not self._states[channel]["initialised"]:
                alerts.append(Alert({
                    "start_time": -1,  # Now
                    "id": "player_{}_not_initialised".format(channel),
                    "title": "Player {} is not initialised.".format(channel),
                    "description": "This typically means the player channel was not able find the configured sound output \
                    on the system. Please check the 'Player Config' and Player logs to determine the cause.",
                    "module": MODULE+str(channel),
                    "severity": CRITICAL
                }))
        return alerts

    def _start_time(self):
        server_start_time = self._server_state["start_time"]
        server_start_time = datetime.fromtimestamp(server_start_time)
        delta = timedelta(
            seconds=30,
        )

        alerts: List[Alert] = []
        for channel in range(self._player_count):
            start_time = self._states[channel]["start_time"]
            start_time = datetime.fromtimestamp(start_time)
            if (start_time > server_start_time + delta):
                alerts.append(Alert({
                    "start_time": -1,
                    "id": "player_{}_restarted".format(channel),
                    "title": "Player {} restarted after the server started.".format(channel),
                    "description":
                    """Player {} last restarted at {}, after the server first started at {}, suggesting a failure.

This likely means there was an unhandled exception in the player code, causing the server to restart the player.

Please check player logs to investigate the cause. Please restart the server to clear this warning."""
                    .format(channel, happytime(start_time), happytime(server_start_time)),
                    "module": MODULE+str(channel),
                    "severity": WARNING
                }))
        return alerts
