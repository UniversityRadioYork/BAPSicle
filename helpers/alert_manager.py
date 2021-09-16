from typing import Any, List

#Magic for importing alert providers from alerts directory.
from pkgutil import iter_modules
from importlib import import_module
from inspect import getmembers,isclass
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
      classes: List[Any] = [mem[1] for mem in getmembers(modules[provider], isclass) if mem[1].__module__ == modules[provider].__name__]

      if (len(classes) != 1):
        print(classes)
        raise Exception("Can't import plugin " + provider + " because it doesn't have 1 class.")

      self._providers.append(classes[0]())


    print("Discovered alert providers: ", self._providers)

  def poll_alerts(self):

    # Poll modules for any alerts.
    alerts: List[Alert] = []
    for provider in self._providers:
      provider_alerts = provider.get_alerts()
      if provider_alerts:
        alerts.extend(provider_alerts)

    self._alerts = alerts

  @property
  def alerts_current(self):
    self.poll_alerts()
    return self._alerts

  @property
  def alert_count_current(self):
    self.poll_alerts()
    return len(self._alerts)

  @property
  def alert_count_previous(self):
    self.poll_alerts()
    return len(self._alerts)
