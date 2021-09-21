# Any alerts produced by the server.py layer. This likely means BIG issues.
import json
from typing import Any, Dict, List
from datetime import datetime, timedelta
from helpers.os_environment import resolve_external_file_path
from helpers.alert_manager import AlertProvider
from baps_types.alert import CRITICAL, WARNING, Alert
from baps_types.happytime import happytime

MODULE = "BAPSicleServer" # This should match the log file, so the UI will link to the logs page.

class ServerAlertProvider(AlertProvider):

  _state: Dict[str, Any]
  # To simplify monitoring (and allow detection of things going super weird), we are going to read from the state file to work out the alerts.
  def get_alerts(self):
    with open(resolve_external_file_path("state/BAPSicleServer.json")) as file:
      self._state = json.loads(file.read())


    funcs = [self._api_key, self._start_time]

    alerts: List[Alert] = []

    for func in funcs:
      func_alerts = func()
      if func_alerts:
        alerts.extend(func_alerts)

    return alerts

  def _api_key(self):
    if not self._state["myradio_api_key"]:
      return [Alert({
        "start_time": -1, # Now
        "id": "api_key_missing",
        "title": "MyRadio API Key is not configured.",
        "description": "This means you will be unable to load show plans, audio items, or tracklist. Please set one on the 'Server Config' page.",
        "module": MODULE,
        "severity": CRITICAL
      })]

    if len(self._state["myradio_api_key"]) < 10:
      return [Alert({
        "start_time": -1,
        "id": "api_key_missing",
        "title": "MyRadio API Key seems incorrect.",
        "description": "The API key is less than 10 characters, it's probably not a valid one. If it is valid, it shouldn't be.",
        "module": MODULE,
        "severity": WARNING
      })]

  def _start_time(self):
    start_time = self._state["start_time"]
    start_time = datetime.fromtimestamp(start_time)
    delta = timedelta(
      days=1,
    )
    if (start_time + delta > datetime.now()):
      return [Alert({
        "start_time": -1,
        "id": "server_restarted",
        "title": "BAPSicle restarted recently.",
        "description":
"""The BAPSicle server restarted at {}, less than a day ago.

It may have been automatically restarted by the OS.

If this is not expected, please check logs to investigate why BAPSicle restarted/crashed."""
        .format(happytime(start_time)),
        "module": MODULE,
        "severity": WARNING
      })]
