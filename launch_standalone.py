import multiprocessing
import time

from server import BAPSicleServer

if __name__ == '__main__':
    # On Windows calling this function is necessary.
    # Causes all kinds of loops if not present.
    multiprocessing.freeze_support()
    server = multiprocessing.Process(target=BAPSicleServer).start()
    while True:
        time.sleep(1)
        pass
