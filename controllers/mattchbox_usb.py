from helpers.logging_manager import LoggingManager
from helpers.state_manager import StateManager
from typing import List, Optional
from controllers.controller import Controller
from multiprocessing import Queue
import serial
import time
from setproctitle import setproctitle

class MattchBox(Controller):
  ser: Optional[serial.Serial]
  port: Optional[str]
  next_port: Optional[str]
  server_state: StateManager
  logger: LoggingManager

  def __init__(self, server_to_q: List[Queue], server_from_q: List[Queue], state: StateManager):

    process_title = "ControllerHandler"
    setproctitle(process_title)

    self.ser = None
    self.logger = LoggingManager("ControllerMattchBox")
    #current_process().name = process_title

    self.server_state = state # This is a copy, will not update :/
    # This doesn't run, the callback function gets lost due to state being a copy in the multiprocessing process.
    #self.server_state.add_callback(self._state_handler) # Allow server config changes to trigger controller reload if required.
    self.port = None
    self.next_port = self.server_state.state["serial_port"]

    self.server_from_q = server_from_q
    self.server_to_q = server_to_q

    self.handler()

  # This doesn't run, the callback function gets lost in StateManager.
  def _state_handler(self):
      new_port = self.server_state.state["serial_port"]
      self.logger.log.info("Got server config update. New port: {}".format(new_port))
      if new_port != self.port:
        self.logger.log.info("Switching from port {} to {}".format(self.port, new_port))
        # The serial port config has changed. Let's reload the serial.
        self.port = None
        self.next_port = new_port

  def connect(self, port: Optional[str]):
      if port:
        # connect to serial port
        self.ser = serial.serial_for_url(port, do_not_open=True)
        self.ser.baudrate = 2400
        try:
            self.ser.open()
            self.logger.log.info('Connected to serial port {}'.format(port))
        except serial.SerialException as e:
            self.logger.log.error('Could not open serial port {}: {}'.format(port, e))
            self.ser = None
      else:
        self.ser = None


  def handler(self):
      while True:
          if self.ser and self.ser.is_open and self.port: # If self.port is changing (via state_handler), we should stop.
            try:
              line = int.from_bytes(self.ser.read(1), "big") # Endianness doesn't matter for 1 byte.
              self.logger.log.info("Received from controller: " + str(line))
              if (line == 255):
                self.ser.write(b'\xff') # Send 255 back.
              elif (line in [1,3,5]):
                self.sendToPlayer(int(line / 2), "PLAY")
              elif (line in [2,4,6]):
                self.sendToPlayer(int(line / 2)-1, "STOP")
            except:
              continue
            finally:
              time.sleep(0.01)

          elif self.port:
            # If there's still a port set, just wait a moment and see if it's been reconnected.
            self.server_state.update("ser_connected", False)
            time.sleep(10)
            self.connect(self.port)

          else:
            # We're not already connected, or a new port connection is to be made.
            if self.ser:
              self.ser.close()
              self.server_state.update("ser_connected", False)

            if self.next_port != None:
              self.connect(self.next_port)
              if self.ser and self.ser.is_open:
                self.port = self.next_port # We connected successfully, make it stick.
                self.server_state.update("ser_connected", True)
                continue # skip the sleep.
            time.sleep(10)



  def sendToPlayer(self, channel: int, msg:str):
    self.logger.log.info("Sending message to server: " + msg)
    self.server_to_q[channel].put("CONTROLLER:" + msg)


