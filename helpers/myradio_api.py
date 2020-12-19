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
import requests

import config
from plan import PlanItem
from helpers.os_environment import resolve_external_file_path


class MyRadioAPI():

  @classmethod
  def get_filename(cls, item: PlanItem):
    format = "mp3" # TODO: Maybe we want this customisable?
    if item.trackId:
      itemType = "track"
      id = item.trackId
      url = "{}/NIPSWeb/secure_play?trackid={}&{}&api_key={}".format(config.MYRADIO_BASE_URL, id, format, config.API_KEY)

    elif item.managedId:
      itemType = "managed"
      id = item.managedId
      url = "{}/NIPSWeb/managed_play?managedid={}&api_key={}".format(config.MYRADIO_BASE_URL, id, config.API_KEY)

    else:
      return None

    request = requests.get(url, timeout=10)

    if request.status_code != 200:
      return None

    filename: str = resolve_external_file_path("/music-tmp/{}-{}.{}".format(itemType, id, format))

    with open(filename, 'wb') as file:
      file.write(request.content)

    return filename
