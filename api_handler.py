import json
from multiprocessing import Queue
from helpers.logging_manager import LoggingManager
from helpers.myradio_api import MyRadioAPI

# The API handler is needed from the main flask thread to process API requests.
# Flask is not able to handle these during page loads, requests.get() hangs.
# TODO: This is single threadded, but it probably doesn't need to be multi.
class APIHandler():
  logger: LoggingManager
  api: MyRadioAPI
  server_to_q: Queue
  server_from_q: Queue

  def __init__(self, server_from_q: Queue, server_to_q: Queue):
    self.server_from_q = server_from_q
    self.server_to_q = server_to_q
    self.logger = LoggingManager("APIHandler")
    self.api = MyRadioAPI(self.logger)

    self.handle()

  def handle(self):
    while self.server_from_q:
      # Wait for an API request to come in.
      request = self.server_from_q.get()
      self.logger.log.info("Recieved Request: {}".format(request))
      if request == "LIST_PLANS":
        self.server_to_q.put(request + ":" + json.dumps(self.api.get_showplans()))
      elif request.startswith("SEARCH_TRACK:"):
        params = request[request.index(":")+1:]

        try:
          params = json.loads(params)
        except Exception as e:
          raise e

        self.server_to_q.put("SEARCH_TRACK:" + json.dumps(self.api.get_track_search(params["title"], params["artist"])))
