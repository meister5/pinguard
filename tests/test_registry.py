import pytest

from pinguard import profiles
from pinguard.board import BoardProfile, PinSpec
from pinguard.capabilities import DIGITAL, Capability
from pinguard.errors import (
    CapabilityUnavailable,
    PinConflict,
    PinReserved,
    UnknownPin,
)
from pinguard.registry import Assignment, PinRegistry, registry_for


@pytest.fixture
def esp32():
    return profiles.load("esp32")


@pytest.fixture
def registry(esp32):
    return PinRegistry(esp32)


def test_claim_records_the_assignment(registry):
    assignment = registry.claim(4, "led", requires=["output"])
    assert assignment == Assignment(4, "led", (Capability.OUTPUT,), "")
    assert registry.pin_for("led") == 4
    assert registry.role_for(4) == "led"
    assert len(registry) == 1
    assert 4 in registry
    assert "led" in registry


def test_claim_requires_a_role_name(registry):
    with pytest.raises(ValueError, match="needs a role"):
        registry.claim(4, "")


def test_claim_of_a_missing_pin(registry):
    with pytest.raises(UnknownPin):
        registry.claim(99, "led")


def test_claim_of_a_flash_pin_is_refused(registry):
    with pytest.raises(PinReserved) as info:
        registry.claim(6, "led", requires=["output"])
    assert info.value.owner == "flash"
    assert info.value.pin == 6
    assert 6 not in registry


def test_a_reserved_pin_can_be_taken_deliberately(registry):
    registry.claim(6, "custom_flash", allow_reserved=True)
    assert registry.pin_for("custom_flash") == 6
    codes = {item.code for item in registry.advisories}
    assert "reserved-override" in codes


def test_output_on_an_input_only_pin_is_refused(registry):
    with pytest.raises(CapabilityUnavailable) as info:
        registry.claim(34, "relay", requires=["output"])
    assert info.value.capability == "output"
    assert "input" in info.value.available
    assert 34 not in registry


def test_input_on_an_input_only_pin_is_fine(registry):
    registry.claim(34, "sense", requires=["input", "adc"])
    assert registry.pin_for("sense") == 34


def test_two_roles_cannot_share_a_pin(registry):
    registry.claim(4, "led")
    with pytest.raises(PinConflict) as info:
        registry.claim(4, "buzzer")
    assert info.value.existing == "led"
    assert info.value.requested == "buzzer"


def test_reclaiming_the_same_pin_for_the_same_role_is_a_no_op(registry):
    first = registry.claim(4, "led", requires=["output"])
    second = registry.claim(4, "led")
    assert first is second
    assert len(registry) == 1


def test_one_role_cannot_hold_two_pins(registry):
    registry.claim(4, "led")
    with pytest.raises(PinConflict):
        registry.claim(5, "led")


def test_release_frees_the_pin_and_the_role(registry):
    registry.claim(4, "led")
    registry.release("led")
    assert 4 not in registry
    assert "led" not in registry
    registry.claim(4, "buzzer")


def test_release_of_an_unclaimed_role_is_silent(registry):
    registry.release("nothing")


def test_release_pin(registry):
    registry.claim(4, "led")
    registry.release_pin(4)
    assert registry.roles() == ()
    registry.release_pin(5)


def test_release_drops_the_advisories_that_came_with_it(registry):
    registry.claim(0, "boot_button")
    assert registry.advisories
    registry.release("boot_button")
    assert registry.advisories == ()


def test_clear(registry):
    registry.claim(0, "boot_button")
    registry.claim(4, "led")
    registry.clear()
    assert len(registry) == 0
    assert registry.advisories == ()


def test_pin_for_names_the_known_roles(registry):
    registry.claim(4, "led")
    with pytest.raises(KeyError, match="led"):
        registry.pin_for("buzzer")


def test_role_for_an_unclaimed_pin_is_empty(registry):
    assert registry.role_for(4) == ""


def test_free_excludes_both_reserved_and_claimed(registry):
    before = {pin.number for pin in registry.free()}
    registry.claim(4, "led")
    after = {pin.number for pin in registry.free()}
    assert before - after == {4}
    assert 6 not in before  # flash


def test_iteration_is_ordered_by_pin(registry):
    registry.claim(21, "b")
    registry.claim(4, "a")
    assert [item.pin for item in registry] == [4, 21]


# -- advisories ----------------------------------------------------------


def test_strapping_pins_produce_an_advisory_not_an_error(registry):
    registry.claim(12, "sensor", requires=["input"])
    messages = registry.conflicts()
    assert any("strapping" in message for message in messages)
    assert any("1.8V" in message for message in messages)


def test_caveats_are_expanded_into_readable_text(registry):
    registry.claim(25, "level", requires=["adc"])
    assert any("Wi-Fi" in message for message in registry.conflicts())


def test_a_plain_pin_produces_no_advisory(registry):
    # GPIO23 has no ADC, no touch pad, no strapping role and no boot function.
    registry.claim(23, "led", requires=["output"])
    assert registry.advisories == ()


def test_advisory_stringifies_with_the_pin_and_role(registry):
    registry.claim(0, "boot_button", requires=["input"])
    text = str(registry.advisories[0])
    assert text.startswith("GPIO0 (boot_button):")


# -- buses ---------------------------------------------------------------


def test_claim_bus_claims_every_line(registry):
    claimed = registry.claim_bus("i2c", "display", sda=21, scl=22)
    assert [item.role for item in claimed] == ["display.sda", "display.scl"]
    assert registry.pin_for("display.sda") == 21


def test_claim_bus_orders_lines_conventionally(registry):
    claimed = registry.claim_bus("spi", "tft", cs=5, sck=18, mosi=23, miso=19)
    assert [item.role for item in claimed] == ["tft.sck", "tft.mosi", "tft.miso", "tft.cs"]


def test_claim_bus_rolls_back_when_one_line_fails(registry):
    registry.claim(22, "other")
    with pytest.raises(PinConflict):
        registry.claim_bus("i2c", "display", sda=21, scl=22)
    assert "display.sda" not in registry
    assert 21 not in registry


def test_claim_bus_rejects_an_unknown_line_name(registry):
    with pytest.raises(ValueError, match="no line called"):
        registry.claim_bus("i2c", "display", sda=21, clk=22)


def test_claim_bus_needs_at_least_one_line(registry):
    with pytest.raises(ValueError, match="at least one line"):
        registry.claim_bus("i2c", "display")


def test_claim_bus_on_a_pi_rejects_spi_on_the_wrong_pin():
    registry = PinRegistry(profiles.load("raspberry-pi-5"))
    with pytest.raises(CapabilityUnavailable):
        registry.claim_bus("spi", "tft", sck=22, mosi=23, miso=24, cs=25)
    assert len(registry) == 0


def test_claim_bus_on_a_pi_accepts_spi0():
    registry = PinRegistry(profiles.load("raspberry-pi-5"))
    registry.claim_bus("spi", "tft", sck=11, mosi=10, miso=9, cs=8)
    assert registry.pin_for("tft.sck") == 11


def test_a_bus_kind_outside_the_table_still_works(registry):
    claimed = registry.claim_bus("pwm", "motor", a=4, b=5)
    assert len(claimed) == 2


# -- suggestions ---------------------------------------------------------


def test_suggest_avoids_strapping_and_caveat_pins(registry):
    first = registry.suggest("output", count=1)[0]
    spec = registry.profile.pin(first)
    assert not spec.strapping
    assert not spec.caveats


def test_suggest_returns_the_requested_count(registry):
    picks = registry.suggest("adc", count=3)
    assert len(picks) == 3
    assert len(set(picks)) == 3


def test_suggest_skips_pins_already_claimed(registry):
    first = registry.suggest("output")[0]
    registry.claim(first, "taken")
    assert registry.suggest("output")[0] != first


def test_suggest_returns_nothing_when_nothing_qualifies():
    registry = PinRegistry(profiles.load("raspberry-pi-5"))
    assert registry.suggest("dac") == ()


def test_suggest_falls_back_to_flagged_pins_when_it_must():
    """A board with nothing but strapping pins still gets an answer."""
    board = BoardProfile(
        name="tiny",
        pins=(
            PinSpec(number=0, capabilities=DIGITAL, strapping="boot"),
            PinSpec(number=1, capabilities=DIGITAL, caveats=("console",)),
        ),
        caveats={"console": "serial console"},
    )
    registry = PinRegistry(board)
    assert registry.suggest("output", count=2) == (1, 0)


def test_suggest_can_be_told_not_to_care():
    board = BoardProfile(
        name="tiny",
        pins=(
            PinSpec(number=0, capabilities=DIGITAL, strapping="boot"),
            PinSpec(number=1, capabilities=DIGITAL),
        ),
    )
    registry = PinRegistry(board)
    assert registry.suggest("output", count=2, avoid_strapping=False) == (0, 1)


def test_suggest_with_no_requirements_returns_free_pins(registry):
    assert len(registry.suggest(count=5)) == 5


# -- state ---------------------------------------------------------------


def test_to_dict_carries_the_fingerprint(registry, esp32):
    registry.claim(4, "led", requires=["output"], note="active high")
    data = registry.to_dict()
    assert data["profile"] == "esp32"
    assert data["fingerprint"] == esp32.fingerprint()
    assert data["assignments"] == [
        {"pin": 4, "role": "led", "capabilities": ["output"], "note": "active high"}
    ]


def test_apply_replays_claims_through_the_same_checks(esp32):
    source = PinRegistry(esp32)
    source.claim(4, "led", requires=["output"])
    target = PinRegistry(esp32)
    target.apply(source.assignments)
    assert target.pin_for("led") == 4


def test_apply_rejects_claims_that_no_longer_fit(esp32):
    source = PinRegistry(esp32)
    source.claim(4, "led", requires=["output"])
    tightened = esp32.reserve(4, "display", "backlight")
    with pytest.raises(PinReserved):
        PinRegistry(tightened).apply(source.assignments)


def test_assignment_round_trips_through_a_dict():
    original = Assignment(4, "led", (Capability.OUTPUT,), "active high")
    assert Assignment.from_dict(original.to_dict()) == original


def test_report_lists_pins_aliases_and_advisories(registry):
    registry.claim(21, "sensor.sda", requires=["i2c"])
    registry.claim(12, "sensor.irq", requires=["input"])
    text = registry.report()
    assert "GPIO21" in text
    assert "SDA (default)" in text
    assert "Advisories:" in text
    assert "strapping" in text


def test_report_on_an_empty_registry_still_names_the_board(registry):
    assert "ESP32" in registry.report()


def test_registry_for_is_a_shorthand(esp32):
    registry = registry_for(esp32, led=4, button=13)
    assert registry.pin_for("led") == 4
    assert registry.pin_for("button") == 13
