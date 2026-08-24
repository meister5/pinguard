import json
from dataclasses import replace

import pytest

from pinguard import persistence, profiles
from pinguard.errors import PersistenceError
from pinguard.persistence import FORMAT_VERSION, PinMap
from pinguard.registry import PinRegistry


@pytest.fixture
def esp32():
    return profiles.load("esp32")


@pytest.fixture
def registry(esp32):
    registry = PinRegistry(esp32)
    registry.claim(23, "led", requires=["output"], note="active high")
    registry.claim(21, "sensor.sda", requires=["i2c"])
    registry.claim(22, "sensor.scl", requires=["i2c"])
    return registry


def test_round_trip_in_memory(registry, esp32):
    restored = persistence.restore(persistence.loads(persistence.dumps(registry)), esp32)
    assert restored.assignments == registry.assignments


def test_round_trip_through_a_file(registry, esp32, tmp_path):
    path = tmp_path / "pins.json"
    persistence.save(registry, path)
    restored = persistence.load(path, esp32)
    assert restored.pin_for("led") == 23
    assert restored.assignments == registry.assignments


def test_saved_json_is_readable(registry, tmp_path):
    path = tmp_path / "pins.json"
    persistence.save(registry, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == FORMAT_VERSION
    assert data["profile"] == "esp32"
    assert {item["role"] for item in data["assignments"]} == {"led", "sensor.sda", "sensor.scl"}


def test_save_leaves_no_temporary_file_behind(registry, tmp_path):
    path = tmp_path / "pins.json"
    persistence.save(registry, path)
    assert [item.name for item in tmp_path.iterdir()] == ["pins.json"]


def test_save_overwrites_an_existing_map(registry, esp32, tmp_path):
    path = tmp_path / "pins.json"
    persistence.save(registry, path)
    registry.release("led")
    persistence.save(registry, path)
    assert "led" not in persistence.load(path, esp32)


def test_save_reports_an_unwritable_path(registry, tmp_path):
    with pytest.raises(PersistenceError, match="cannot write"):
        persistence.save(registry, tmp_path / "missing" / "pins.json")


def test_load_reports_a_missing_file(esp32, tmp_path):
    with pytest.raises(PersistenceError, match="cannot read"):
        persistence.load(tmp_path / "absent.json", esp32)


def test_loads_rejects_garbage():
    with pytest.raises(PersistenceError, match="not valid JSON"):
        persistence.loads("{{{")


def test_loads_rejects_a_json_list():
    with pytest.raises(PersistenceError, match="must be a JSON object"):
        persistence.loads("[]")


def test_an_unknown_format_version_is_refused():
    with pytest.raises(PersistenceError, match="version 99"):
        persistence.loads(json.dumps({"version": 99, "profile": "esp32", "fingerprint": "x"}))


def test_a_map_without_a_version_is_refused():
    with pytest.raises(PersistenceError, match="version 0"):
        persistence.loads(json.dumps({"profile": "esp32", "fingerprint": "x"}))


def test_a_map_missing_its_fingerprint_is_refused():
    with pytest.raises(PersistenceError, match="fingerprint"):
        persistence.loads(json.dumps({"version": FORMAT_VERSION, "profile": "esp32"}))


def test_a_malformed_assignment_is_refused():
    payload = {
        "version": FORMAT_VERSION,
        "profile": "esp32",
        "fingerprint": "x",
        "assignments": [{"role": "led"}],
    }
    with pytest.raises(PersistenceError, match="malformed assignment"):
        persistence.loads(json.dumps(payload))


def test_restoring_onto_the_wrong_profile_is_refused(registry):
    with pytest.raises(PersistenceError, match="saved for profile 'esp32'"):
        persistence.restore(PinMap.of(registry), profiles.load("esp32s3"))


def test_restoring_onto_a_changed_board_is_refused(registry, esp32):
    """The failure this whole module exists for."""
    revised = replace(esp32, name="esp32").reserve(23, "display", "backlight")
    with pytest.raises(PersistenceError, match="has changed since this map was saved"):
        persistence.restore(PinMap.of(registry), revised)


def test_the_fingerprint_check_can_be_waived(registry, esp32):
    revised = esp32.reserve(19, "display", "MISO")
    restored = persistence.restore(PinMap.of(registry), revised, ignore_fingerprint=True)
    assert restored.pin_for("led") == 23


def test_waiving_the_fingerprint_still_re_runs_the_checks(registry, esp32):
    revised = esp32.reserve(23, "display", "backlight")
    with pytest.raises(PersistenceError, match="no longer fits"):
        persistence.restore(PinMap.of(registry), revised, ignore_fingerprint=True)


def test_a_reserved_claim_can_be_restored_when_asked(esp32):
    source = PinRegistry(esp32)
    source.claim(6, "custom_flash", allow_reserved=True)
    restored = persistence.restore(PinMap.of(source), esp32, allow_reserved=True)
    assert restored.pin_for("custom_flash") == 6


def test_restoring_a_reserved_claim_fails_by_default(esp32):
    source = PinRegistry(esp32)
    source.claim(6, "custom_flash", allow_reserved=True)
    with pytest.raises(PersistenceError, match="no longer fits"):
        persistence.restore(PinMap.of(source), esp32)


def test_pin_map_of_an_empty_registry(esp32):
    pin_map = PinMap.of(PinRegistry(esp32))
    assert pin_map.assignments == ()
    assert pin_map.fingerprint == esp32.fingerprint()


def test_pin_map_round_trips_through_a_dict(registry):
    original = PinMap.of(registry)
    assert PinMap.from_dict(original.to_dict()) == original


def test_restored_registry_regains_its_advisories(esp32):
    source = PinRegistry(esp32)
    source.claim(12, "sensor", requires=["input"])
    restored = persistence.restore(PinMap.of(source), esp32)
    assert any("strapping" in message for message in restored.conflicts())
