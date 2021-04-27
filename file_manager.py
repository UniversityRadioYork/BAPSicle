from helpers.state_manager import StateManager
from helpers.os_environment import resolve_external_file_path
from typing import List
from setproctitle import setproctitle
from multiprocessing import current_process, Queue
from time import sleep
import os
import json
from syncer import sync

from helpers.logging_manager import LoggingManager
from helpers.the_terminator import Terminator
from helpers.myradio_api import MyRadioAPI
from baps_types.plan import PlanItem


class FileManager:
    logger: LoggingManager
    api: MyRadioAPI

    def __init__(self, channel_from_q: List[Queue], server_config: StateManager):

        self.logger = LoggingManager("FileManager")
        self.api = MyRadioAPI(self.logger, server_config)

        process_title = "File Manager"
        setproctitle(process_title)
        current_process().name = process_title

        terminator = Terminator()
        channel_count = len(channel_from_q)
        channel_received = None
        last_known_show_plan = [[]]*channel_count
        next_channel_preload = 0
        last_known_item_ids = [[]]*channel_count
        try:

            while not terminator.terminate:
                # If all channels have received the delete command, reset for the next one.
                if (channel_received == None or channel_received == [True]*channel_count):
                  channel_received = [False]*channel_count

                for channel in range(channel_count):
                    try:
                        message = channel_from_q[channel].get_nowait()
                        #source = message.split(":")[0]
                        command = message.split(":",2)[1]

                        # If we have requested a new show plan, empty the music-tmp directory for the previous show.
                        if command == "GET_PLAN":

                          if channel_received != [False]*channel_count and channel_received[channel] != True:
                            # We've already received a delete trigger on a channel, let's not delete the folder more than once.
                            # If the channel was already in the process of being deleted, the user has requested it again, so allow it.

                            channel_received[channel] = True
                            continue

                          # Delete the previous show files!
                          # Note: The players load into RAM. If something is playing over the load, the source file can still be deleted.
                          path: str = resolve_external_file_path("/music-tmp/")

                          if not os.path.isdir(path):
                              self.logger.log.warning("Music-tmp folder is missing, not handling.")
                              continue

                          files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
                          for file in files:
                            filepath = path+"/"+file
                            self.logger.log.info("Removing file {} on new show load.".format(filepath))
                            os.remove(filepath)
                          channel_received[channel] = True

                        # If we receive a new status message, let's check for files which have not been pre-loaded.
                        if command == "STATUS":
                          extra = message.split(":",3)
                          if extra[2] != "OKAY":
                            continue

                          status = json.loads(extra[3])
                          show_plan = status["show_plan"]
                          item_ids = []
                          for item in show_plan:
                            item_ids += item["timeslotitemid"]

                          # If the new status update has a different order / list of items, let's update the show plan we know about
                          # This will trigger the chunk below to do the rounds again and preload any new files.
                          if item_ids != last_known_item_ids[channel]:
                            last_known_item_ids[channel] = item_ids
                            last_known_show_plan[channel] = show_plan

                    except Exception:
                        pass


                # Right, let's have a quick check in the status for shows without filenames, to preload them.
                delay = True
                for i in range(len(last_known_show_plan[next_channel_preload])):

                  item_obj = PlanItem(last_known_show_plan[next_channel_preload][i])
                  if not item_obj.filename:
                    self.logger.log.info("Checking pre-load on channel {}, weight {}: {}".format(next_channel_preload, item_obj.weight, item_obj.name))

                    # Getting the file name will only pull the new file if the file doesn't already exist, so this is not too inefficient.
                    item_obj.filename,did_download = sync(self.api.get_filename(item_obj, True))
                    # Alright, we've done one, now let's give back control to process new statuses etc.

                    # Save back the resulting item back in regular dict form
                    last_known_show_plan[next_channel_preload][i] = item_obj.__dict__

                    if did_download:
                      # Given we probably took some time to download, let's not sleep in the loop.
                      delay = False
                      self.logger.log.info("File successfully preloaded: {}".format(item_obj.filename))
                      break
                    else:
                      # We didn't download anything this time, file was already loaded.
                      # Let's try the next one.
                      continue
                next_channel_preload += 1
                if next_channel_preload >= channel_count:
                  next_channel_preload = 0
                if delay:
                  sleep(0.1)
        except Exception as e:
            self.logger.log.exception(
                "Received unexpected exception: {}".format(e))
        del self.logger
