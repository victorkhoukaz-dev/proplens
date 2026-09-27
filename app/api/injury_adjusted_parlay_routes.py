from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import injury_adjusted_parlay

router = APIRouter(prefix="/tracker/injury-adjusted-parlays", tags=["Injury-adjusted parlays"])


class ReceiptRequest(BaseModel):
    amount: float = Field(gt=0, multiple_of=.01)
    injured_leg_index: int = Field(ge=0)


@router.get("")
def list_injury_adjusted_parlays():
    return injury_adjusted_parlay.overview()


@router.post("/{parlay_id}/receipt")
def save_receipt(parlay_id: str, payload: ReceiptRequest):
    try:
        return {"parlay": injury_adjusted_parlay.record_receipt(parlay_id, payload.amount, payload.injured_leg_index)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
