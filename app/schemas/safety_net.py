"""Optional full-loss bonus refund; never part of cash settlement accounting."""
import math
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SafetyNetOffer(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    refund_amount: float = Field(gt=0, multiple_of=.01)
    conversion_rate: float = Field(ge=0, le=1)


class SafetyNetFields(BaseModel):
    safety_net: SafetyNetOffer | None = None

    @model_validator(mode="after")
    def validate_safety_net(self):
        if self.safety_net is not None:
            for key in ("stake", "original_decimal_odds", "effective_decimal_odds", "decimal_odds", "profit_boost_pct", "actual_total_return"):
                value = getattr(self, key, None)
                if value is not None and not math.isfinite(value):
                    raise ValueError("Safety-net amounts and odds must be finite numbers.")
            if self.bet_type != "cash":
                raise ValueError("Safety nets apply to cash parlays only.")
            if self.safety_net.refund_amount > self.stake:
                raise ValueError("The bonus refund cannot exceed the cash stake.")
        return self
