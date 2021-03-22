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
        channel.put("WEBSOCKET:STATUS")

    async def handle_from_webstudio():
        try:
            async for message in websocket:
                data = json.loads(message)
                print(data)
                if not "channel" in data:
                    # Didn't specify a channel, send to all.
                    for channel in range(len(channel_to_q)):
                        sendCommand(channel, data)
                else:
                    channel = int(data["channel"])
                    sendCommand(channel, data)


                await asyncio.wait([conn.send(message) for conn in baps_clients])

        except websockets.exceptions.ConnectionClosedError as e:
            print("RIP {}, {}".format(websocket, e))

        # TODO: Proper Logging
        except Exception as e:
            print("Exception", e)

        finally:
            baps_clients.remove(websocket)

    def sendCommand(channel, data):
        if channel not in range(len(channel_to_q)):
            print("ERROR: Received channel number larger than server supported channels.")
            return

        if "command" in data.keys():
            command = data["command"]

            # Handle the general case
            # Message format:
            ## SOURCE:COMMAND:EXTRADATA

            message = "WEBSOCKET:" + command

            # If we just want PLAY, PAUSE etc, we're all done.
            # Else, let's pipe in some extra info.
            extra = ""

            try:
                if command == "SEEK":
                    extra += str(data["time"])
                elif command == "LOAD":
                    extra += str(data["weight"])
                elif command == "AUTOADVANCE":
                    extra += str(data["enabled"])
                elif command == "PLAYONLOAD":
                    extra += str(data["enabled"])
                elif command == "REPEAT":
                    extra += str(data["mode"]).lower()
                elif command == "ADD":
                    extra += json.dumps(data["newItem"])
                elif command == "REMOVE":
                    extra += str(data["weight"])
                elif command == "GET_PLAN":
                    extra += str(data["timeslotId"])

                # SPECIAL CASE ALERT! We need to talk to two channels here.
                elif command == "MOVE":
                    # TODO Should we trust the client with the item info?

                    # Tell the old channel to remove "weight"
                    extra += str(data["weight"])

                    # Now modify the item with the weight in the new channel
                    new_channel = int(data["new_channel"])
                    item = data["item"]
                    item["weight"] = int(data["new_weight"])
                    # Now send the special case.
                    channel_to_q[new_channel].put("ADD:" + json.dumps(item))


            except ValueError as e:
                print("ERROR decoding extra data {} for command {} ".format(e, command))
                pass

            # Stick the message together and send!
            if extra != "":
                message += ":" + extra

            try:
                channel_to_q[channel].put(message)
            except Exception as e:
                print("ERRORL: Failed to send message {} to channel {}: {}".format(message, channel, e))

        else:
            print("ERROR: Command missing from message.")

    async def handle_to_webstudio():
        while True:
            for channel in range(len(webstudio_to_q)):
                try:
                    message = webstudio_to_q[channel].get_nowait()
                    source = message.split(":")[0]

                    # TODO ENUM
                    if source not in ["WEBSOCKET","ALL"]:
                        print("ERROR: Message received from invalid source to websocket_handler. Ignored.", source, message)
                        continue

                    command = message.split(":")[1]
                    #print("Websocket Out:", command)
                    if command == "STATUS":
                        try:
                            message = message.split("OKAY:")[1]
                            message = json.loads(message)
                        except:
                            continue # TODO more logging
                    elif command == "POS":
                        try:
                            message = message.split(":", 2)[2]
                        except:
                            continue
                    else:
                        continue

                    data = json.dumps({
                        "command": command,
                        "data": message,
                        "channel": channel
                    })
                    await asyncio.wait([conn.send(data) for conn in baps_clients])
                except queue.Empty:
                    continue
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
