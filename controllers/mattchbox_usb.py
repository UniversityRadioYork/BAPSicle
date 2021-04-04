from typing import List
from controllers.controller import Controller
from multiprocessing import Queue
import serial
import sys
from setproctitle import setproctitle
class MattchBox(Controller):
  ser: serial.Serial

  def __init__(self, player_to_q: List[Queue], player_from_q: List[Queue]):

    process_title = "ControllerHandler"
    setproctitle(process_title)
    #current_process().name = process_title

    # connect to serial port
    self.ser = serial.serial_for_url("/dev/cu.usbserial-210", do_not_open=True)
    self.ser.baudrate = 2400

    # TOOD: These need to be split in the player handler.
    self.player_from_q = player_from_q
    self.player_to_q = player_to_q

    try:
        self.ser.open()
    except serial.SerialException as e:
        sys.stderr.write('Could not open serial port {}: {}\n'.format(self.ser.name, e))
        return

    self.handler()

  def handler(self):
      while True:
        try:
          if self.ser.is_open:
            line = int.from_bytes(self.ser.read(1), "big") # Endianness doesn't matter for 1 byte.
            print("Controller got:", line)
            if (line == 255):
              print("Sending back KeepAlive")
              self.ser.write(b'\xff') # Send 255 back.
            elif (line in [1,3,5]):
              self.sendToPlayer(int(line / 2), "PLAY")
            elif (line in [2,4,6]):
              self.sendToPlayer(int(line / 2)-1, "STOP")

        except:
          continue

  def sendToPlayer(self, channel: int, msg:str):
    self.player_to_q[channel].put("CONTROLLER:" + msg)


