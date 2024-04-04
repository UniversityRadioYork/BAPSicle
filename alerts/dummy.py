from helpers.alert_manager import AlertProvider
from package import BETA
from baps_types.alert import WARNING, Alert
# Dummy alert provider for testing basics like UI without needing to actually cause errors.


class DummyAlertProvider(AlertProvider):

    def get_alerts(self):
        if BETA:
            return [Alert(
                {
                    "start_time": -1,
                    "id": "test",
                    "title": "BAPSicle is in Debug Mode",
                    "description": "This is a test alert. It will not appear on production builds.",
                    "module": "Test",
                    "severity": WARNING
                }
            )]
