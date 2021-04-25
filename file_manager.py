import time
from helpers.os_environment import resolve_external_file_path
from typing import List
from setproctitle import setproctitle
from multiprocessing import current_process, Queue
from time import sleep
import os

from helpers.logging_manager import LoggingManager
from helpers.the_terminator import Terminator


class FileManager:
    logger: LoggingManager

    def __init__(self, channel_from_q: List[Queue], server_config):

        self.logger = LoggingManager("FileManager")
        process_title = "File Manager"
        setproctitle(process_title)
        current_process().name = process_title

        terminator = Terminator()
        channel_count = len(channel_from_q)
        channel_received = None
        try:

            while not terminator.terminate:
                # If all channels have received the delete command, reset for the next one.
                if (channel_received == None or channel_received == [True]*channel_count):
                  channel_received = [False]*channel_count

                for channel in range(channel_count):
                    try:
                        message = channel_from_q[channel].get_nowait()
                        #source = message.split(":")[0]
                        command  = message.split(":",2)[1]
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
                            os.remove(path+"/"+file)
                          channel_received[channel] = True


                    except Exception:
                        pass

                sleep(1)
        except Exception as e:
            self.logger.log.exception(
                "Received unexpected exception: {}".format(e))
        del self.logger
