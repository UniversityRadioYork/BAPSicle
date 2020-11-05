"""
    BAPSicle Server
    Next-gen audio playout server for University Radio York playout,
    based on WebStudio interface.

    MyRadio API Handler

    Authors:
        Matthew Stratford
        Michael Grace

    Date:
        November 2020
"""
import requests

import config
from helpers.os_environment import resolve_external_file_path


class MyRadioAPI():

  @classmethod
  def secure_play(self, trackId: int, format: str = "mp3"):
    url = "{}/NIPSWeb/secure_play?trackid={}&{}&api_key={}".format(config.MYRADIO_BASE_URL, trackId, format, config.API_KEY)

    request = requests.get(url)

    if request.status_code != 200:
      return False

    filename: str = resolve_external_file_path("/music-tmp/{}.{}".format(trackId,format))
    with open(filename, 'wb') as file:
      file.write(request.content)

    return filename
