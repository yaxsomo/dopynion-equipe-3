from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class PlayRequest(BaseModel):
    player_id: str
    action: str


class PlayResponse(BaseModel):
    valid: bool
    message: str


@router.post("/play", response_model=PlayResponse)
def play(req: PlayRequest) -> PlayResponse:
    if req.action not in {"buy", "trash", "end", "play"}:
        return PlayResponse(valid=False, message="Action invalide")
    return PlayResponse(valid=True, message=f"Action {req.action} acceptée")
