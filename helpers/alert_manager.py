from typing import List
from baps_types.alert import CRITICAL, Alert

class AlertManager():
  _alerts: List[Alert]

  def __init__(self):
    self._alerts = [Alert(
      {
        "start_time": -1,
        "id": "test",
        "title": "Test Alert",
        "description": "This is a test alert.",
        "module": "Test",
        "severity": CRITICAL
      }
    )]

  @property
  def alerts_current(self):
    return self._alerts

  @property
  def alert_count_current(self):
    return len(self._alerts)

  @property
  def alert_count_previous(self):
    return len(self._alerts)
