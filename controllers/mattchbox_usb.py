from typing import List
from controllers.controller import Controller
from multiprocessing import Queue
import serial
import sys

class MattchBox(Controller):
  ser: serial.Serial

  def __init__(self, player_to_q: List[Queue], player_from_q: List[Queue]):
    # connect to serial port
    self.ser = serial.serial_for_url("/dev/cu.usbserial-310", do_not_open=True)
    self.ser.baudrate = 2400

    # TOOD: These need to be split in the player handler.
    self.player_from_q = player_from_q
    self.player_to_q = player_to_q

    try:
        self.ser.open()
    except serial.SerialException as e:
        sys.stderr.write('Could not open serial port {}: {}\n'.format(self.ser.name, e))
        return

    self.receive()

  def receive(self):
      while self.ser.is_open:
        try:
          line = int.from_bytes(self.ser.read(1), "big") # Endianness doesn't matter for 1 byte.
          print("Controller got:", line)
          if (line == 255):
            print("Sending back KeepAlive")
            self.ser.write(b'\xff') # Send 255 back.
          elif (line in [1,3,5]):
            self.player_to_q[int(line / 2)].put("PLAY")
          elif (line in [2,4,6]):
            self.player_to_q[int(line / 2)-1].put("STOP")

        except:
          continue


