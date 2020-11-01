import multiprocessing
import time

from server import BAPSicleServer

def startServer():

    # On Windows calling this function is necessary.
    # Causes all kinds of loops if not present.
    multiprocessing.freeze_support()

    server = multiprocessing.Process(target=BAPSicleServer)
    server.start()

    while True:
        time.sleep(2)
        if server and server.is_alive():
            pass
        else:
            print("Server dead. Exiting.")
            sys.exit(0)

if __name__ == '__main__':
        startServer()