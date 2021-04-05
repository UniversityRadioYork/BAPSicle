import json
from multiprocessing import Queue #, current_process
from helpers.logging_manager import LoggingManager
from helpers.myradio_api import MyRadioAPI
from setproctitle import setproctitle
from os import _exit

# The API handler is needed from the main flask thread to process API requests.
# Flask is not able to handle these during page loads, requests.get() hangs.
# TODO: This is single threadded, but it probably doesn't need to be multi.
class APIHandler():
  logger: LoggingManager
  api: MyRadioAPI
  server_to_q: Queue
  server_from_q: Queue

  def __init__(self, server_from_q: Queue, server_to_q: Queue):

    process_title = "APIHandler"
    setproctitle(process_title)
    #current_process().name = process_title

    self.server_from_q = server_from_q
    self.server_to_q = server_to_q
    self.logger = LoggingManager("APIHandler")
    self.api = MyRadioAPI(self.logger)

    self.handle()

  def handle(self):
    try:
      while self.server_from_q:
        # Wait for an API request to come in.
        request = self.server_from_q.get()
        self.logger.log.info("Received Request: {}".format(request))
        if request == "LIST_PLANS":
          self.server_to_q.put(request + ":" + json.dumps(self.api.get_showplans()))
        elif request == "LIST_PLAYLIST_MUSIC":
          self.server_to_q.put(request + ":" + json.dumps(self.api.get_playlist_music()))
        elif request == "LIST_PLAYLIST_AUX":
          self.server_to_q.put(request + ":" + json.dumps(self.api.get_playlist_aux()))

        else:
          # Commands with params
          command = request[:request.index(":")]
          params = request[request.index(":")+1:]



          if command == "GET_PLAYLIST_AUX":
            self.server_to_q.put(request + ":" + json.dumps(self.api.get_playlist_aux_items(str(params))))
          elif command == "GET_PLAYLIST_MUSIC":
            self.server_to_q.put(request + ":" + json.dumps(self.api.get_playlist_music_items(str(params))))
          elif command == "SEARCH_TRACK":
            try:
              params = json.loads(params)

              self.server_to_q.put(request + ":" + json.dumps(self.api.get_track_search(str(params["title"]), str(params["artist"]))))
            except Exception as e:
              self.logger.log.exception("Failed to parse params with message {}, command {}, params {}\n{}".format(request, command, params, e))

    # Catch the handler being killed externally.
    except KeyboardInterrupt:
        self.logger.log.info("Received KeyboardInterupt")
    except SystemExit:
        self.logger.log.info("Received SystemExit")
    except Exception as e:
        self.logger.log.exception("Received unexpected exception: {}".format(e))
    del self.logger
    _exit(0)
