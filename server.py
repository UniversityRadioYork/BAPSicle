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
import player
from flask import Flask, render_template, send_from_directory, request
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

setproctitle.setproctitle("BAPSicle - Server")

default_state = {
    "server_version": 0,
    "server_name": "URY BAPSicle",
    "host": "localhost",
    "port": 13500,
    "num_channels": 3
}


class BAPSicleServer():

    def __init__(self):

        process_title = "Server"
        setproctitle.setproctitle(process_title)
        multiprocessing.current_process().name = process_title

        startServer()

    def __del__(self):
        stopServer()


logger = LoggingManager("BAPSicleServer")

state = StateManager("BAPSicleServer", logger, default_state)
state.update("server_version", config.VERSION)

app = Flask(__name__, static_url_path='')

log = logging.getLogger('werkzeug')
log.disabled = True
app.logger.disabled = True

channel_to_q = []
channel_from_q = []
channel_p = []

stopping = False


# General Endpoints

@app.errorhandler(404)
def page_not_found(e):
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
    for i in range(3):
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

# Channel Audio Options


@app.route("/player/<int:channel>/play")
def play(channel):

    channel_to_q[channel].put("PLAY")

    return ui_status()


@app.route("/player/<int:channel>/pause")
def pause(channel):

    channel_to_q[channel].put("PAUSE")

    return ui_status()


@app.route("/player/<int:channel>/unpause")
def unPause(channel):

    channel_to_q[channel].put("UNPAUSE")

    return ui_status()


@app.route("/player/<int:channel>/stop")
def stop(channel):

    channel_to_q[channel].put("STOP")

    return ui_status()


@app.route("/player/<int:channel>/seek/<int:pos>")
def seek(channel, pos):

    channel_to_q[channel].put("SEEK:" + str(pos))

    return ui_status()


@app.route("/player/<int:channel>/output/<name>")
def output(channel, name):
    channel_to_q[channel].put("OUTPUT:" + name)
    return ui_status()


@app.route("/player/<int:channel>/autoadvance/<int:state>")
def autoadvance(channel: int, state: int):
    channel_to_q[channel].put("AUTOADVANCE:" + str(state))
    return ui_status()


@app.route("/player/<int:channel>/repeat/<state>")
def repeat(channel: int, state):
    channel_to_q[channel].put("REPEAT:" + state.upper())
    return ui_status()


@app.route("/player/<int:channel>/playonload/<int:state>")
def playonload(channel: int, state: int):
    channel_to_q[channel].put("PLAYONLOAD:" + str(state))
    return ui_status()

# Channel Items


@app.route("/player/<int:channel>/load/<int:timeslotitemid>")
def load(channel: int, timeslotitemid: int):
    channel_to_q[channel].put("LOAD:" + str(timeslotitemid))
    return ui_status()


@app.route("/player/<int:channel>/unload")
def unload(channel):

    channel_to_q[channel].put("UNLOAD")

    return ui_status()


@app.route("/player/<int:channel>/add", methods=["POST"])
def add_to_plan(channel: int):
    new_item: Dict[str, any] = {
        "timeslotitemid": int(request.form["timeslotitemid"]),
        "filename": request.form["filename"],
        "title":  request.form["title"],
        "artist":  request.form["artist"],
    }

    channel_to_q[channel].put("ADD:" + json.dumps(new_item))

    return new_item


@app.route("/player/<int:channel>/move/<int:timeslotitemid>/<int:position>")
def move_plan(channel: int, timeslotitemid: int, position: int):
    channel_to_q[channel].put("MOVE:" + json.dumps({"timeslotitemid": timeslotitemid, "position": position}))

    # TODO Return
    return True


@app.route("/player/<int:channel>/remove/<int:timeslotitemid>")
def remove_plan(channel: int, timeslotitemid: int):
    channel_to_q[channel].put("REMOVE:" + timeslotitemid)

    # TODO Return
    return True


@app.route("/player/<int:channel>/clear")
def clear_channel_plan(channel: int):
    channel_to_q[channel].put("CLEAR")

    # TODO Return
    return True

# General Channel Endpoints


@app.route("/player/<int:channel>/status")
def status(channel):

    channel_to_q[channel].put("STATUS")
    while True:
        response = channel_from_q[channel].get()
        if response.startswith("STATUS:"):
            response = response[7:]
            response = response[response.index(":")+1:]
            try:
                response = json.loads(response)
            except:
                pass

            return response


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
def send_static(path):
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


def startServer():
    if isMacOS():
        multiprocessing.set_start_method("spawn", True)
    for channel in range(state.state["num_channels"]):

        channel_to_q.append(multiprocessing.Queue())
        channel_from_q.append(multiprocessing.Queue())
        channel_p.append(
            multiprocessing.Process(
                target=player.Player,
                args=(channel, channel_to_q[-1], channel_from_q[-1]),
                daemon=True
            )
        )
        channel_p[channel].start()

    if not isMacOS():

        # Temporary RIP.

        # Welcome Speech

        text_to_speach = pyttsx3.init()
        text_to_speach.save_to_file(
            """Thank-you for installing BAPSicle - the play-out server from the broadcasting and presenting suite.
        This server is accepting connections on port 13500
        The version of the server service is {}
        Please refer to the documentation included with this application for further assistance.""".format(
                config.VERSION
            ),
            "dev/welcome.mp3"
        )
        text_to_speach.runAndWait()

    new_item: Dict[str, any] = {
        "timeslotitemid": 0,
        "filename": "dev/welcome.mp3",
        "title":  "Welcome to BAPSicle",
        "artist":  "University Radio York",
    }

    channel_to_q[0].put("ADD:" + json.dumps(new_item))
    # channel_to_q[0].put("LOAD:0")
    # channel_to_q[0].put("PLAY")

    # Don't use reloader, it causes Nested Processes!
    app.run(host=state.state["host"], port=state.state["port"], debug=True, use_reloader=False)


def stopServer():
    print("Stopping server.py")
    for q in channel_to_q:
        q.put("QUIT")
    for player in channel_p:
        try:
            player.join()
        except:
            pass
    print("Stopped all players.")
    global stopping
    if stopping == False:
        stopping = True
        shutdown = request.environ.get('werkzeug.server.shutdown')
        if shutdown is None:
            print("Shutting down Server.")

        else:
            print("Shutting down Flask.")
            shutdown()


if __name__ == "__main__":
    print("BAPSicle is a service. Please run it like one.")
