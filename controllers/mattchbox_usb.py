
from helpers.the_terminator import Terminator
from typing import List, Optional
from multiprocessing import Queue, current_process
import serial
import time
from setproctitle import setproctitle

from helpers.logging_manager import LoggingManager
from helpers.state_manager import StateManager
from controllers.controller import Controller


class MattchBox(Controller):
    ser: Optional[serial.Serial]
    port: Optional[str]
    next_port: Optional[str]
    server_state: StateManager
    logger: LoggingManager

    def __init__(
        self, server_to_q: List[Queue], server_from_q: List[Queue], state: StateManager
    ):

        process_title = "ControllerHandler"
        setproctitle(process_title)
        current_process().name = process_title

        self.ser = None
        self.logger = LoggingManager("ControllerMattchBox")

        self.server_state = state  # This is a copy, will not update :/

        # This doesn't run, the callback function gets lost
        # due to state being a copy in the multiprocessing process.
        # self.server_state.add_callback(self._state_handler)

        # Allow server config changes to trigger controller reload if required.
        self.port = None
        self.next_port = self.server_state.get()["serial_port"]
        self.logger.log.info("Server config gives port as: {}".format(self.next_port))

        self.server_from_q = server_from_q
        self.server_to_q = server_to_q

        self.handler()

    # This doesn't run, the callback function gets lost in StateManager.

    def _state_handler(self):
        new_port = self.server_state.get()["serial_port"]
        self.logger.log.info("Got server config update. New port: {}".format(new_port))
        if new_port != self.port:
            self.logger.log.info(
                "Switching from port {} to {}".format(self.port, new_port)
            )
            # The serial port config has changed. Let's reload the serial.
            self.port = None
            self.next_port = new_port

    def _disconnected(self):
        # If we lose the controller, make sure to set channels live, so we tracklist.
        for i in range(len(self.server_from_q)):
            self.sendToPlayer(i, "SETLIVE:True")
        self.server_state.update("ser_connected", False)

    def connect(self, port: Optional[str]):

        if port:
            # connect to serial port
            self.ser = serial.serial_for_url(port, do_not_open=True)
            self.ser.baudrate = 2400
            try:
                self.ser.open()
                self.logger.log.info("Connected to serial port {}".format(port))
            except serial.SerialException as e:
                self.logger.log.error(
                    "Could not open serial port" + str(port),
                    e
                )
                self._disconnected()
                self.ser = None
        else:
            self.ser = None

    def handler(self):
        terminator = Terminator()
        while not terminator.terminate:
            if (
                self.ser and self.ser.is_open and self.port
            ):  # If self.port is changing (via state_handler), we should stop.
                try:
                    line = int.from_bytes(
                        self.ser.read(1), "big"
                    )  # Endianness doesn't matter for 1 byte.
                    self.logger.log.info("Received from controller: " + str(line))
                    if line == 255:
                        self.ser.write(b"\xff")  # Send 255 back, this is a keepalive.
                    elif line in [51,52,53]:
                        # We've received a status update about fader live status, fader is down.
                        self.sendToPlayer(line-51, "SETLIVE:False")
                    elif line in [61,62,63]:
                        # We've received a status update about fader live status, fader is up.
                        self.sendToPlayer(line-61, "SETLIVE:True")
                    elif line in [1, 3, 5]:
                        self.sendToPlayer(int(line / 2), "PLAYPAUSE")
                    elif line in [2, 4, 6]:
                        self.sendToPlayer(int(line / 2) - 1, "STOP")
                except Exception:
                    time.sleep(5)
                    self.connect(self.port)
                finally:
                    time.sleep(0.01)

            elif self.port:
                # If there's still a port set, just wait a moment and see if it's been reconnected.
                self._disconnected()
                time.sleep(10)
                self.connect(self.port)

            else:
                # We're not already connected, or a new port connection is to be made.
                if self.ser:
                    self.ser.close()
                    self._disconnected()

                if self.next_port is not None:
                    self.connect(self.next_port)
                    if self.ser and self.ser.is_open:
                        self.port = (
                            self.next_port
                        )  # We connected successfully, make it stick.
                        self.server_state.update("ser_connected", True)
                        continue  # skip the sleep.
                time.sleep(10)

        self.connect(None)

    def sendToPlayer(self, channel: int, msg: str):
        self.logger.log.info("Sending message to player channel {}: {}".format(channel, msg))
        self.server_to_q[channel].put("CONTROLLER:" + msg)
