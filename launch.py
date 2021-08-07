#!/usr/bin/env python3
import multiprocessing
import time
import sys
from typing import Any
import webbrowser
from setproctitle import setproctitle

from helpers.the_terminator import Terminator


def startServer(notifications=False):
    # Only spend the time importing the Server if we want to start the server. Speeds up web browser opens.
    from server import BAPSicleServer

    #server = multiprocessing.Process(target=BAPSicleServer)
    #server.start()

    sent_start_notif = False

    terminator = Terminator()
    if notifications and not sent_start_notif:
        print("NOTIFICATION:Welcome to BAPSicle!")
        sent_start_notif = True
    while not terminator.terminate:
        server = BAPSicleServer()



    print("Server dead. Exiting.")
    if notifications:
        print("NOTIFICATION:BAPSicle Server Stopped!")
        sys.exit(0)

def printer(msg: Any):
    print("LAUNCHER:{}".format(msg))


if __name__ == "__main__":
    # On Windows, calling this function is necessary.
    # Causes all kinds of loops if not present.
    # IT HAS TO BE RIGHT HERE, AT THE TOP OF __MAIN__
    # NOT INSIDE AN IF STATEMENT. RIGHT. HERE.
    # If it's not here, multiprocessing just doesn't run in the package.
    # Freeze support refers to being packaged with Pyinstaller.
    multiprocessing.freeze_support()
    setproctitle("BAPSicle Launcher")
    if len(sys.argv) > 1:
        # We got an argument! It's probably Platypus's UI.
        try:
            if (sys.argv[1]) == "Start Server":
                print("NOTIFICATION:BAPSicle is starting, please wait...")
                webbrowser.open("http://localhost:13500/")
                startServer(notifications=True)
            if sys.argv[1] == "Server":
                webbrowser.open("http://localhost:13500/")
            if sys.argv[1] == "Presenter":
                webbrowser.open("http://localhost:13500/presenter/")
        except Exception as e:
            print("ALERT:BAPSicle failed with exception of type {}:\n{}".format(type(e).__name__, str(e)))
            sys.exit(1)

        sys.exit(0)
    else:
        startServer()
