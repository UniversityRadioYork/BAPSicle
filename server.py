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
import queue
import time
import player
from flask import Flask, render_template, send_from_directory, request, jsonify, abort
from flask_cors import CORS
from typing import Any, Optional
import json
from setproctitle import setproctitle
import logging

from player_handler import PlayerHandler

from helpers.os_environment import isMacOS
from helpers.device_manager import DeviceManager

if not isMacOS():
    # Rip, this doesn't like threading on MacOS.
    import pyttsx3

import config
from typing import Dict, List
from helpers.state_manager import StateManager
from helpers.logging_manager import LoggingManager
from websocket_server import WebsocketServer

setproctitle("BAPSicleServer.py")


class BAPSicleServer:
    def __init__(self):

        startServer()

    def __del__(self):
        stopServer()

    def get_flask(self):
        return app


default_state = {
    "server_version": 0,
    "server_name": "URY BAPSicle",
    "host": "localhost",
    "port": 13500,
    "ws_port": 13501,
    "num_channels": 3,
    "ser_port": None,
    "ser_connected": False,
}


app = Flask(__name__, static_url_path="")


logger: LoggingManager
state: StateManager

api_from_q: queue.Queue
api_to_q: queue.Queue

channel_to_q: List[queue.Queue] = []
channel_from_q: List[queue.Queue] = []
ui_to_q: List[queue.Queue] = []
websocket_to_q: List[queue.Queue] = []
controller_to_q: List[queue.Queue] = []

channel_p: List[multiprocessing.Process] = []
websockets_server: multiprocessing.Process
controller_handler: multiprocessing.Process
webserver: multiprocessing.Process

# General Endpoints


@app.errorhandler(404)
def page_not_found(e: Any):
    data = {"ui_page": "404", "ui_title": "404"}
    return render_template("404.html", data=data), 404


@app.route("/")
def ui_index():
    data = {
        "ui_page": "index",
        "ui_title": "",
        "server_version": config.VERSION,
        "server_name": state.state["server_name"],
    }
    return render_template("index.html", data=data)


@app.route("/config")
def ui_config():
    channel_states = []
    for i in range(state.state["num_channels"]):
        channel_states.append(status(i))

    outputs = DeviceManager.getAudioOutputs()

    data = {
        "channels": channel_states,
        "outputs": outputs,
        "ui_page": "config",
        "ui_title": "Config",
    }
    return render_template("config.html", data=data)


@app.route("/status")
def ui_status():
    channel_states = []
    for i in range(state.state["num_channels"]):
        channel_states.append(status(i))

    data = {"channels": channel_states, "ui_page": "status", "ui_title": "Status"}
    return render_template("status.html", data=data)


@app.route("/status-json")
def json_status():
    channel_states = []
    for i in range(state.state["num_channels"]):
        channel_states.append(status(i))
    return {"server": state.state, "channels": channel_states}


@app.route("/server")
def server_config():
    data = {
        "ui_page": "server",
        "ui_title": "Server Config",
        "state": state.state,
        "ser_ports": DeviceManager.getSerialPorts(),
    }
    return render_template("server.html", data=data)


@app.route("/server/update", methods=["POST"])
def update_server():
    state.update("server_name", request.form["name"])
    state.update("host", request.form["host"])
    state.update("port", int(request.form["port"]))
    state.update("num_channels", int(request.form["channels"]))
    state.update("ws_port", int(request.form["ws_port"]))
    state.update("serial_port", request.form["serial_port"])
    # stopServer()
    return server_config()


# Get audio for UI to generate waveforms.


@app.route("/audiofile/<type>/<int:id>")
def audio_file(type: str, id: int):
    if type not in ["managed", "track"]:
        abort(404)
    return send_from_directory("music-tmp", type + "-" + str(id) + ".mp3")


# Channel Audio Options


@app.route("/player/<int:channel>/play")
def play(channel: int):

    channel_to_q[channel].put("UI:PLAY")

    return ui_status()


@app.route("/player/<int:channel>/pause")
def pause(channel: int):

    channel_to_q[channel].put("UI:PAUSE")

    return ui_status()


@app.route("/player/<int:channel>/unpause")
def unPause(channel: int):

    channel_to_q[channel].put("UI:UNPAUSE")

    return ui_status()


@app.route("/player/<int:channel>/stop")
def stop(channel: int):

    channel_to_q[channel].put("UI:STOP")

    return ui_status()


@app.route("/player/<int:channel>/seek/<float:pos>")
def seek(channel: int, pos: float):

    channel_to_q[channel].put("UI:SEEK:" + str(pos))

    return ui_status()


@app.route("/player/<int:channel>/output/<name>")
def output(channel: int, name: Optional[str]):
    channel_to_q[channel].put("UI:OUTPUT:" + str(name))
    return ui_config()


@app.route("/player/<int:channel>/autoadvance/<int:state>")
def autoadvance(channel: int, state: int):
    channel_to_q[channel].put("UI:AUTOADVANCE:" + str(state))
    return ui_status()


@app.route("/player/<int:channel>/repeat/<state>")
def repeat(channel: int, state: str):
    channel_to_q[channel].put("UI:REPEAT:" + state.upper())
    return ui_status()


@app.route("/player/<int:channel>/playonload/<int:state>")
def playonload(channel: int, state: int):
    channel_to_q[channel].put("UI:PLAYONLOAD:" + str(state))
    return ui_status()


# Channel Items


@app.route("/player/<int:channel>/load/<int:channel_weight>")
def load(channel: int, channel_weight: int):
    channel_to_q[channel].put("UI:LOAD:" + str(channel_weight))
    return ui_status()


@app.route("/player/<int:channel>/unload")
def unload(channel: int):

    channel_to_q[channel].put("UI:UNLOAD")

    return ui_status()


@app.route("/player/<int:channel>/add", methods=["POST"])
def add_to_plan(channel: int):
    new_item: Dict[str, Any] = {
        "channel_weight": int(request.form["channel_weight"]),
        "filename": request.form["filename"],
        "title": request.form["title"],
        "artist": request.form["artist"],
    }

    channel_to_q[channel].put("UI:ADD:" + json.dumps(new_item))

    return new_item


# @app.route("/player/<int:channel>/remove/<int:channel_weight>")
def remove_plan(channel: int, channel_weight: int):
    channel_to_q[channel].put("UI:REMOVE:" + str(channel_weight))

    # TODO Return
    return True


# @app.route("/player/<int:channel>/clear")
def clear_channel_plan(channel: int):
    channel_to_q[channel].put("UI:CLEAR")

    # TODO Return
    return True


# General Channel Endpoints


@app.route("/player/<int:channel>/status")
def channel_json(channel: int):
    try:
        return jsonify(status(channel))
    except:
        return status(channel)


@app.route("/plan/list")
def list_showplans():
    while not api_from_q.empty():
        api_from_q.get()  # Just waste any previous status responses.

    api_to_q.put("LIST_PLANS")

    while True:
        try:
            response = api_from_q.get_nowait()
            if response.startswith("LIST_PLANS:"):
                response = response[response.index(":") + 1 :]
                return response

        except queue.Empty:
            pass

        time.sleep(0.02)


@app.route("/library/search/<type>")
def search_library(type: str):

    if type not in ["managed", "track"]:
        abort(404)

    while not api_from_q.empty():
        api_from_q.get()  # Just waste any previous status responses.

    params = json.dumps(
        {"title": request.args.get("title"), "artist": request.args.get("artist")}
    )
    api_to_q.put("SEARCH_TRACK:{}".format(params))

    while True:
        try:
            response = api_from_q.get_nowait()
            if response.startswith("SEARCH_TRACK:"):
                response = response.split(":", 1)[1]
                return response

        except queue.Empty:
            pass

        time.sleep(0.02)


@app.route("/library/playlists/<type>")
def get_playlists(type: str):

    if type not in ["music", "aux"]:
        abort(401)

    while not api_from_q.empty():
        api_from_q.get()  # Just waste any previous status responses.

    command = "LIST_PLAYLIST_{}".format(type.upper())
    api_to_q.put(command)

    while True:
        try:
            response = api_from_q.get_nowait()
            if response.startswith(command):
                response = response.split(":", 1)[1]
                return response

        except queue.Empty:
            pass

        time.sleep(0.02)


@app.route("/library/playlist/<type>/<library_id>")
def get_playlist(type: str, library_id: str):

    if type not in ["music", "aux"]:
        abort(401)

    while not api_from_q.empty():
        api_from_q.get()  # Just waste any previous status responses.

    command = "GET_PLAYLIST_{}:{}".format(type.upper(), library_id)
    api_to_q.put(command)

    while True:
        try:
            response = api_from_q.get_nowait()
            if response.startswith(command):
                response = response[len(command) + 1 :]
                if response == "null":
                    abort(401)
                return response

        except queue.Empty:
            pass

        time.sleep(0.02)


@app.route("/plan/load/<int:timeslotid>")
def load_showplan(timeslotid: int):

    for channel in channel_to_q:
        channel.put("UI:GET_PLAN:" + str(timeslotid))

    return ui_status()


def status(channel: int):
    while not ui_to_q[channel].empty():
        ui_to_q[channel].get()  # Just waste any previous status responses.

    channel_to_q[channel].put("UI:STATUS")
    retries = 0
    while retries < 40:
        try:
            response = ui_to_q[channel].get_nowait()
            if response.startswith("UI:STATUS:"):
                response = response.split(":", 2)[2]
                # TODO: Handle OKAY / FAIL
                response = response[response.index(":") + 1 :]
                try:
                    response = json.loads(response)
                except Exception as e:
                    raise e
                return response

        except queue.Empty:
            pass

        retries += 1

        time.sleep(0.02)


@app.route("/quit")
def quit():
    stopServer()
    return "Shutting down..."


@app.route("/player/all/stop")
def all_stop():
    for channel in channel_to_q:
        channel.put("UI:STOP")
    return ui_status()


@app.route("/player/all/clear")
def clear_all_channels():
    for channel in channel_to_q:
        channel.put("UI:CLEAR")
    return ui_status()


@app.route("/logs")
def list_logs():
    data = {
        "ui_page": "loglist",
        "ui_title": "Logs",
        "logs": ["BAPSicleServer"]
        + ["channel{}".format(x) for x in range(state.state["num_channels"])],
    }
    return render_template("loglist.html", data=data)


@app.route("/logs/<path:path>")
def send_logs(path):
    l = open("logs/{}.log".format(path))
    data = {
        "logs": l.read().splitlines(),
        "ui_page": "log",
        "ui_title": "Logs - {}".format(path),
    }
    l.close()
    return render_template("log.html", data=data)


@app.route("/favicon.ico")
def serve_favicon():
    return send_from_directory("ui-static", "favicon.ico")


@app.route("/static/<path:path>")
def serve_static(path: str):
    return send_from_directory("ui-static", path)


def startServer():
    process_title = "startServer"
    setproctitle(process_title)
    # multiprocessing.current_process().name = process_title

    global logger
    global state
    logger = LoggingManager("BAPSicleServer")

    state = StateManager("BAPSicleServer", logger, default_state)
    state.update("server_version", config.VERSION)

    if isMacOS():
        multiprocessing.set_start_method("spawn", True)
    for channel in range(state.state["num_channels"]):

        channel_to_q.append(multiprocessing.Queue())
        channel_from_q.append(multiprocessing.Queue())
        ui_to_q.append(multiprocessing.Queue())
        websocket_to_q.append(multiprocessing.Queue())
        controller_to_q.append(multiprocessing.Queue())
        channel_p.append(
            multiprocessing.Process(
                target=player.Player,
                args=(channel, channel_to_q[-1], channel_from_q[-1])
                # daemon=True
            )
        )
        channel_p[channel].start()

    global api_from_q, api_to_q, api_handler, player_handler, websockets_server, controller_handler
    api_to_q = multiprocessing.Queue()
    api_from_q = multiprocessing.Queue()
    api_handler = multiprocessing.Process(
        target=APIHandler, args=(api_to_q, api_from_q)
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

    # Don't use reloader, it causes Nested Processes!
    def runWebServer():
        process_title = "WebServer"
        setproctitle(process_title)
        CORS(app, supports_credentials=True)  # Allow ALL CORS!!!

        log = logging.getLogger("werkzeug")
        log.disabled = True

        app.logger.disabled = True
        app.run(
            host=state.state["host"],
            port=state.state["port"],
            debug=True,
            use_reloader=False,
        )

    global webserver
    webserver = multiprocessing.Process(runWebServer())
    webserver.start()


def stopServer():
    global channel_p, channel_from_q, channel_to_q, websockets_server, webserver, controller_handler
    print("Stopping Controllers")
    controller_handler.terminate()
    controller_handler.join()

    print("Stopping Websockets")
    websocket_to_q[0].put("WEBSOCKET:QUIT")
    websockets_server.join()
    del websockets_server

    print("Stopping server.py")
    for q in channel_to_q:
        q.put("QUIT")
    for player in channel_p:
        try:
            player.join()
        except Exception as e:
            print("*** Ignoring exception:", e)
            pass
        finally:
            del player
    del channel_from_q
    del channel_to_q
    print("Stopped all players.")

    print("Stopping webserver")
    global webserver
    webserver.terminate()
    webserver.join()

    print("Stopped webserver")


if __name__ == "__main__":
    raise Exception("BAPSicle is a service. Please run it like one.")
