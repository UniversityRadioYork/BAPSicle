"""
    BAPSicle Server
    Next-gen audio playout server for University Radio York playout,
    based on WebStudio interface.

    MyRadio API Handler

    In an ideal world, this module gives out and is fed PlanItems.
    This means it can be swapped for a different backend in the (unlikely) event
    someone else wants to integrate BAPsicle with something else.

    Authors:
        Matthew Stratford
        Michael Grace

    Date:
        November 2020
"""
from typing import Optional
import requests
import json
import config
from plan import PlanItem
from helpers.os_environment import resolve_external_file_path
from helpers.logging_manager import LoggingManager
from logging import CRITICAL, INFO, DEBUG
class MyRadioAPI():
  logger = None

  def __init__(self, logger: LoggingManager):
    self.logger = logger

  def get_non_api_call(self, url):

    url = "{}{}".format(config.MYRADIO_BASE_URL, url)

    if "?" in url:
      url += "&api_key={}".format(config.API_KEY)
    else:
      url += "?api_key={}".format(config.API_KEY)

    self._log("Requesting non-API URL: " + url)
    request = requests.get(url, timeout=10)
    self._log("Finished request.")

    if request.status_code != 200:
      self._logException("Failed to get API request. Status code: " + str(request.status_code))
      self._logException(str(request.content))
      return None

    return request

  def get_apiv2_call(self, url):

    url = "{}/v2{}".format(config.MYRADIO_API_URL, url)

    if "?" in url:
      url += "&api_key={}".format(config.API_KEY)
    else:
      url += "?api_key={}".format(config.API_KEY)

    self._log("Requesting API V2 URL: " + url)
    request = requests.get(url, timeout=10)
    self._log("Finished request.")

    if request.status_code != 200:
      self._logException("Failed to get API request. Status code: " + str(request.status_code))
      self._logException(str(request.content))
      return None

    return request




  # Show plans


  def get_showplans(self):
    url = "/timeslot/currentandnext"
    request = self.get_apiv2_call(url)

    if not request:
      self._logException("Failed to get list of show plans.")
      return None

    return json.loads(request.content)["payload"]

  def get_showplan(self, timeslotid: int):

    url = "/timeslot/{}/showplan".format(timeslotid)
    request = self.get_apiv2_call(url)

    if not request:
      self._logException("Failed to get show plan.")
      return None

    return json.loads(request.content)["payload"]



  # Audio Library

  def get_filename(self, item: PlanItem):
    format = "mp3" # TODO: Maybe we want this customisable?
    if item.trackid:
      itemType = "track"
      id = item.trackid
      url = "/NIPSWeb/secure_play?trackid={}&{}".format(id, format)

    elif item.managedid:
      itemType = "managed"
      id = item.managedid
      url = "/NIPSWeb/managed_play?managedid={}".format(id)

    else:
      return None


    request = self.get_non_api_call(url)

    if not request:
      return None

    filename: str = resolve_external_file_path("/music-tmp/{}-{}.{}".format(itemType, id, format))

    with open(filename, 'wb') as file:
      file.write(request.content)

    return filename

  def get_track_search(self, title: Optional[str], artist: Optional[str], limit: int = 100):
    url = "/track/search?title={}&artist={}&digitised=1&limit={}".format(title if title else "", artist if artist else "", limit)
    request = self.get_apiv2_call(url)

    if not request:
      self._logException("Failed to search for track.")
      return None

    return json.loads(request.content)["payload"]



  def _log(self, text:str, level: int = INFO):
      self.logger.log.log(level, "MyRadio API: " + text)

  def _logException(self, text:str):
      self.logger.log.exception("MyRadio API: " + text)

