from setproctitle import setproctitle
from multiprocessing import current_process
from time import sleep
from os import _exit

from helpers.logging_manager import LoggingManager
from helpers.the_terminator import Terminator


class PlayerHandler:
    logger: LoggingManager

    def __init__(
        self, channel_from_q, websocket_to_q, ui_to_q, controller_to_q, file_to_q
    ):

        self.logger = LoggingManager("PlayerHandler")
        process_title = "Player Handler"
        setproctitle(process_title)
        current_process().name = process_title

        terminator = Terminator()
        try:
            while not terminator.terminate:
                try:
                    # Format <CHANNEL NUM>:<SOURCE>:<COMMAND>:<EXTRAS>
                    q_msg = channel_from_q.get_nowait()
                    if not isinstance(q_msg, str):
                        continue
                    split = q_msg.split(":", 1)
                    message = split[1]
                    source = message.split(":")[0]
                    command = message.split(":")[1]

                    # Let the file manager manage the files based on status and loading new show plan triggers.
                    if command == "GETPLAN" or command == "STATUS":
                        file_to_q.put(q_msg)

                    # TODO ENUM
                    if source in ["ALL", "WEBSOCKET"]:
                        websocket_to_q.put(q_msg)
                    if source in ["ALL", "UI"]:
                        if not message.split(":")[1] == "POS":
                            # We don't care about position update spam
                            ui_to_q.put(q_msg)
                    if source in ["ALL", "CONTROLLER"]:
                        controller_to_q.put(q_msg)
                except Exception:
                    pass

                sleep(0.02)
        except Exception as e:
            self.logger.log.exception(
                "Received unexpected exception: {}".format(e))
        del self.logger
        _exit(0)
