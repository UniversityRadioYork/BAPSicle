from server import BAPSicleServer
from pathlib import Path
from SMWinservice import SMWinservice
import time
import multiprocessing

import sys
sys.path.append("..\\")


class BAPScileAsAService(SMWinservice):
    _svc_name_ = "BAPSicle"
    _svc_display_name_ = "BAPSicle Server"
    _svc_description_ = "BAPS development has been frozen for a while, but this new spike of progress is dripping."

    def start(self):
        self.isrunning = True
        self.server = multiprocessing.Process(target=BAPSicleServer).start()

    def stop(self):
        print("stopping")
        self.isrunning = False
        try:
            self.server.terminate()
            self.server.join()
        except:
            pass

    def main(self):
        while self.isrunning:
            time.sleep(1)
            print("BAPSicle is running.")


if __name__ == '__main__':
    BAPScileAsAService.parse_command_line()
