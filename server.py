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
import multiprocessing
from multiprocessing.queues import Queue
import time
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
from controllers.mattchbox_usb import MattchBox
from helpers.the_terminator import Terminator
import player

setproctitle("server.py")


class BAPSicleServer:

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

    player_to_q: List[Queue] = []
    player_from_q: List[Queue] = []
    ui_to_q: List[Queue] = []
    websocket_to_q: List[Queue] = []
    controller_to_q: List[Queue] = []
    api_from_q: Queue
    api_to_q: Queue

    player: List[multiprocessing.Process] = []
    websockets_server: multiprocessing.Process
    controller_handler: multiprocessing.Process
    player_handler: multiprocessing.Process
    webserver: multiprocessing.Process

    def __init__(self):

        self.startServer()

        terminator = Terminator()
        while not terminator.terminate:
            time.sleep(1)

        self.stopServer()

    def startServer(self):
        if isMacOS():
            multiprocessing.set_start_method("spawn", True)

        process_title = "startServer"
        setproctitle(process_title)
        # multiprocessing.current_process().name = process_title

        self.logger = LoggingManager("BAPSicleServer")

        self.state = StateManager("BAPSicleServer", self.logger, self.default_state)

        build_commit = "Dev"
        if isBundelled():
            build_commit = build.BUILD

        print("Launching BAPSicle...")

        # TODO: Check these match, if not, trigger any upgrade noticies / welcome
        self.state.update("server_version", config.VERSION)
        self.state.update("server_build", build_commit)

        for channel in range(self.state.state["num_channels"]):

            self.player_to_q.append(multiprocessing.Queue())
            self.player_from_q.append(multiprocessing.Queue())
            self.ui_to_q.append(multiprocessing.Queue())
            self.websocket_to_q.append(multiprocessing.Queue())
            self.controller_to_q.append(multiprocessing.Queue())

            # TODO Replace state with individual read-only StateManagers or something nicer?

            self.player.append(
                multiprocessing.Process(
                    target=player.Player,
                    args=(channel, self.player_to_q[-1], self.player_from_q[-1], self.state)
                )
            )
            self.player[channel].start()

        self.player_handler = multiprocessing.Process(
            target=PlayerHandler,
            args=(self.player_from_q, self.websocket_to_q, self.ui_to_q, self.controller_to_q),
        )
        self.player_handler.start()

        # Note, state here will become a copy in the process.
        # It will not update, and callbacks will not work :/
        self.websockets_server = multiprocessing.Process(
            target=WebsocketServer, args=(self.player_to_q, self.websocket_to_q, self.state)
        )
        self.websockets_server.start()

        self.controller_handler = multiprocessing.Process(
            target=MattchBox, args=(self.player_to_q, self.controller_to_q, self.state)
        )
        self.controller_handler.start()

        self.webserver = multiprocessing.Process(
            target=WebServer, args=(self.player_to_q, self.ui_to_q, self.state)
        )
        self.webserver.start()

        print("Welcome to BAPSicle Server version: {}, build: {}.".format(config.VERSION, build_commit))
        print("The Server UI is available at http://{}:{}".format(self.state.state["host"], self.state.state["port"]))

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

                self.player_to_q[0].put("ADD:" + json.dumps(new_item))
                self.player_to_q[0].put("LOAD:0")
                self.player_to_q[0].put("PLAY")

    def stopServer(self):
        print("Stopping BASPicle Server.")

        print("Stopping Websocket Server")
        self.websocket_to_q[0].put("WEBSOCKET:QUIT")
        if self.websockets_server:
            self.websockets_server.join()

        print("Stopping Players")
        for q in self.player_to_q:
            q.put("ALL:QUIT")

        for player in self.player:
            player.join()

        print("Stopping Web Server")
        if self.webserver:
            self.webserver.terminate()
            self.webserver.join()

        print("Stopping Player Handler")
        if self.player_handler:
            self.player_handler.terminate()
            self.player_handler.join()

        print("Stopping Controllers")
        if self.controller_handler:
            self.controller_handler.terminate()
            self.controller_handler.join()


if __name__ == "__main__":
    raise Exception("BAPSicle is a service. Please run it like one.")
