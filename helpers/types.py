from enum import Enum
from plan import PlanItem
from typing import List, Optional

from typing_extensions import TypedDict


class ServerState(TypedDict):
    server_version: str
    server_name: str
    host: str
    port: int
    num_channels: int


class RepeatMode(Enum):
    none = 0
    one = 1
    all = 2


# TODO: Use this.
class PlayerState(TypedDict):
    initialised: bool
    loaded_item: Optional[PlanItem]
    channel: int
    playing: bool
    paused: bool
    loaded: bool
    pos: float
    pos_offset: float
    pos_true: float
    remaining: float
    length: float
    auto_advance: bool
    repeat: RepeatMode
    play_on_load: bool
    output: Optional[str]
    show_plan: List[PlanItem]
    last_updated: str
