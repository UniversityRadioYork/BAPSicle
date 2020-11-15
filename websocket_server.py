import asyncio
import websockets
import json

baps_clients = set()
channel_to_q = None


async def websocket_handler(websocket, path):
    baps_clients.add(websocket)
    await websocket.send(json.dumps({"message": "Hello"}))
    print("New Client: {}".format(websocket))

    try:
        async for message in websocket:
            data = json.loads(message)
            channel = int(data["channel"])
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
                    pass

            asyncio.wait([await conn.send(message) for conn in baps_clients])

    except websockets.exceptions.ConnectionClosedError:
        print("RIP {}".format(websocket))

    except Exception as e:
        print(e)

    finally:
        baps_clients.remove(websocket)


class WebsocketServer:

    def __init__(self, in_q, state):
        global channel_to_q
        channel_to_q = in_q

        websocket_server = websockets.serve(websocket_handler, state.state["host"], state.state["ws_port"])

        asyncio.get_event_loop().run_until_complete(websocket_server)
        asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    print("Don't do this")
