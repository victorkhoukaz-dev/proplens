import json

from app.db.raw_odds_snapshot_store import RawOddsSnapshotStore


def test_raw_snapshot_preserves_diagnostic_fields_and_redacts_secrets(tmp_path):
    store = RawOddsSnapshotStore(tmp_path / "raw")

    path = store.save(
        bookmaker_responses={
            "bet365": {
                "apiKey": "must-not-survive",
                "fixturePath": "https://example.test/game?apiKey=also-secret&view=all",
                "markets": {
                    "14272": {
                        "outcomes": {
                            "14272": {
                                "players": {
                                    "0": {
                                        "bookmakerOutcomeId": "home/-3.5",
                                        "changedAt": "2026-08-24T00:40:00Z",
                                        "price": 3.5,
                                        "mainLine": False,
                                    }
                                }
                            }
                        }
                    }
                },
            }
        },
        market_catalog_response=[{"marketId": 14272, "marketName": "Handicap"}],
        parsed_market_catalog={"14272": {"handicap": -3.5}},
        request_metadata={"sport_id": 14, "authorization": "secret-header"},
    )

    raw_text = path.read_text(encoding="utf-8")
    saved = json.loads(raw_text)

    assert "must-not-survive" not in raw_text
    assert "also-secret" not in raw_text
    assert "secret-header" not in raw_text
    assert saved["bookmaker_responses"]["bet365"]["apiKey"] == "[REDACTED]"
    player = saved["bookmaker_responses"]["bet365"]["markets"]["14272"]["outcomes"]["14272"]["players"]["0"]
    assert player["bookmakerOutcomeId"] == "home/-3.5"
    assert player["changedAt"] == "2026-08-24T00:40:00Z"
    assert player["price"] == 3.5
    assert player["mainLine"] is False
