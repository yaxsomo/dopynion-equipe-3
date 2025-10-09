from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from pydantic import BaseModel


def get_game_id(x_game_id: str = Header(description="ID of the game")) -> str:
    return x_game_id


GameIdDependency = Annotated[str, Depends(get_game_id)]


class DopynionResponseBool(BaseModel):
    game_id: str
    decision: bool


class DopynionResponseCardName(BaseModel):
    game_id: str
    decision: str  # CardName alias is a str in datamodel


class DopynionResponseStr(BaseModel):
    game_id: str
    decision: str
