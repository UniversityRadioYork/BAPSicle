from helpers.logging_manager import LoggingManager
from setproctitle import setproctitle
#from multiprocessing import current_process
from time import sleep
from os import _exit

class PlayerHandler():
    logger: LoggingManager

    def __init__(self,channel_from_q, websocket_to_q, ui_to_q, controller_to_q):

        self.logger = LoggingManager("PlayerHandler")
        process_title = "PlayerHandler"
        setproctitle(process_title)
        #current_process().name = process_title

        try:
            while True:

                for channel in range(len(channel_from_q)):
                    try:
                        message = channel_from_q[channel].get_nowait()
                        source = message.split(":")[0]
                        # TODO ENUM
                        if source in ["ALL","WEBSOCKET"]:
                            websocket_to_q[channel].put(message)
                        if source in ["ALL","UI"]:
                            if not message.split(":")[1] == "POS":
                                # We don't care about position update spam
                                ui_to_q[channel].put(message)
                        if source in ["ALL","CONTROLLER"]:
                            controller_to_q[channel].put(message)
                    except:
                        pass

                sleep(0.01)
        # Catch the handler being killed externally.
        except KeyboardInterrupt:
            self.logger.log.info("Received KeyboardInterupt")
        except SystemExit:
            self.logger.log.info("Received SystemExit")
        except Exception as e:
            self.logger.log.exception("Received unexpected exception: {}".format(e))
        del self.logger
        _exit(0)

