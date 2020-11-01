import multiprocessing
import time
import sys
import webbrowser

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
    if len(sys.argv) > 1:
        # We got an argument! It's probably Platypus's UI.
        try:
            if (sys.argv[1]) == "Start Server":
                print("NOTIFICATION:Welcome to BAPSicle!")
                webbrowser.open("http://localhost:13500/")
                startServer()
            if (sys.argv[1] == "Status"):
                webbrowser.open("http://localhost:13500/status")
            if (sys.argv[1] == "Config"):
                webbrowser.open("http://localhost:13500/config")
            if (sys.argv[1] == "Logs"):
                webbrowser.open("http://localhost:13500/logs")
        except Exception as e:
            print("ALERT:BAPSicle failed with exception:\n", e)

        sys.exit(0)
    else:
        startServer()
