"""Conservative draft extraction from a placed parlay ticket's OCR text.

This module never saves a wager. Unclear fields stay blank for human review.
"""
from __future__ import annotations

import re
from typing import Any


MARKETS = (
    ("rushing_receiving_yards", r"rush(?:ing)?\s*(?:\+|and|&)\s*receiv(?:ing)?\s*yards?"),
    ("passing_interceptions", r"passing\s+interceptions?"),
    ("tackles_assists", r"tackles?\s*(?:\+|and|&)\s*assists?"),
    ("rushing_attempts", r"rushing\s+attempts?"),
    ("passing_yards", r"(?:passing|pass)\s+(?:yards?|yds?)"),
    ("rushing_yards", r"(?:rushing|rush)\s+(?:yards?|yds?)"),
    ("receiving_yards", r"(?:receiving|rec)\s+(?:yards?|yds?)"),
    ("receptions", r"receptions?"),
    ("passing_tds", r"passing\s+(?:touchdowns?|tds?)"),
    ("sacks", r"sacks?"),
    ("anytime_td", r"anytime\s+(?:touchdown|td)(?:\s+scorer)?|to\s+score\s+(?:a\s+)?touchdown"),
)
SIDE_LINE = re.compile(r"\b(over|under)\s+(\d+(?:[.,]\d+)?)\b", re.I)
PLUS_LINE = re.compile(r"\b(\d+)\s*\+")
EXPLICIT_ODDS_LABEL = re.compile(r"\b(?:total|combined|parlay)\s+odds\b", re.I)
ODDS_LABEL = re.compile(r"^odds\b|^price\b", re.I)
SGP_LABEL = re.compile(r"\bsame\s+game\s+parlay\b", re.I)
STAKE_LABEL = re.compile(r"\b(?:total\s+)?stake\b|\bbet\s+amount\b|\bwager(?:\s+amount)?\b", re.I)
GAME_MARKET = re.compile(r"\b(?:moneyline|spread|game total|team total)\b", re.I)
PRICE = re.compile(r"(?<!\w)([+-]\d{3,5}|\d{1,5}[.,]\d{2})(?!\w)")
MONEY = re.compile(r"(?<!\w)(?:\$\s*)?(\d{1,5}(?:[.,]\d{2})?)(?!\w)")


def _decimal_price(token: str) -> float | None:
    token = token.replace(",", ".")
    if token.startswith("+"):
        price = 1 + int(token[1:]) / 100
    elif token.startswith("-"):
        price = 1 + 100 / abs(int(token))
    else:
        price = float(token)
    return round(price, 4) if 1 < price < 10000 else None


def _labeled_value(lines: list[str], label: re.Pattern[str], value: re.Pattern[str]) -> str | None:
    for index, line in enumerate(lines):
        matched = label.search(line)
        if not matched:
            continue
        candidate = value.search(line[matched.end():])
        if candidate:
            return candidate.group(1)
        if index + 1 < len(lines) and not line[matched.end():].strip(" :|=-"):
            if STAKE_LABEL.search(lines[index + 1]) or EXPLICIT_ODDS_LABEL.search(lines[index + 1]) or ODDS_LABEL.search(lines[index + 1]):
                continue
            candidate = value.search(lines[index + 1])
            if candidate:
                return candidate.group(1)
    return None


def _clean_name(text: str) -> str | None:
    text = re.sub(r"\b(?:player|selection|leg\s*\d+|yes|no)\b", " ", text, flags=re.I)
    text = re.sub(r"(?:\s+[-+]?\d{1,5}[.,]\d{2})$", "", text)
    text = re.sub(r"^[\s:;·,|—–-]+|[\s:;·,|—–-]+$", "", text)
    text = " ".join(text.split())
    if not re.fullmatch(r"[A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*){1,4}", text):
        return None
    if re.search(r"\b(?:parlay|bet|total|stake|odds|return|profit|boost)\b", text, re.I):
        return None
    return text


def _structured_leg(text: str) -> dict[str, Any] | None:
    for market, pattern in MARKETS:
        market_match = re.search(rf"\b(?:{pattern})\b", text, re.I)
        if not market_match:
            continue
        side = SIDE_LINE.search(text)
        plus = PLUS_LINE.search(text)
        if market == "anytime_td":
            side_label, line = "Yes", 0.5
        elif side:
            side_label, line = side.group(1).title(), float(side.group(2).replace(",", "."))
        elif plus and int(plus.group(1)) > 0:
            side_label, line = "Over", int(plus.group(1)) - 0.5
        else:
            continue
        remaining = text[:market_match.start()] + " " + text[market_match.end():]
        if side:
            remaining = SIDE_LINE.sub(" ", remaining, count=1)
        elif plus:
            remaining = PLUS_LINE.sub(" ", remaining, count=1)
        remaining = re.sub(r"^[Oo]\s+(?=[A-Z])", "", remaining)
        remaining = remaining.replace(":", " ")
        name = _clean_name(remaining)
        if not name:
            continue
        return {
            "entry_mode": "structured", "category": "player_prop",
            "description": " ".join(text.split()), "player_name": name,
            "market": market, "side_label": side_label, "line": line,
            "decimal_odds": None,
        }
    return None


def parse_parlay_ticket(text: str) -> dict[str, Any]:
    """Return review-required ticket fields, never an auto-save instruction."""
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    odds_lines = [line for line in lines if not re.search(r"\bboost\b", line, re.I)]
    odds_token = _labeled_value(odds_lines, EXPLICIT_ODDS_LABEL, PRICE) or _labeled_value(odds_lines, ODDS_LABEL, PRICE)
    # A single SGP heading before every selection prices the entire ticket.
    # A heading after an earlier selection is only a subgroup price.
    sgp_indexes = [index for index, line in enumerate(lines) if SGP_LABEL.search(line)]
    if odds_token is None and len(sgp_indexes) == 1:
        sgp_index = sgp_indexes[0]
        if not any(_structured_leg(line) or GAME_MARKET.search(line) for line in lines[:sgp_index]):
            odds_token = _labeled_value([lines[sgp_index]], SGP_LABEL, PRICE)
    combined_odds = _decimal_price(odds_token) if odds_token else None
    stake_token = _labeled_value(lines, STAKE_LABEL, MONEY)
    return_token = _labeled_value(lines, re.compile(r"\b(?:to|net) return\b", re.I), MONEY)
    # Bet365 share tickets place the two amounts below a two-column heading.
    for index, line in enumerate(lines):
        heading = re.sub(r"\bbonus(?:\s+bet)?\b", "", line, flags=re.I)
        if re.fullmatch(r"Wager\s+(?:To|Net) Return", heading.strip(), re.I) and index + 1 < len(lines):
            amounts = re.findall(r"\$\s*(\d+(?:[.,]\d{2})?)(?![\d.,])", lines[index + 1])
            if len(amounts) == 2:
                stake_token = amounts[0]
                return_token = amounts[1]
    stake = float(stake_token.replace(",", ".")) if stake_token else None
    bonus = any(re.search(r"\b(?:bonus|free bet|bet credit)\b", line, re.I) for line in lines)
    cash = any(re.search(r"\bcash (?:bet|wager)\b", line, re.I) for line in lines)
    bet_type = "bonus" if bonus else "cash" if cash or stake is not None else None
    total_return = float(return_token.replace(",", ".")) if return_token else None
    calculated_odds = False
    if combined_odds is None and stake is not None and stake > 0 and total_return is not None:
        implied = total_return / stake + (1 if bet_type == "bonus" else 0)
        if 1 < implied < 10000:
            combined_odds = round(implied, 4)
            calculated_odds = True
    expected = next((int(match.group(1)) for line in lines if (match := re.search(r"\b(\d{1,2})[- ]leg\s+parlay\b", line, re.I))), None)

    legs: list[dict[str, Any]] = []
    used: set[int] = set()
    for index, line in enumerate(lines):
        if index in used or not any(re.search(rf"\b(?:{pattern})\b", line, re.I) for _, pattern in MARKETS):
            continue
        leg = _structured_leg(line)
        companion = None
        if leg is None:
            for nearby in (index - 1, index + 1):
                if nearby < 0 or nearby >= len(lines) or nearby in used:
                    continue
                candidate = lines[nearby]
                if EXPLICIT_ODDS_LABEL.search(candidate) or ODDS_LABEL.search(candidate) or STAKE_LABEL.search(candidate):
                    continue
                if _structured_leg(candidate) is not None:
                    continue  # Repeated market subtitle is not another selection.
                leg = _structured_leg(f"{candidate} {line}" if nearby < index else f"{line} {candidate}")
                if leg:
                    companion = nearby
                    break
        if leg:
            legs.append(leg)
            used.add(index)
            if companion is not None:
                used.add(companion)
        if len(legs) >= 10:
            break

    for index, line in enumerate(lines):
        if len(legs) >= 10:
            break
        if index not in used and GAME_MARKET.search(line) and not (EXPLICIT_ODDS_LABEL.search(line) or ODDS_LABEL.search(line) or STAKE_LABEL.search(line)):
            legs.append({"entry_mode": "free_text", "description": line})
            used.add(index)
        elif index not in used and re.fullmatch(r"[Oo]?\s*(?:Over|Under)\s+\d+(?:[.,]\d+)?\s+Points", line, re.I):
            if index + 1 < len(lines) and lines[index + 1].lower() == "total":
                legs.append({"entry_mode": "free_text", "description": f"{line} (game total)"})
                used.add(index)

    warnings = []
    if calculated_odds:
        formula = "(To Return + Wager) / Wager" if bet_type == "bonus" else "To Return / Wager"
        warnings.append(f"Combined odds calculated from the ticket amounts: {formula} = {combined_odds:g}. Check the rounded payout and any promo terms against your ticket.")
    if bet_type == "cash" and not cash:
        warnings.append("Cash bet selected because no bonus label was read. Check that the screenshot includes the full wager label.")
    if PLUS_LINE.search(text):
        warnings.append("Bet365 N+ minimum selections were converted to equivalent Over (N minus 0.5) lines. Check each converted threshold against your ticket.")
    if combined_odds is None:
        warnings.append("Combined odds were not read. Enter the exact ticket price.")
    if stake is None:
        warnings.append("Stake was not read. Enter the actual stake or bonus value.")
    if bet_type is None:
        warnings.append("Cash versus bonus was not clear. Choose the ticket's bet type.")
    if not legs:
        warnings.append("No complete player-prop legs were recognized. Add the legs manually from the screenshot.")
    elif expected is not None and len(legs) != expected:
        warnings.append(f"Ticket mentions {expected} legs, but only {len(legs)} were recognized. Add or correct the missing legs.")
    if any(leg["entry_mode"] == "free_text" for leg in legs):
        warnings.append("Some game-bet legs are free text. Check their full selections before saving.")
    return {"legs": legs, "combined_odds": combined_odds, "stake": stake, "bet_type": bet_type, "expected_leg_count": expected, "warnings": warnings}
