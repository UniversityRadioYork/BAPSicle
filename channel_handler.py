from setproctitle import setproctitle
from multiprocessing import current_process
from time import sleep
from os import _exit

from helpers.logging_manager import LoggingManager
from helpers.the_terminator import Terminator


class ChannelHandler:
    logger: LoggingManager

    def __init__(self, channel_from_q, websocket_to_q, ui_to_q, controller_to_q, file_to_q):

        self.logger = LoggingManager("ChannelHandler")
        process_title = "Channel Handler"
        setproctitle(process_title)
        current_process().name = process_title

        terminator = Terminator()
        try:
            while not terminator.terminate:

                for channel in range(len(channel_from_q)):
                    try:
                        message = channel_from_q[channel].get_nowait()
                        source = message.split(":")[0]
                        command = message.split(":")[1]

                        # Let the file manager manage the files based on status and loading new show plan triggers.
                        if command == "GET_PLAN" or command == "STATUS":
                            file_to_q[channel].put(message)


                        # TODO ENUM
                        if source in ["ALL", "WEBSOCKET"]:
                            websocket_to_q[channel].put(message)
                        if source in ["ALL", "UI"]:
                            if not message.split(":")[1] == "POS":
                                # We don't care about position update spam
                                ui_to_q[channel].put(message)
                        if source in ["ALL", "CONTROLLER"]:
                            controller_to_q[channel].put(message)
                    except Exception:
                        pass

                sleep(0.02)
        except Exception as e:
            self.logger.log.exception(
                "Received unexpected exception: {}".format(e))
        del self.logger
        _exit(0)
