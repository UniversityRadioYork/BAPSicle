import asyncio
import multiprocessing
import queue
from typing import Dict, List, Optional
import websockets
import json

baps_clients = set()
channel_to_q: List[multiprocessing.Queue]
webstudio_to_q: List[multiprocessing.Queue]
server_name: str



async def websocket_handler(websocket, path):
    baps_clients.add(websocket)
    await websocket.send(json.dumps({"message": "Hello", "serverName": server_name}))
    print("New Client: {}".format(websocket))
    for channel in channel_to_q:
        channel.put("STATUS")

    async def handle_from_webstudio():
        try:
            async for message in websocket:
                data = json.loads(message)
                channel = int(data["channel"])
                print(data)
                if "command" in data.keys():
                    if data["command"] == "PLAY":
                        channel_to_q[channel].put("PLAY")
                    elif data["command"] == "PAUSE":
                        channel_to_q[channel].put("PAUSE")
                    elif data["command"] == "UNPAUSE":
                        channel_to_q[channel].put("UNPAUSE")
                    elif data["command"] == "STOP":
                        channel_to_q[channel].put("STOP")
                    elif data["command"] == "SEEK":
                        channel_to_q[channel].put("SEEK:" + str(data["time"]))
                    elif data["command"] == "LOAD":
                        channel_to_q[channel].put("LOAD:" + str(data["weight"]))

                    elif data["command"] == "AUTOADVANCE":
                        channel_to_q[channel].put("AUTOADVANCE:" + str(data["enabled"]))

                    elif data["command"] == "PLAYONLOAD":
                        channel_to_q[channel].put("PLAYONLOAD:" + str(data["enabled"]))

                    elif data["command"] == "REPEAT":
                        channel_to_q[channel].put("REPEAT:" + str(data["mode"]).lower())


                    elif data["command"] == "ADD":
                        channel_to_q[channel].put("ADD:" + json.dumps(data["newItem"]))
                    elif data["command"] == "REMOVE":
                        channel_to_q[channel].put("REMOVE:" + str(data["weight"]))

                await asyncio.wait([conn.send(message) for conn in baps_clients])

        except websockets.exceptions.ConnectionClosedError as e:
            print("RIP {}, {}".format(websocket, e))

        except Exception as e:
            print("Exception", e)

        finally:
            baps_clients.remove(websocket)

    async def handle_to_webstudio():
        while True:
            for channel in range(len(webstudio_to_q)):
                try:
                    message = webstudio_to_q[channel].get_nowait()
                    command = message.split(":")[0]
                    #print("Websocket Out:", command)
                    if command == "STATUS":
                        try:
                            message = message.split("OKAY:")[1]
                            message = json.loads(message)
                        except:
                            continue
                    elif command == "POS":
                        message = message.split(":")[1]
                    else:
                        continue

                    data = json.dumps({
                        "command": command,
                        "data": message,
                        "channel": channel
                    })
                    await asyncio.wait([conn.send(data) for conn in baps_clients])
                except queue.Empty:
                    pass
                except Exception as e:
                    raise e
            await asyncio.sleep(0.01)

    from_webstudio = asyncio.create_task(handle_from_webstudio())
    to_webstudio = asyncio.create_task(handle_to_webstudio())

    try:
        await asyncio.gather(from_webstudio, to_webstudio)
    finally:
        from_webstudio.cancel()
        to_webstudio.cancel()


class WebsocketServer:

    def __init__(self, in_q, out_q, state):
        global channel_to_q
        global webstudio_to_q
        channel_to_q = in_q
        webstudio_to_q = out_q

        global server_name
        server_name = state.state["server_name"]

        websocket_server = websockets.serve(websocket_handler, state.state["host"], state.state["ws_port"])

        asyncio.get_event_loop().run_until_complete(websocket_server)
        asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    print("Don't do this")
