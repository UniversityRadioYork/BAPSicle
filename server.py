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
from typing import Any, Optional
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
    websockets_server: Optional[multiprocessing.Process] = None
    controller_handler: Optional[multiprocessing.Process] = None
    player_handler: Optional[multiprocessing.Process] = None
    webserver: Optional[multiprocessing.Process] = None

    def __init__(self):

        self.startServer()

        self.check_processes()

        self.stopServer()

    def check_processes(self):

        terminator = Terminator()
        log_function = self.logger.log.info
        while not terminator.terminate:

            # Note, state here will become a copy in the process.
            # callbacks will not passthrough :/

            for channel in range(self.state.state["num_channels"]):
                if not self.player[channel] or not self.player[channel].is_alive():
                    log_function("Player {} not running, (re)starting.".format(channel))
                    self.player[channel] = multiprocessing.Process(
                        target=player.Player,
                        args=(channel, self.player_to_q[channel], self.player_from_q[channel], self.state)
                    )
                    self.player[channel].start()

            if not self.player_handler or not self.player_handler.is_alive():
                log_function("Player Handler not running, (re)starting.")
                self.player_handler = multiprocessing.Process(
                    target=PlayerHandler,
                    args=(self.player_from_q, self.websocket_to_q, self.ui_to_q, self.controller_to_q),
                )
                self.player_handler.start()

            if not self.websockets_server or not self.websockets_server.is_alive():
                log_function("Websocket Server not running, (re)starting.")
                self.websockets_server = multiprocessing.Process(
                    target=WebsocketServer, args=(self.player_to_q, self.websocket_to_q, self.state)
                )
                self.websockets_server.start()

            if not self.webserver or not self.webserver.is_alive():
                log_function("Webserver not running, (re)starting.")
                self.webserver = multiprocessing.Process(
                    target=WebServer, args=(self.player_to_q, self.ui_to_q, self.state)
                )
                self.webserver.start()

            if not self.controller_handler or not self.controller_handler.is_alive():
                log_function("Controller Handler not running, (re)starting.")
                self.controller_handler = multiprocessing.Process(
                    target=MattchBox, args=(self.player_to_q, self.controller_to_q, self.state)
                )
                self.controller_handler.start()

            # After first starting processes, switch logger to error, since any future starts will have been failures.
            log_function = self.logger.log.error
            time.sleep(1)

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

        channel_count = self.state.state["num_channels"]
        self.player = [None] * channel_count

        for channel in range(self.state.state["num_channels"]):

            self.player_to_q.append(multiprocessing.Queue())
            self.player_from_q.append(multiprocessing.Queue())
            self.ui_to_q.append(multiprocessing.Queue())
            self.websocket_to_q.append(multiprocessing.Queue())
            self.controller_to_q.append(multiprocessing.Queue())

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
