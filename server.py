import multiprocessing
import player
from flask import Flask, render_template, send_from_directory, request
import json
import sounddevice as sd
import setproctitle
import logging
from helpers.os_environment import isMacOS

setproctitle.setproctitle("BAPSicle - Server")


class BAPSicleServer():
    def __init__(self):
        startServer()

    def __del__(self):
        stopServer()


app = Flask(__name__, static_url_path='')

log = logging.getLogger('werkzeug')
log.disabled = True
app.logger.disabled = True

channel_to_q = []
channel_from_q = []
channel_p = []

stopping = False


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
        "ui_title": ""
    }
    return render_template('index.html', data=data)


@app.route("/config")
def ui_config():
    channel_states = []
    for i in range(3):
        channel_states.append(status(i))

    devices = sd.query_devices()
    outputs = []

    for device in devices:
        if device["max_output_channels"] > 0:
            outputs.append(device)

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
    for i in range(3):
        channel_states.append(status(i))

    data = {
        'channels': channel_states,
        'ui_page': "status",
        "ui_title": "Status"
    }
    return render_template('status.html', data=data)


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


@app.route("/player/<int:channel>/unload")
def unload(channel):

    channel_to_q[channel].put("UNLOAD")

    return ui_status()


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
    ui_status()


@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('ui-static', path)


def startServer():
    if isMacOS():
        multiprocessing.set_start_method("spawn", True)
    for channel in range(3):

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

    # Don't use reloader, it causes Nested Processes!
    app.run(host='0.0.0.0', port=13500, debug=True, use_reloader=False)


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
