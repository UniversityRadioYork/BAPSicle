import asyncio
from asyncio.futures import Future
from asyncio.tasks import Task, shield
import multiprocessing
import queue
from typing import List
import websockets
import json
from os import _exit
from websockets.server import Serve
from setproctitle import setproctitle
from multiprocessing import current_process

from helpers.logging_manager import LoggingManager
from helpers.the_terminator import Terminator


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

        process_title = "Websockets Servr"
        setproctitle(process_title)
        current_process().name = process_title

        self.logger = LoggingManager("Websockets")
        self.server_name = state.get()["server_name"]

        self.websocket_server = websockets.serve(
            self.websocket_handler, state.get()["host"], state.get()["ws_port"]
        )

        asyncio.get_event_loop().run_until_complete(self.websocket_server)
        asyncio.get_event_loop().run_until_complete(self.handle_to_webstudio())

        try:
            asyncio.get_event_loop().run_forever()
        except Exception:
            # Sever died somehow, just quit out.
            self.quit()

    def quit(self):
        self.logger.log.info("Quitting.")
        del self.websocket_server
        del self.logger
        _exit(0)

    def __del__(self):
        self.logger.log.info("Deleting websocket server")
        self.quit()

    async def websocket_handler(self, websocket, path):
        self.baps_clients.add(websocket)
        await websocket.send(
            json.dumps({"message": "Hello", "serverName": self.server_name})
        )
        self.logger.log.info("New Client: {}".format(websocket))
        for channel in self.channel_to_q:
            channel.put("WEBSOCKET:STATUS")

        self.from_webstudio = asyncio.create_task(
            self.handle_from_webstudio(websocket))

        try:
            self.threads = await shield(asyncio.gather(self.from_webstudio))
        finally:
            self.from_webstudio.cancel()

    async def handle_from_webstudio(self, websocket):
        try:
            async for message in websocket:
                data = json.loads(message)
                if "channel" not in data:
                    # Didn't specify a channel, send to all.
                    for channel in range(len(self.channel_to_q)):
                        self.sendCommand(channel, data)
                else:
                    channel = int(data["channel"])
                    self.sendCommand(channel, data)

                await asyncio.wait([conn.send(message) for conn in self.baps_clients])

        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.log.error(
                "Client Disconncted {}, {}".format(websocket, e))

        except Exception as e:
            self.logger.log.exception(
                "Exception handling messages from Websocket.\n{}".format(e)
            )

        finally:
            self.logger.log.info("Removing client: {}".format(websocket))
            self.baps_clients.remove(websocket)

    def sendCommand(self, channel, data):
        if channel not in range(len(self.channel_to_q)):
            self.logger.log.exception(
                "Received channel number larger than server supported channels."
            )
            return

        if "command" in data.keys():
            command = data["command"]

            # Handle the general case
            # Message format:
            # SOURCE:COMMAND:EXTRADATA

            message = "WEBSOCKET:"

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
                elif command == "RESETPLAYED":
                    extra += str(data["weight"])
                elif command == "SETPLAYED":
                    extra += str(data["weight"])
                elif command == "GETPLAN":
                    extra += str(data["timeslotId"])
                elif command == "SETMARKER":
                    extra += "{}:{}".format(
                        data["timeslotitemid"], json.dumps(data["marker"])
                    )

                # TODO: Move this to player handler.
                # SPECIAL CASE ALERT! We need to talk to two channels here.
                elif command == "MOVE":

                    # remove the exiting item first
                    self.channel_to_q[channel].put(
                        "{}REMOVE:{}".format(message, data["weight"])
                    )

                    # Now hijack to send the new add on the new channel.

                    # Now modify the item with the weight in the new channel
                    new_channel = int(data["new_channel"])
                    item = data["item"]
                    item["weight"] = int(data["new_weight"])

                    # Now send the special case.
                    self.channel_to_q[new_channel].put(
                        "WEBSOCKET:ADD:" + json.dumps(item)
                    )

                    # Don't bother, we should be done.
                    return

            except ValueError as e:
                self.logger.log.exception(
                    "Error decoding extra data {} for command {} ".format(
                        e, command)
                )
                pass

            # Stick the message together and send!
            message += (
                # Put the command in at the end, in case MOVE etc changed it.
                command
            )
            if extra != "":
                message += ":" + extra

            try:
                self.channel_to_q[channel].put(message)
            except Exception as e:
                self.logger.log.exception(
                    "Failed to send message {} to channel {}: {}".format(
                        message, channel, e
                    )
                )

        else:
            self.logger.log.error(
                "Command missing from message. Data: {}".format(data))

    async def handle_to_webstudio(self):

        terminator = Terminator()
        while not terminator.terminate:

            for channel in range(len(self.webstudio_to_q)):
                try:
                    message = self.webstudio_to_q[channel].get_nowait()
                    source = message.split(":")[0]
                    # TODO ENUM
                    if source not in ["WEBSOCKET", "ALL"]:
                        self.logger.log.error(
                            "ERROR: Message received from invalid source to websocket_handler. Ignored.",
                            source,
                            message,
                        )
                        continue

                    command = message.split(":")[1]
                    if command == "STATUS":
                        try:
                            message = message.split("OKAY:")[1]
                            message = json.loads(message)
                        except Exception:
                            continue  # TODO more logging
                    elif command == "POS":
                        try:
                            message = message.split(":", 2)[2]
                        except Exception:
                            continue
                    elif command == "QUIT":
                        self.quit()
                    else:
                        continue

                    data = json.dumps(
                        {"command": command, "data": message, "channel": channel}
                    )
                    await asyncio.wait([conn.send(data) for conn in self.baps_clients])
                except queue.Empty:
                    continue
                except ValueError:
                    # Typically a "Set of coroutines/Futures is empty." when sending to a dead client.
                    continue
                except Exception as e:
                    self.logger.log.exception(
                        "Exception trying to send to websocket:", e
                    )
            await asyncio.sleep(0.02)

        self.quit()


if __name__ == "__main__":
    raise Exception("Don't run this file standalone.")
