"""Placement rationale is optional, except for an evaluated negative-EV wager."""

import pytest
from fastapi import HTTPException

from app.api.routes import DecisionContext, _validated_decision_context


def test_negative_ev_requires_a_reason():
    with pytest.raises(HTTPException, match="negative-EV"):
        _validated_decision_context(None, requires_negative_ev_reason=True)
    with pytest.raises(HTTPException, match="short reason"):
        _validated_decision_context(
            DecisionContext(source="hedge"), requires_negative_ev_reason=True
        )


def test_analyst_context_is_saved_for_a_negative_ev_bet():
    context = _validated_decision_context(
        DecisionContext(source="analyst", analyst="Chris Wecht"),
        requires_negative_ev_reason=True,
    )
    assert context == {"source": "analyst", "analyst": "Chris Wecht"}


def test_positive_ev_context_remains_optional():
    assert _validated_decision_context(None) is None
