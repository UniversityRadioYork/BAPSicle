"""
    BAPSicle Server
    Next-gen audio playout server for University Radio York playout,
    based on WebStudio interface.

    Flask Server

    Authors:
        Matthew Stratford
        Michael Grace

    Date:
        October, November 2020
"""
from api_handler import APIHandler
from controllers.mattchbox_usb import MattchBox
import multiprocessing
from multiprocessing.queues import Queue
import time
import player
from typing import Any
import json
from setproctitle import setproctitle

from helpers.os_environment import isBundelled, isMacOS

if not isMacOS():
    # Rip, this doesn't like threading on MacOS.
    import pyttsx3

if isBundelled():
    import build

import config
from typing import Dict, List
from helpers.state_manager import StateManager
from helpers.logging_manager import LoggingManager
from websocket_server import WebsocketServer
from web_server import WebServer
from player_handler import PlayerHandler

setproctitle("server.py")


class BAPSicleServer:
    def __init__(self):

        startServer()

#    def get_flask(self):
#        return app


default_state = {
    "server_version": "",
    "server_build": "",
    "server_name": "URY BAPSicle",
    "host": "localhost",
    "port": 13500,
    "ws_port": 13501,
    "num_channels": 3,
    "serial_port": None,
    "ser_connected": False,
    "myradio_api_key": None,
    "myradio_base_url": "https://ury.org.uk/myradio",
    "myradio_api_url": "https://ury.org.uk/api"
}


channel_to_q: List[Queue] = []
channel_from_q: List[Queue] = []
ui_to_q: List[Queue] = []
websocket_to_q: List[Queue] = []
controller_to_q: List[Queue] = []

channel_p: List[multiprocessing.Process] = []
websockets_server: multiprocessing.Process
controller_handler: multiprocessing.Process
webserver: multiprocessing.Process


def startServer():
    process_title = "startServer"
    setproctitle(process_title)
    # multiprocessing.current_process().name = process_title

    global logger
    global state
    logger = LoggingManager("BAPSicleServer")

    state = StateManager("BAPSicleServer", logger, default_state)
    # TODO: Check these match, if not, trigger any upgrade noticies / welcome
    state.update("server_version", config.VERSION)
    build_commit = "Dev"
    if isBundelled():
        build_commit = build.BUILD
    state.update("server_build", build_commit)

    if isMacOS():
        multiprocessing.set_start_method("spawn", True)
    for channel in range(state.state["num_channels"]):

        channel_to_q.append(multiprocessing.Queue())
        channel_from_q.append(multiprocessing.Queue())
        ui_to_q.append(multiprocessing.Queue())
        websocket_to_q.append(multiprocessing.Queue())
        controller_to_q.append(multiprocessing.Queue())

        # TODO Replace state with individual read-only StateManagers or something nicer?

        channel_p.append(
            multiprocessing.Process(
                target=player.Player,
                args=(channel, channel_to_q[-1], channel_from_q[-1], state)
                # daemon=True
            )
        )
        channel_p[channel].start()

    global api_from_q, api_to_q, api_handler, player_handler, websockets_server, controller_handler  # , webserver
    api_to_q = multiprocessing.Queue()
    api_from_q = multiprocessing.Queue()
    api_handler = multiprocessing.Process(
        target=APIHandler, args=(api_to_q, api_from_q, state)
    )
    api_handler.start()

    player_handler = multiprocessing.Process(
        target=PlayerHandler,
        args=(channel_from_q, websocket_to_q, ui_to_q, controller_to_q),
    )
    player_handler.start()

    # Note, state here will become a copy in the process.
    # It will not update, and callbacks will not work :/
    websockets_server = multiprocessing.Process(
        target=WebsocketServer, args=(channel_to_q, websocket_to_q, state)
    )
    websockets_server.start()

    controller_handler = multiprocessing.Process(
        target=MattchBox, args=(channel_to_q, controller_to_q, state)
    )
    controller_handler.start()

    webserver = multiprocessing.Process(
        target=WebServer, args=(channel_to_q, ui_to_q, api_to_q, api_from_q, state)
    )
    webserver.start()

    # TODO Move this to player or installer.
    if False:
        if not isMacOS():

            # Temporary RIP.

            # Welcome Speech

            text_to_speach = pyttsx3.init()
            text_to_speach.save_to_file(
                """Thank-you for installing BAPSicle - the play-out server from the broadcasting and presenting suite.
            By default, this server is accepting connections on port 13500
            The version of the server service is {}
            Please refer to the documentation included with this application for further assistance.""".format(
                    config.VERSION
                ),
                "dev/welcome.mp3",
            )
            text_to_speach.runAndWait()

            new_item: Dict[str, Any] = {
                "channel_weight": 0,
                "filename": "dev/welcome.mp3",
                "title": "Welcome to BAPSicle",
                "artist": "University Radio York",
            }

            channel_to_q[0].put("ADD:" + json.dumps(new_item))
            channel_to_q[0].put("LOAD:0")
            channel_to_q[0].put("PLAY")

    while True:
        time.sleep(10000)


def stopServer():
    global channel_p, channel_from_q, channel_to_q, websockets_server, controller_handler, webserver
    print("Stopping Controllers")
    if controller_handler:
        controller_handler.terminate()
        controller_handler.join()

    print("Stopping Websockets")
    websocket_to_q[0].put("WEBSOCKET:QUIT")
    if websockets_server:
        websockets_server.join()
        del websockets_server

    print("Stopping server.py")
    for q in channel_to_q:
        q.put("ALL:QUIT")
    for channel in channel_p:
        try:
            channel.join()
        except Exception as e:
            print("*** Ignoring exception:", e)
            pass
        finally:
            del channel
    del channel_from_q
    del channel_to_q
    print("Stopped all players.")

    print("Stopping webserver")

    if webserver:
        webserver.terminate()
        webserver.join()

    print("Stopped webserver")


if __name__ == "__main__":
    raise Exception("BAPSicle is a service. Please run it like one.")
