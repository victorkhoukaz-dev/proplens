from app.db.cache import AppSettings
from app.db.settings_store import SettingsStore


def test_settings_round_trip_including_api_key(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    settings = AppSettings(
        bankroll=2500.0,
        kelly_fraction=0.5,
        min_stake=2.0,
        odds_api_key="saved-test-key",
    )

    store.save(settings.to_storage_dict())
    restored = store.load()

    assert restored["bankroll"] == 2500.0
    assert restored["kelly_fraction"] == 0.5
    assert restored["min_stake"] == 2.0
    assert restored["odds_api_key"] == "saved-test-key"


def test_corrupt_settings_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not valid json", encoding="utf-8")

    assert SettingsStore(path).load() == {}
