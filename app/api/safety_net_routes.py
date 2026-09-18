"""Explicit receipt and linkage actions, independent of settlement and cash profit."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.services import safety_net

router = APIRouter(prefix="/tracker/safety-nets", tags=["Safety nets"])


class ReceiptRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    amount: float | None = Field(default=None, gt=0, multiple_of=.01)


class LinkRequest(BaseModel):
    kind: Literal["straight", "parlay"]
    ticket_id: str
    unlink: bool = False


@router.get("")
def list_safety_nets():
    return safety_net.overview()


@router.post("/{source_id}/receipt")
def save_receipt(source_id: str, payload: ReceiptRequest):
    try:
        return {"parlay": safety_net.record_receipt(source_id, payload.amount)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{source_id}/link")
def save_link(source_id: str, payload: LinkRequest):
    try:
        return {"parlay": safety_net.link_bonus(source_id, payload.kind, payload.ticket_id, payload.unlink)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
