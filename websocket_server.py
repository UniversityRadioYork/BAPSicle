import asyncio
from asyncio.futures import Future
from asyncio.tasks import Task, shield

from websockets.server import Serve
from helpers.logging_manager import LoggingManager
import multiprocessing
import queue
from typing import Any, Dict, List, Optional
import websockets
import json
from os import _exit

class WebsocketServer:

    threads = Future
    baps_clients = set()
    channel_to_q: List[multiprocessing.Queue]
    webstudio_to_q: List[multiprocessing.Queue]
    server_name: str
    logger: LoggingManager
    to_webstudio: Task
    from_webstudio: Task
    websocket_server: Serve

    def __init__(self, in_q, out_q, state):

        self.channel_to_q = in_q
        self.webstudio_to_q = out_q

        self.logger = LoggingManager("Websockets")
        self.server_name = state.state["server_name"]

        self.websocket_server = websockets.serve(self.websocket_handler, state.state["host"], state.state["ws_port"])

        asyncio.get_event_loop().run_until_complete(self.websocket_server)

        try:
            asyncio.get_event_loop().run_forever()
        except:
            self.quit()

    def quit(self):
        del self.websocket_server
        del self.logger
        _exit(0)

    def __del__(self):
        print("Deleting websocket server")
        self.quit()

    async def websocket_handler(self, websocket, path):
        self.baps_clients.add(websocket)
        await websocket.send(json.dumps({"message": "Hello", "serverName": self.server_name}))
        self.logger.log.info("New Client: {}".format(websocket))
        for channel in self.channel_to_q:
            channel.put("WEBSOCKET:STATUS")

        async def handle_from_webstudio():
            try:
                async for message in websocket:
                    data = json.loads(message)
                    if not "channel" in data:
                        # Didn't specify a channel, send to all.
                        for channel in range(len(self.channel_to_q)):
                            sendCommand(channel, data)
                    else:
                        channel = int(data["channel"])
                        sendCommand(channel, data)

                    async def send(conn, message):
                        # TODO this doesn't actually catch.
                        try:
                            await conn.send(message)
                        except:
                            pass

                    await asyncio.wait([send(conn, message) for conn in self.baps_clients])

            except websockets.exceptions.ConnectionClosedError as e:
                self.logger.log.error("Client Disconncted {}, {}".format(websocket, e))

            # TODO: Proper Logging
            except Exception as e:
                self.logger.log.exception("Exception handling messages from Websocket.\n{}".format(e))

            finally:
                self.logger.log.info("Removing client: {}".format(websocket))
                self.baps_clients.remove(websocket)

        def sendCommand(channel, data):
            if channel not in range(len(self.channel_to_q)):
                self.logger.log.exception("Received channel number larger than server supported channels.")
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
                        self.channel_to_q[new_channel].put("ADD:" + json.dumps(item))


                except ValueError as e:
                    self.logger.log.exception("Error decoding extra data {} for command {} ".format(e, command))
                    pass

                # Stick the message together and send!
                if extra != "":
                    message += ":" + extra

                try:
                    self.channel_to_q[channel].put(message)
                except Exception as e:
                    self.logger.log.exception("Failed to send message {} to channel {}: {}".format(message, channel, e))

            else:
                self.logger.log.error("Command missing from message. Data: {}".format(data))

        async def handle_to_webstudio():
            while True:
                for channel in range(len(self.webstudio_to_q)):
                    try:
                        message = self.webstudio_to_q[channel].get_nowait()
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
                        elif command == "QUIT":
                            self.quit()
                        else:
                            continue

                        data = json.dumps({
                            "command": command,
                            "data": message,
                            "channel": channel
                        })
                        await asyncio.wait([conn.send(data) for conn in self.baps_clients])
                    except queue.Empty:
                        continue
                    except ValueError:
                        # Typically a "Set of coroutines/Futures is empty." when sending to a dead client.
                        continue
                    except Exception as e:
                        self.logger.log.exception("Exception trying to send to websocket:", e)
                await asyncio.sleep(0.02)

        self.from_webstudio = asyncio.create_task(handle_from_webstudio())
        self.to_webstudio = asyncio.create_task(handle_to_webstudio())

        try:
            self.threads = await shield(asyncio.gather(self.from_webstudio, self.to_webstudio))
        finally:
            self.from_webstudio.cancel()
            self.to_webstudio.cancel()




if __name__ == "__main__":
    print("Don't do this")