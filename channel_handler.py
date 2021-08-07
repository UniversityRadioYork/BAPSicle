from queue import Empty
from typing import List
from setproctitle import setproctitle
from multiprocessing import Queue
from threading import current_thread
import queue
from time import sleep
from os import _exit

from helpers.logging_manager import LoggingManager
from helpers.the_terminator import Terminator


class ChannelHandler:
    logger: LoggingManager

    def __init__(self, channel_from_q: List[Queue], websocket_to_q: queue.Queue, ui_to_q:queue.Queue, controller_to_q:queue.Queue, file_to_q: queue.Queue):

        self.logger = LoggingManager("ChannelHandler")
        process_title = "Channel Handler"
        setproctitle(process_title)
        current_thread().name = process_title

        terminator = Terminator()
        try:
            while not terminator.terminate:
                for channel in range(len(channel_from_q)):
                    try:
                        message = channel_from_q[channel].get_nowait()
                        source = message.split(":")[0]
                        command = message.split(":")[1]

                        # Append the channel number to save on multiple output queues.
                        message = str(channel) + ":" + message

                        # Let the file manager manage the files based on status and loading new show plan triggers.
                        if command == "GET_PLAN" or command == "STATUS":
                            file_to_q.put(message)
                        if source in ["ALL", "WEBSOCKET"]:
                            websocket_to_q.put(message)
                        if source in ["ALL", "UI"]:
                            if not command == "POS":
                                # We don't care about position update spam
                                ui_to_q.put(message)
                        if source in ["ALL", "CONTROLLER"]:
                            controller_to_q.put(message)
                    except Empty:
                        pass

                sleep(0.02)
        except Exception as e:
            self.logger.log.exception(
                "Received unexpected exception: {}".format(e))
        del self.logger
        _exit(0)
