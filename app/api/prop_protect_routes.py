from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.services import prop_protect

router = APIRouter(prefix="/tracker/prop-protect", tags=["Prop Protect"])
class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger: Literal["injury_void", "bonus_cashout"]
    amount: float = Field(gt=0, multiple_of=.01)
class Link(BaseModel):
    kind: Literal["straight", "parlay"]
    ticket_id: str
    unlink: bool = False
@router.get("")
def list_prop_protect(): return prop_protect.overview()
@router.post("/{kind}/{source_id}/receipt")
def save_receipt(kind: Literal["straight", "parlay"], source_id: str, payload: Receipt):
    try: return {"ticket": prop_protect.record_receipt(kind, source_id, payload.trigger, payload.amount)}
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
@router.post("/{kind}/{source_id}/link")
def save_link(kind: Literal["straight", "parlay"], source_id: str, payload: Link):
    try: return {"ticket": prop_protect.link_bonus(kind, source_id, payload.kind, payload.ticket_id, payload.unlink)}
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
