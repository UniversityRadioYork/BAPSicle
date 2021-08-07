# msg parsing helpers


from typing import Optional, Union
from json import dumps, loads

def encode_msg_new(src:str,command:str, extra:Optional[Union[str,list,object]] = None, status:Optional[bool] = None):
  encoded = {
    "src": src,
    "command": command,
    "extra": extra
  }
  return encode_msg_dict(encoded, status)

def encode_msg_dict(msg:dict, status:Optional[bool] = None, status_reason:str = None):
  msg["status"]=status
  msg["reason"] = status_reason
  return dumps(msg)

def decode_msg(msg:str):
  return loads(msg)
#def decode_msg(msg:str):
#  decoded = {}

  # See Wiki docs for format

  # SRC:COMMAND:EXTRAS
#  msg_split = msg.split(":")
#  msg_parts = len(msg_split)
#  if msg_parts < 2:
#    raise ValueError("Failed to parse decoded msg, not enough parts: {}".format(msg))

#  decoded["source"] = msg_split[0]
#  decoded["command"] = msg_split[1]

#  if msg_parts > 2:

#  if msg.endswith(":OKAY") or msg.endswith(":FAIL"):
#    decoded["status"] = msg[len(msg)-4:]
#  else:
#    decoded["status"] = None

#  print(decoded)

