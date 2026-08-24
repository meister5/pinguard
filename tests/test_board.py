import json

import pytest

from pinguard.board import BoardProfile, Overlay, PinSpec
from pinguard.capabilities import Capability
from pinguard.errors import ProfileError, UnknownPin


def spec(number, caps=("input", "output"), **kwargs):
    return PinSpec(
        number=number,
        capabilities=frozenset(Capability(c) for c in caps),
        **kwargs,
    )


@pytest.fixture
def profile():
    return BoardProfile(
        name="demo",
        display_name="Demo board",
        pins=(
            spec(0, strapping="boot mode"),
            spec(1, reserved_by="flash", reserved_reason="SPI flash clock"),
            spec(2, caps=("input",), notes="input only"),
            spec(3, caps=("input", "output", "adc"), adc_unit="adc1", aliases=("A0",)),
        ),
    )


def test_pins_are_sorted_regardless_of_input_order():
    unsorted = BoardProfile(name="x", pins=(spec(7), spec(2), spec(5)))
    assert unsorted.numbers() == (2, 5, 7)


def test_duplicate_pin_numbers_are_rejected():
    with pytest.raises(ProfileError, match="GPIO4 appears twice"):
        BoardProfile(name="x", pins=(spec(4), spec(4)))


def test_pin_lookup_and_membership(profile):
    assert profile.pin(3).number == 3
    assert 3 in profile
    assert 9 not in profile
    assert len(profile) == 4
    assert [p.number for p in profile] == [0, 1, 2, 3]


def test_unknown_pin_error_names_the_board(profile):
    with pytest.raises(UnknownPin, match="Demo board has no GPIO9"):
        profile.pin(9)


def test_label_falls_back_to_the_gpio_number(profile):
    assert profile.pin(0).label == "GPIO0"
    assert PinSpec(number=5, name="SCK").label == "SCK"


def test_free_excludes_reserved_pins(profile):
    assert [p.number for p in profile.free()] == [0, 2, 3]


def test_with_capability_skips_reserved_by_default():
    board = BoardProfile(
        name="x",
        pins=(spec(1, reserved_by="flash"), spec(2)),
    )
    assert [p.number for p in board.with_capability(Capability.OUTPUT)] == [2]
    assert [p.number for p in board.with_capability(Capability.OUTPUT, include_reserved=True)] == [
        1,
        2,
    ]


def test_supports(profile):
    assert profile.pin(3).supports(Capability.ADC)
    assert not profile.pin(2).supports(Capability.OUTPUT)


def test_reserve_returns_a_copy_and_leaves_the_original_alone(profile):
    updated = profile.reserve(3, "display", "chip select")
    assert updated.pin(3).reserved_by == "display"
    assert updated.pin(3).reserved_reason == "chip select"
    assert profile.pin(3).reserved is False


def test_round_trip_through_dict_preserves_everything(profile):
    restored = BoardProfile.from_dict(profile.to_dict())
    assert restored == profile


def test_round_trip_through_a_file(profile, tmp_path):
    path = tmp_path / "demo.json"
    profile.save(path)
    assert BoardProfile.load(path) == profile


def test_load_reports_bad_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProfileError):
        BoardProfile.load(path)


def test_load_reports_a_missing_file(tmp_path):
    with pytest.raises(ProfileError, match="cannot read"):
        BoardProfile.load(tmp_path / "absent.json")


def test_from_dict_requires_a_name():
    with pytest.raises(ProfileError, match="needs a name"):
        BoardProfile.from_dict({"pins": []})


def test_pin_from_dict_requires_a_number():
    with pytest.raises(ProfileError, match="needs a number"):
        PinSpec.from_dict({"capabilities": ["input"]})


def test_pin_from_dict_reports_a_bad_capability():
    with pytest.raises(ProfileError, match="pin 3"):
        PinSpec.from_dict({"number": 3, "capabilities": ["analog"]})


def test_to_dict_omits_empty_fields(profile):
    data = profile.pin(0).to_dict()
    assert "reserved_by" not in data
    assert data["strapping"] == "boot mode"


def test_fingerprint_is_stable_across_equal_profiles(profile):
    twin = BoardProfile.from_dict(json.loads(json.dumps(profile.to_dict())))
    assert twin.fingerprint() == profile.fingerprint()


def test_fingerprint_changes_when_a_pin_is_reserved(profile):
    assert profile.reserve(3, "display").fingerprint() != profile.fingerprint()


def test_fingerprint_ignores_cosmetic_text(profile):
    """Renaming the board must not invalidate a saved pin map."""
    from dataclasses import replace

    renamed = replace(profile, display_name="Demo board rev B")
    assert renamed.fingerprint() == profile.fingerprint()


def test_overlay_accepts_a_bare_owner_string():
    overlay = Overlay.from_dict({"reserve": {"3": "display"}})
    assert overlay.reservations == {3: ("display", "")}


def test_overlay_accepts_an_owner_object():
    overlay = Overlay.from_dict({"reserve": {"3": {"owner": "display", "reason": "CS"}}})
    assert overlay.reservations == {3: ("display", "CS")}
    assert set(overlay.owners()) == {"display"}


def test_overlay_rejects_a_reservation_without_an_owner():
    with pytest.raises(ProfileError, match="needs an owner"):
        Overlay.from_dict({"reserve": {"3": {"reason": "CS"}}})


def test_overlay_rejects_a_non_numeric_pin():
    with pytest.raises(ProfileError, match="not a pin number"):
        Overlay.from_dict({"reserve": {"sda": "display"}})


def test_overlay_rejects_a_bad_reserve_block():
    with pytest.raises(ProfileError, match="must be an object"):
        Overlay.from_dict({"reserve": [3, 4]})


def test_apply_reserves_pins_and_merges_caveats(profile):
    overlay = Overlay.from_dict(
        {
            "name": "handheld",
            "display_name": "Handheld",
            "reserve": {"3": {"owner": "display", "reason": "CS"}},
            "caveats": {"shared-spi": "the bus is shared"},
        }
    )
    board = profile.apply(overlay)
    assert board.name == "handheld"
    assert board.display_name == "Handheld"
    assert board.pin(3).reserved_by == "display"
    assert board.caveats["shared-spi"] == "the bus is shared"
    # The chip's own pins are untouched.
    assert board.pin(1).reserved_by == "flash"


def test_apply_over_an_unknown_pin_fails_loudly(profile):
    with pytest.raises(UnknownPin):
        profile.apply(Overlay.from_dict({"reserve": {"40": "display"}}))


def test_overlay_load_round_trip(tmp_path):
    path = tmp_path / "overlay.json"
    path.write_text(json.dumps({"name": "b", "reserve": {"2": "display"}}), encoding="utf-8")
    assert Overlay.load(path).reservations == {2: ("display", "")}


def test_overlay_load_reports_bad_json(tmp_path):
    path = tmp_path / "overlay.json"
    path.write_text("nope", encoding="utf-8")
    with pytest.raises(ProfileError):
        Overlay.load(path)
