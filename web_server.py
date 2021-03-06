from helpers.myradio_api import MyRadioAPI
from sanic import Sanic
from sanic.exceptions import NotFound, abort
from sanic.response import html, text, file, redirect
from sanic.response import json as resp_json
from sanic_cors import CORS
from syncer import sync
import asyncio

from jinja2 import Environment, FileSystemLoader
from urllib.parse import unquote
from setproctitle import setproctitle
import logging
from typing import Any, Optional, List
from multiprocessing.queues import Queue
from queue import Empty
from time import sleep
import json
import os

from helpers.os_environment import isBundelled, resolve_external_file_path, resolve_local_file_path
from helpers.logging_manager import LoggingManager
from helpers.device_manager import DeviceManager
from helpers.state_manager import StateManager
from helpers.the_terminator import Terminator

env = Environment(loader=FileSystemLoader('%s/ui-templates/' % os.path.dirname(__file__)))
app = Sanic("BAPSicle Web Server")


def render_template(file, data, status=200):
    template = env.get_template(file)
    html_content = template.render(data=data)
    return html(html_content, status=status)


logger: LoggingManager
server_state: StateManager
api: MyRadioAPI

player_to_q: List[Queue] = []
player_from_q: List[Queue] = []

# General UI Endpoints


@app.exception(NotFound)
def page_not_found(request, e: Any):
    data = {"ui_page": "404", "ui_title": "404"}
    return render_template("404.html", data=data, status=404)


@app.route("/")
def ui_index(request):
    config = server_state.get()
    data = {
        "ui_page": "index",
        "ui_title": "",
        "server_version": config["server_version"],
        "server_build": config["server_build"],
        "server_name": config["server_name"],
        "server_beta": config["server_beta"],
        "server_branch": config["server_branch"]
    }
    return render_template("index.html", data=data)


@app.route("/status")
def ui_status(request):
    channel_states = []
    for i in range(server_state.get()["num_channels"]):
        channel_states.append(status(i))

    data = {"channels": channel_states,
            "ui_page": "status", "ui_title": "Status"}
    return render_template("status.html", data=data)


@app.route("/config/player")
def ui_config_player(request):
    channel_states = []
    for i in range(server_state.get()["num_channels"]):
        channel_states.append(status(i))

    outputs = DeviceManager.getAudioOutputs()

    data = {
        "channels": channel_states,
        "outputs": outputs,
        "ui_page": "config",
        "ui_title": "Player Config",
    }
    return render_template("config_player.html", data=data)


@app.route("/config/server")
def ui_config_server(request):
    data = {
        "ui_page": "server",
        "ui_title": "Server Config",
        "state": server_state.get(),
        "ser_ports": DeviceManager.getSerialPorts(),
        "tracklist_modes": ["off", "on", "delayed"]
    }
    return render_template("config_server.html", data=data)


@app.route("/config/server/update", methods=["POST"])
def ui_config_server_update(request):
    # TODO Validation!

    server_state.update("server_name", request.form.get("name"))
    server_state.update("host", request.form.get("host"))
    server_state.update("port", int(request.form.get("port")))
    server_state.update("num_channels", int(request.form.get("channels")))
    server_state.update("ws_port", int(request.form.get("ws_port")))
    server_state.update("serial_port", request.form.get("serial_port"))

    # Because we're not showing the api key once it's set.
    if "myradio_api_key" in request.form and request.form.get("myradio_api_key") != "":
        server_state.update("myradio_api_key", request.form.get("myradio_api_key"))

    server_state.update("myradio_base_url", request.form.get("myradio_base_url"))
    server_state.update("myradio_api_url", request.form.get("myradio_api_url"))
    server_state.update("myradio_api_tracklist_source", request.form.get("myradio_api_tracklist_source"))
    server_state.update("tracklist_mode", request.form.get("tracklist_mode"))

    return redirect("/restart")


@app.route("/logs")
def ui_logs_list(request):
    files = os.listdir(resolve_external_file_path("/logs"))
    log_files = []
    for file in files:
        if file.endswith(".log"):
            log_files.append(file.rstrip(".log"))

    log_files.sort()
    data = {
        "ui_page": "logs",
        "ui_title": "Logs",
        "logs": log_files
    }
    return render_template("loglist.html", data=data)


@app.route("/logs/<path:path>")
def ui_logs_render(request, path):
    page = request.args.get("page")
    if not page:
        return redirect(f"/logs/{path}?page=1")
    page = int(page)
    assert page >= 1

    log_file = open(resolve_external_file_path("/logs/{}.log").format(path))
    data = {
        "logs": log_file.read().splitlines()[-300*page:(-300*(page-1) if page > 1 else None)][::-1],
        "ui_page": "logs",
        "ui_title": "Logs - {}".format(path),
        "page": page
    }
    log_file.close()
    return render_template("log.html", data=data)


# Player Audio Control Endpoints
# Just useful for messing arround without presenter / websockets.


@app.route("/player/<channel:int>/<command>")
def player_simple(request, channel: int, command: str):

    simple_endpoints = ["play", "pause", "unpause", "stop", "unload", "clear"]
    if command in simple_endpoints:
        player_to_q[channel].put("UI:" + command.upper())
        return redirect("/status")

    abort(404)


@app.route("/player/<channel:int>/seek/<pos:number>")
def player_seek(request, channel: int, pos: float):

    player_to_q[channel].put("UI:SEEK:" + str(pos))

    return redirect("/status")


@app.route("/player/<channel:int>/load/<channel_weight:int>")
def player_load(request, channel: int, channel_weight: int):

    player_to_q[channel].put("UI:LOAD:" + str(channel_weight))
    return redirect("/status")


@app.route("/player/<channel:int>/remove/<channel_weight:int>")
def player_remove(request, channel: int, channel_weight: int):
    player_to_q[channel].put("UI:REMOVE:" + str(channel_weight))

    return redirect("/status")


@app.route("/player/<channel:int>/output/<name:string>")
def player_output(request, channel: int, name: Optional[str]):
    player_to_q[channel].put("UI:OUTPUT:" + unquote(str(name)))
    return redirect("/config/player")


@app.route("/player/<channel:int>/autoadvance/<state:int>")
def player_autoadvance(request, channel: int, state: int):
    player_to_q[channel].put("UI:AUTOADVANCE:" + str(state))
    return redirect("/status")


@app.route("/player/<channel:int>/repeat/<state:string>")
def player_repeat(request, channel: int, state: str):
    player_to_q[channel].put("UI:REPEAT:" + state.upper())
    return redirect("/status")


@app.route("/player/<channel:int>/playonload/<state:int>")
def player_playonload(request, channel: int, state: int):
    player_to_q[channel].put("UI:PLAYONLOAD:" + str(state))
    return redirect("/status")


@app.route("/player/<channel:int>/status")
def player_status_json(request, channel: int):

    return resp_json(status(channel))


@app.route("/player/all/stop")
def player_all_stop(request):

    for channel in player_to_q:
        channel.put("UI:STOP")
    return redirect("/status")


# Show Plan Functions

@app.route("/plan/load/<timeslotid:int>")
def plan_load(request, timeslotid: int):

    for channel in player_to_q:
        channel.put("UI:GET_PLAN:" + str(timeslotid))

    return redirect("/status")


@app.route("/plan/clear")
def plan_clear(request):
    for channel in player_to_q:
        channel.put("UI:CLEAR")
    return redirect("/status")


# API Proxy Endpoints

@app.route("/plan/list")
async def api_list_showplans(request):

    return resp_json(await api.get_showplans())


@app.route("/library/search/track")
async def api_search_library(request):

    return resp_json(await api.get_track_search(request.args.get("title"), request.args.get("artist")))


@app.route("/library/playlists/<type:string>")
async def api_get_playlists(request, type: str):

    if type not in ["music", "aux"]:
        abort(401)

    if type == "music":
        return resp_json(await api.get_playlist_music())
    else:
        return resp_json(await api.get_playlist_aux())


@app.route("/library/playlist/<type:string>/<library_id:string>")
async def api_get_playlist(request, type: str, library_id: str):

    if type not in ["music", "aux"]:
        abort(401)

    if type == "music":
        return resp_json(await api.get_playlist_music_items(library_id))
    else:
        return resp_json(await api.get_playlist_aux_items(library_id))


# JSON Outputs


@app.route("/status-json")
def json_status(request):
    channel_states = []
    for i in range(server_state.get()["num_channels"]):
        channel_states.append(status(i))
    return resp_json({"server": server_state.get(), "channels": channel_states})


# Get audio for UI to generate waveforms.


@app.route("/audiofile/<type:string>/<id:int>")
async def audio_file(request, type: str, id: int):
    if type not in ["managed", "track"]:
        abort(404)
    return await file("music-tmp/" + type + "-" + str(id) + ".mp3")


# Static Files
app.static("/favicon.ico", resolve_local_file_path("ui-static/favicon.ico"), name="ui-favicon")
app.static("/static", resolve_local_file_path("ui-static"), name="ui-static")
app.static("/presenter/", resolve_local_file_path("presenter-build/index.html"),
           strict_slashes=True, name="presenter-index")
app.static("/presenter/", resolve_local_file_path("presenter-build"))


# Helper Functions

def status(channel: int):
    while not player_from_q[channel].empty():
        player_from_q[channel].get()  # Just waste any previous status responses.

    player_to_q[channel].put("UI:STATUS")
    retries = 0
    while retries < 40:
        try:
            response = player_from_q[channel].get_nowait()
            if response.startswith("UI:STATUS:"):
                response = response.split(":", 2)[2]
                # TODO: Handle OKAY / FAIL
                response = response[response.index(":") + 1:]
                try:
                    response = json.loads(response)
                except Exception as e:
                    raise e
                return response

        except Empty:
            pass

        retries += 1

        sleep(0.02)

# WebServer Start / Stop Functions


@app.route("/quit")
def quit(request):
    server_state.update("running_state", "quitting")

    data = {
        "ui_page": "message",
        "ui_title": "Quitting BAPSicle",
        "title": "See you later!",
        "ui_menu": False,
        "message": "BAPSicle is going back into winter hibernation, see you again soon!"
    }
    return render_template("message.html", data)


@app.route("/restart")
def restart(request):
    server_state.update("running_state", "restarting")

    data = {
        "ui_page": "message",
        "ui_title": "Restarting BAPSicle",
        "title": "Please Wait...",
        "ui_menu": False,
        "message": "Just putting BAPSicle back in the freezer for a moment!",
        "redirect_to": "/",
        "redirect_wait_ms": 10000
    }
    return render_template("message.html", data)


# Don't use reloader, it causes Nested Processes!
def WebServer(player_to: List[Queue], player_from: List[Queue], state: StateManager):

    global player_to_q, player_from_q, server_state, api, app
    player_to_q = player_to
    player_from_q = player_from
    server_state = state

    logger = LoggingManager("WebServer")
    api = MyRadioAPI(logger, state)

    process_title = "Web Server"
    setproctitle(process_title)
    CORS(app, supports_credentials=True)  # Allow ALL CORS!!!

    terminate = Terminator()
    while not terminate.terminate:
        try:
            sync(app.run(
                host=server_state.get()["host"],
                port=server_state.get()["port"],
                debug=(not isBundelled()),
                auto_reload=False,
                access_log=(not isBundelled())
            ))
        except Exception:
            break
    loop = asyncio.get_event_loop()
    if loop:
        loop.close()
    if app:
        app.stop()
        del app
