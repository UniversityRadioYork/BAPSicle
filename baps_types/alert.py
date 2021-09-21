from typing import Any, Dict, Optional
from datetime import datetime

CRITICAL = "Critical"
WARNING = "Warning"

class Alert:
    start_time: datetime
    last_time: datetime
    end_time: Optional[datetime]
    id: str
    title: str
    description: str
    module: str
    severity: str


    @property
    def ui_class(self) -> str:
      if self.severity == CRITICAL:
        return "danger"
      if self.severity == WARNING:
        return "warning"
      return "info"

    # This alert has happened again.
    def reoccured(self):
      self.last_time = datetime.now()
      self.end_time = None

    # This alert has finished, just update end time and keep last_time.
    def cleared(self):
      self.end_time = datetime.now()


    @property
    def __dict__(self):
        attrs = ["start_time", "last_time", "end_time", "id", "title", "description", "module", "severity"]
        out = {}
        for attr in attrs:
          out[attr] = self.__getattribute__(attr)

        return out

    def __init__(self, new_data: Dict[str,Any]):
      required_vars = [
        "start_time", # Just in case an alert wants to show starting earlier than it is reported.
        "id",
        "title",
        "description",
        "module",
        "severity"
      ]

      for key in required_vars:
        if key not in new_data.keys():
          raise KeyError("Key {} is missing from data to create Alert.".format(key))

        #if type(new_data[key]) != type(getattr(self,key)):
        #  raise TypeError("Key {} has type {}, was expecting {}.".format(key, type(new_data[key]), type(getattr(self,key))))

        # Account for if the creator didn't want to set a custom time.
        if key == "start_time" and new_data[key] == -1:
          new_data[key] = datetime.now()

        setattr(self,key,new_data[key])

      self.last_time = self.start_time
      self.end_time = None
