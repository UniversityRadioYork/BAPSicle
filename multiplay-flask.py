import multiprocessing
import bapsicle_standalone
from flask import Flask, render_template, send_from_directory
import json
import sounddevice as sd

app = Flask(__name__, static_url_path='')

channel_to_q = []
channel_from_q = []
channel_p = []



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

@app.route("/status")
def ui_status():
    channel_states = []
    for i in range(3):
      channel_states.append(details(i))

    devices = sd.query_devices()
    outputs = []
    
    for device in devices:
      if device["max_output_channels"] > 0:
        outputs.append(device)

    

    data = {
      'channels': channel_states,
      'outputs': outputs,
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
  channel_to_q[channel].put("LOAD:test"+str(channel)+".mp3")
  return ui_status()


@app.route("/player/<int:channel>/details")
def details(channel):

  channel_to_q[channel].put("DETAILS")
  while True:
    response = channel_from_q[channel].get()

    if response and response.startswith("RESP:DETAILS"):
      return json.loads(response.strip("RESP:DETAILS:"))


@app.route("/player/all/stop")
def all_stop():
  for channel in channel_to_q:
    channel.put("STOP")
  ui_status()


@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('ui-static', path)

if __name__ == "__main__":

  for channel in range(3):
    channel_to_q.append(multiprocessing.Queue())
    channel_from_q.append(multiprocessing.Queue())
    # channel_to_q[-1].put_nowait("LOAD:test"+str(channel)+".mp3")
    channel_p.append(
      multiprocessing.Process(
        target=bapsicle_standalone.bapsicle,
        args=(channel, channel_to_q[-1], channel_from_q[-1])
      )
    )
    channel_p[channel].start()


  # Don't use reloader, it causes Nested Processes!
  app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
