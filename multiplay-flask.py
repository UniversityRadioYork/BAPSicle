import multiprocessing
from bapsicle_standalone import bapsicle
from flask import Flask, render_template
import json

app = Flask(__name__)

channel_to_q = []
channel_from_q = []
channel_p = []








@app.route("/")
def status():
    data = []
    for i in range(3):
      data.append(details(i))
    return render_template('index.html', data=data)


@app.route("/player/<int:channel>/play")
def play(channel):

  channel_to_q[channel].put("PLAY")

  return status()


@app.route("/player/<int:channel>/pause")
def pause(channel):

  channel_to_q[channel].put("PAUSE")

  return status()


@app.route("/player/<int:channel>/unpause")
def unPause(channel):

  channel_to_q[channel].put("UNPAUSE")

  return status()


@app.route("/player/<int:channel>/stop")
def stop(channel):

  channel_to_q[channel].put("STOP")

  return status()


@app.route("/player/<int:channel>/seek/<int:pos>")
def seek(channel, pos):

  channel_to_q[channel].put("SEEK:" + str(pos))

  return status()


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
  status()

if __name__ == "__main__":

  for channel in range(3):
    channel_to_q.append(multiprocessing.Queue())
    channel_from_q.append(multiprocessing.Queue())
    channel_to_q[-1].put_nowait("LOAD:test"+str(channel)+".mp3")
    channel_p.append(multiprocessing.Process(target=bapsicle, args=(channel, channel_to_q[-1], channel_from_q[-1])).start())


  app.run(host='0.0.0.0', port=5000, debug=True)
