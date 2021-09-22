from typing import Any, List, Optional

# Magic for importing alert providers from alerts directory.
from pkgutil import iter_modules
from importlib import import_module
from inspect import getmembers, isclass
from sys import modules

from baps_types.alert import CRITICAL, Alert
import alerts


def iter_namespace(ns_pkg):
    # Specifying the second argument (prefix) to iter_modules makes the
    # returned name an absolute name instead of a relative one. This allows
    # import_module to work without having to do additional modification to
    # the name.
    return iter_modules(ns_pkg.__path__, ns_pkg.__name__ + ".")


class AlertProvider():

    def __init__(self):
        return None

    def get_alerts(self):
        return []


class AlertManager():
    _alerts: List[Alert]
    _providers: List[AlertProvider] = []

    def __init__(self):
        self._alerts = []

        # Find all the alert providers from the /alerts/ directory.
        providers = {
            name: import_module(name)
            for _, name, _
            in iter_namespace(alerts)
        }

        for provider in providers:
            classes: List[Any] = [
                mem[1] for mem in getmembers(
                    modules[provider],
                    isclass) if mem[1].__module__ == modules[provider].__name__]

            if (len(classes) != 1):
                print(classes)
                raise Exception("Can't import plugin " + provider + " because it doesn't have 1 class.")

            self._providers.append(classes[0]())

        print("Discovered alert providers: ", self._providers)

    def poll_alerts(self):

        # Poll modules for any alerts.
        new_alerts: List[Optional[Alert]] = []
        for provider in self._providers:
            provider_alerts = provider.get_alerts()
            if provider_alerts:
                new_alerts.extend(provider_alerts)

        # Here we replace new firing alerts with older ones, to keep any context.
        # (This doesn't do anything yet really, for future use.)
        for existing in self._alerts:
            found = False
            for new in new_alerts:
                # given we're removing alerts, got to skip any we removed.
                if not new:
                    continue

                if existing.id == new.id:
                    # Alert is continuing. Replace it with the old one.
                    index = new_alerts.index(new)
                    existing.reoccured()
                    new_alerts[index] = None  # We're going to merge the existing and new, so clear the new one out.
                    found = True
                    break
            if not found:
                # The existing alert is gone, mark it as ended.
                existing.cleared()

        self._alerts.extend([value for value in new_alerts if value])  # Remove any nulled out new alerts

    @property
    def alerts_current(self):
        self.poll_alerts()
        return [alert for alert in self._alerts if not alert.end_time]

    @property
    def alerts_previous(self):
        self.poll_alerts()
        return [alert for alert in self._alerts if alert.end_time]
