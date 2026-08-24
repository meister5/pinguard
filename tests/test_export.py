import re

import pytest

from pinguard import export, profiles
from pinguard.export import MAX_STATIC_ASSERT_PINS, identifier
from pinguard.registry import PinRegistry


@pytest.fixture
def registry():
    registry = PinRegistry(profiles.load("esp32"))
    registry.claim(23, "status_led", requires=["output"], note="active high")
    registry.claim_bus("i2c", "sensor", sda=21, scl=22)
    return registry


def test_identifier_uppercases_and_replaces_punctuation():
    assert identifier("display.sda") == "PIN_DISPLAY_SDA"
    assert identifier("button-a") == "PIN_BUTTON_A"
    assert identifier("led 2") == "PIN_LED_2"


def test_identifier_honours_a_custom_prefix():
    assert identifier("led", prefix="") == "LED"


def test_identifier_will_not_start_with_a_digit():
    assert identifier("2nd_led", prefix="") == "_2ND_LED"


def test_identifier_rejects_a_role_with_nothing_usable():
    with pytest.raises(ValueError, match="no characters"):
        identifier("...")


def test_header_declares_typed_constants(registry):
    header = export.to_cpp_header(registry)
    assert "inline constexpr int PIN_STATUS_LED = 23;" in header
    assert "inline constexpr int PIN_SENSOR_SDA = 21;" in header


def test_header_uses_pragma_once_by_default(registry):
    assert "#pragma once" in export.to_cpp_header(registry)


def test_header_can_use_an_include_guard_instead(registry):
    header = export.to_cpp_header(registry, guard="MY_PINS_H")
    assert "#ifndef MY_PINS_H" in header
    assert header.rstrip().endswith("#endif  // MY_PINS_H")
    assert "#pragma once" not in header


def test_header_wraps_in_a_namespace(registry):
    header = export.to_cpp_header(registry, namespace="board")
    assert "namespace board {" in header
    assert "}  // namespace board" in header


def test_header_can_skip_the_namespace(registry):
    assert "namespace" not in export.to_cpp_header(registry, namespace="")


def test_header_records_the_board_and_fingerprint(registry):
    header = export.to_cpp_header(registry)
    assert "// Board: ESP32" in header
    assert registry.profile.fingerprint() in header


def test_header_comments_carry_the_aliases(registry):
    header = export.to_cpp_header(registry)
    assert "aka SDA (default)" in header


def test_header_carries_the_note(registry):
    assert "active high" in export.to_cpp_header(registry)


def test_static_asserts_cover_every_pair(registry):
    header = export.to_cpp_header(registry)
    asserts = re.findall(r"^static_assert\(", header, flags=re.MULTILINE)
    assert len(asserts) == 3  # 3 pins -> 3 pairs


def test_static_asserts_are_skipped_for_a_single_pin():
    registry = PinRegistry(profiles.load("esp32"))
    registry.claim(23, "led", requires=["output"])
    assert "static_assert" not in export.to_cpp_header(registry)


def test_static_asserts_are_dropped_once_the_header_would_drown_in_them():
    registry = PinRegistry(profiles.load("esp32s3"))
    for index, spec in enumerate(registry.free()[: MAX_STATIC_ASSERT_PINS + 1]):
        registry.claim(spec.number, f"role_{index}")
    header = export.to_cpp_header(registry)
    assert "static_assert" not in header
    assert "pairwise static asserts omitted" in header


def test_colliding_identifiers_are_disambiguated():
    registry = PinRegistry(profiles.load("esp32"))
    registry.claim(23, "led.a", requires=["output"])
    registry.claim(19, "led_a", requires=["output"])
    header = export.to_cpp_header(registry)
    # Assignments come out ordered by pin, so GPIO19 takes the plain name.
    assert "PIN_LED_A = 19;" in header
    assert "PIN_LED_A_2 = 23;" in header


def test_advisories_are_carried_into_the_header():
    registry = PinRegistry(profiles.load("esp32"))
    registry.claim(12, "sensor", requires=["input"])
    header = export.to_cpp_header(registry)
    assert "// Advisories carried over" in header
    assert "1.8V" in header


def test_advisories_can_be_left_out():
    registry = PinRegistry(profiles.load("esp32"))
    registry.claim(12, "sensor", requires=["input"])
    assert "Advisories" not in export.to_cpp_header(registry, include_advisories=False)


def test_an_empty_registry_still_produces_a_valid_header():
    header = export.to_cpp_header(PinRegistry(profiles.load("esp32")))
    assert "#pragma once" in header
    assert "// No pins claimed." in header
    assert "static_assert" not in header


def test_python_module_is_importable(registry, tmp_path):
    module = tmp_path / "board_pins.py"
    module.write_text(export.to_python_module(registry), encoding="utf-8")
    namespace: dict = {}
    exec(compile(module.read_text(encoding="utf-8"), str(module), "exec"), namespace)
    assert namespace["PIN_STATUS_LED"] == 23
    assert namespace["BY_ROLE"]["sensor.sda"] == 21
    assert namespace["BOARD"] == "esp32"


def test_python_module_records_the_fingerprint(registry):
    assert registry.profile.fingerprint() in export.to_python_module(registry)


def test_markdown_has_a_row_per_pin(registry):
    table = export.to_markdown(registry)
    assert table.count("| GPIO") == 3
    assert "`sensor.sda`" in table


def test_markdown_lists_advisories():
    registry = PinRegistry(profiles.load("esp32"))
    registry.claim(12, "sensor", requires=["input"])
    assert "## Advisories" in export.to_markdown(registry)


def test_render_dispatches_by_name(registry):
    assert export.render(registry, "cpp") == export.to_cpp_header(registry)
    assert export.render(registry, "python") == export.to_python_module(registry)
    assert export.render(registry, "markdown") == export.to_markdown(registry)


def test_render_rejects_an_unknown_format(registry):
    with pytest.raises(ValueError, match="unknown format"):
        export.render(registry, "rust")


def test_every_output_ends_with_a_single_newline(registry):
    for fmt in export.FORMATS:
        text = export.render(registry, fmt)
        assert text.endswith("\n")
        assert not text.endswith("\n\n")
