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
import asyncio
from controllers.mattchbox_usb import MattchBox
import copy
import multiprocessing
import queue
import threading
import time
import player
from flask import Flask, render_template, send_from_directory, request, jsonify
from typing import Any, Optional
import json
import setproctitle
import logging

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

setproctitle.setproctitle("BAPSicle - Server")

default_state = {
    "server_version": 0,
    "server_name": "URY BAPSicle",
    "host": "localhost",
    "port": 13500,
    "ws_port": 13501,
    "num_channels": 3
}

logger = None
state = None

class BAPSicleServer():

    def __init__(self):

        process_title = "Server"
        setproctitle.setproctitle(process_title)
        multiprocessing.current_process().name = process_title

        global logger
        global state
        logger = LoggingManager("BAPSicleServer")

        state = StateManager("BAPSicleServer", logger, default_state)
        state.update("server_version", config.VERSION)

        asyncio.get_event_loop().run_until_complete(startServer())
        asyncio.get_event_loop().run_forever()

    def __del__(self):
        stopServer()

class PlayerHandler():
    def __init__(self,channel_from_q, websocket_to_q, ui_to_q):
        while True:
            for channel in range(len(channel_from_q)):
                try:
                    message = channel_from_q[channel].get_nowait()
                    websocket_to_q[channel].put(message)
                    #print("Player Handler saw:", message.split(":")[0])
                    ui_to_q[channel].put(message)
                except:
                    pass
            time.sleep(0.1)


app = Flask(__name__, static_url_path='')

log = logging.getLogger('werkzeug')
log.disabled = True
app.logger.disabled = True

channel_to_q: List[queue.Queue] = []
channel_from_q: List[queue.Queue] = []
ui_to_q: List[queue.Queue] = []
websocket_to_q: List[queue.Queue] = []
channel_p = []

stopping = False


# General Endpoints

@app.errorhandler(404)
def page_not_found(e: Any):
    data = {
        'ui_page': "404",
        "ui_title": "404"
    }
    return render_template('404.html', data=data), 404


@app.route("/")
def ui_index():
    data = {
        'ui_page': "index",
        "ui_title": "",
        "server_version": config.VERSION,
        "server_name": state.state["server_name"]
    }
    return render_template('index.html', data=data)


@app.route("/config")
def ui_config():
    channel_states = []
    for i in range(state.state["num_channels"]):
        channel_states.append(status(i))

    outputs = DeviceManager.getOutputs()

    data = {
        'channels': channel_states,
        'outputs': outputs,
        'ui_page': "config",
        "ui_title": "Config"
    }
    return render_template('config.html', data=data)


@app.route("/status")
def ui_status():
    channel_states = []
    for i in range(state.state["num_channels"]):
        channel_states.append(status(i))

    data = {
        'channels': channel_states,
        'ui_page': "status",
        "ui_title": "Status"
    }
    return render_template('status.html', data=data)


@app.route("/status-json")
def json_status():
    channel_states = []
    for i in range(state.state["num_channels"]):
        channel_states.append(status(i))
    return {
        "server": state.state,
        "channels": channel_states
    }


@app.route("/server")
def server_config():
    data = {
        "ui_page": "server",
        "ui_title": "Server Config",
        "state": state.state
    }
    return render_template("server.html", data=data)


@app.route("/restart", methods=["POST"])
def restart_server():
    state.update("server_name", request.form["name"])
    state.update("host", request.form["host"])
    state.update("port", int(request.form["port"]))
    state.update("num_channels", int(request.form["channels"]))
    state.update("ws_port", int(request.form["ws_port"]))
    stopServer(restart=True)
    startServer()

# Channel Audio Options


@app.route("/player/<int:channel>/play")
def play(channel: int):

    channel_to_q[channel].put("PLAY")

    return ui_status()


@app.route("/player/<int:channel>/pause")
def pause(channel: int):

    channel_to_q[channel].put("PAUSE")

    return ui_status()


@app.route("/player/<int:channel>/unpause")
def unPause(channel: int):

    channel_to_q[channel].put("UNPAUSE")

    return ui_status()


@app.route("/player/<int:channel>/stop")
def stop(channel: int):

    channel_to_q[channel].put("STOP")

    return ui_status()


@app.route("/player/<int:channel>/seek/<float:pos>")
def seek(channel: int, pos: float):

    channel_to_q[channel].put("SEEK:" + str(pos))

    return ui_status()


@app.route("/player/<int:channel>/output/<name>")
def output(channel: int, name: Optional[str]):
    channel_to_q[channel].put("OUTPUT:" + str(name))
    return ui_status()


@app.route("/player/<int:channel>/autoadvance/<int:state>")
def autoadvance(channel: int, state: int):
    channel_to_q[channel].put("AUTOADVANCE:" + str(state))
    return ui_status()


@app.route("/player/<int:channel>/repeat/<state>")
def repeat(channel: int, state: str):
    channel_to_q[channel].put("REPEAT:" + state.upper())
    return ui_status()


@app.route("/player/<int:channel>/playonload/<int:state>")
def playonload(channel: int, state: int):
    channel_to_q[channel].put("PLAYONLOAD:" + str(state))
    return ui_status()

# Channel Items


@app.route("/player/<int:channel>/load/<int:channel_weight>")
def load(channel: int, channel_weight: int):
    channel_to_q[channel].put("LOAD:" + str(channel_weight))
    return ui_status()


@app.route("/player/<int:channel>/unload")
def unload(channel: int):

    channel_to_q[channel].put("UNLOAD")

    return ui_status()


@app.route("/player/<int:channel>/add", methods=["POST"])
def add_to_plan(channel: int):
    new_item: Dict[str, Any] = {
        "channel_weight": int(request.form["channel_weight"]),
        "filename": request.form["filename"],
        "title":  request.form["title"],
        "artist":  request.form["artist"],
    }

    channel_to_q[channel].put("ADD:" + json.dumps(new_item))

    return new_item

#@app.route("/player/<int:channel>/move/<int:channel_weight>/<int:position>")
#def move_plan(channel: int, channel_weight: int, position: int):
#    channel_to_q[channel].put("MOVE:" + json.dumps({"channel_weight": channel_weight, "position": position}))#

    # TODO Return
#    return True

#@app.route("/player/<int:channel>/remove/<int:channel_weight>")
def remove_plan(channel: int, channel_weight: int):
    channel_to_q[channel].put("REMOVE:" + str(channel_weight))

    # TODO Return
    return True


#@app.route("/player/<int:channel>/clear")
def clear_channel_plan(channel: int):
    channel_to_q[channel].put("CLEAR")

    # TODO Return
    return True

# General Channel Endpoints


@app.route("/player/<int:channel>/status")
def channel_json(channel: int):
    try:
        return jsonify(status(channel))
    except:
        return status(channel)

@app.route("/plan/load/<int:timeslotid>")
def load_showplan(timeslotid: int):

    for channel in channel_to_q:
        channel.put("GET_PLAN:" + str(timeslotid))

    return ui_status()

def status(channel: int):
    while (not ui_to_q[channel].empty()):
        ui_to_q[channel].get() # Just waste any previous status responses.

    channel_to_q[channel].put("STATUS")
    i = 0
    while True:
        try:
            response = ui_to_q[channel].get_nowait()
            if response.startswith("STATUS:"):
                response = response[7:]
                response = response[response.index(":")+1:]
                try:
                    response = json.loads(response)
                except Exception as e:
                    raise e
                return response

        except queue.Empty:
            pass

        time.sleep(0.1)


@app.route("/quit")
def quit():
    stopServer()
    return "Shutting down..."


@app.route("/player/all/stop")
def all_stop():
    for channel in channel_to_q:
        channel.put("STOP")
    return ui_status()


@app.route("/player/all/clear")
def clear_all_channels():
    for channel in channel_to_q:
        channel.put("CLEAR")
    return ui_status()


@app.route('/static/<path:path>')
def send_static(path: str):
    return send_from_directory('ui-static', path)


@app.route("/logs")
def list_logs():
    data = {
        "ui_page": "loglist",
        "ui_title": "Logs",
        "logs": ["BAPSicleServer"] + ["channel{}".format(x) for x in range(state.state["num_channels"])]
    }
    return render_template("loglist.html", data=data)


@app.route("/logs/<path:path>")
def send_logs(path):
    l = open("logs/{}.log".format(path))
    data = {
        "logs": l.read().splitlines(),
        'ui_page': "log",
        "ui_title": "Logs - {}".format(path)
    }
    l.close()
    return render_template('log.html', data=data)


async def startServer():
    process_title="startServer"
    threading.current_thread().name = process_title

    if isMacOS():
        multiprocessing.set_start_method("spawn", True)
    for channel in range(state.state["num_channels"]):

        channel_to_q.append(multiprocessing.Queue())
        channel_from_q.append(multiprocessing.Queue())
        ui_to_q.append(multiprocessing.Queue())
        websocket_to_q.append(multiprocessing.Manager().Queue())
        channel_p.append(
            multiprocessing.Process(
                target=player.Player,
                args=(channel, channel_to_q[-1], channel_from_q[-1]),
                #daemon=True
            )
        )
        channel_p[channel].start()




    player_handler = multiprocessing.Process(target=PlayerHandler, args=(channel_from_q, websocket_to_q, ui_to_q))
    player_handler.start()

    websockets_server = multiprocessing.Process(target=WebsocketServer, args=(channel_to_q, channel_from_q, state))
    websockets_server.start()


    controller_handler = multiprocessing.Process(target=MattchBox, args=(channel_to_q, channel_from_q))
    controller_handler.start()

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
            "dev/welcome.mp3"
        )
        text_to_speach.runAndWait()

    new_item: Dict[str,Any] = {
        "channel_weight": 0,
        "filename": "dev/welcome.mp3",
        "title":  "Welcome to BAPSicle",
        "artist":  "University Radio York",
    }

    #channel_to_q[0].put("ADD:" + json.dumps(new_item))
    # channel_to_q[0].put("LOAD:0")
    # channel_to_q[0].put("PLAY")

    # Don't use reloader, it causes Nested Processes!
    app.run(host=state.state["host"], port=state.state["port"], debug=True, use_reloader=False)

async def player_message_handler():
    print("Handling")
    pass

def stopServer(restart=False):
    global channel_p
    global channel_from_q
    global channel_to_q
    print("Stopping server.py")
    for q in channel_to_q:
        q.put("QUIT")
    for player in channel_p:
        try:
            player.join()
        except:
            pass
        finally:
            channel_p = []
            channel_from_q = []
            channel_to_q = []
    print("Stopped all players.")
    global stopping
    if stopping == False:
        stopping = True
        shutdown = request.environ.get('werkzeug.server.shutdown')
        if shutdown is None:
            print("Shutting down Server.")

        else:
            print("Shutting down Flask.")
            if not restart:
                shutdown()


if __name__ == "__main__":
    print("BAPSicle is a service. Please run it like one.")
