"""The example is part of the test suite so it cannot quietly stop working."""

import importlib.util
import sys
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "build_pin_map.py"


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("build_pin_map", EXAMPLE)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules["build_pin_map"] = loaded
    spec.loader.exec_module(loaded)
    yield loaded
    del sys.modules["build_pin_map"]


def test_the_overlay_is_layered_onto_the_chip(module):
    registry = module.build()
    assert registry.profile.name == "handheld"
    assert registry.profile.pin(18).reserved_by == "display"
    assert registry.profile.pin(6).reserved_by == "flash"


def test_the_project_claims_what_it_says_it_does(module):
    registry = module.build()
    assert registry.pin_for("status_led") == 2
    assert registry.pin_for("sensor.sda") == 21
    assert registry.roles() == (
        "button_a",
        "button_b",
        "sensor.scl",
        "sensor.sda",
        "status_led",
    )


def test_both_mistakes_are_caught(module):
    registry = module.build()
    caught = module.show_the_two_mistakes(registry)
    assert len(caught) == 2
    assert "reserved by display" in caught[0]
    assert "ST7789 SCLK" in caught[0]
    assert "GPIO34 does not support output" in caught[1]


def test_a_rejected_claim_leaves_nothing_behind(module):
    registry = module.build()
    before = len(registry)
    module.show_the_two_mistakes(registry)
    assert len(registry) == before
    assert 18 not in registry
    assert 34 not in registry


def test_main_writes_a_header_and_a_map(module, tmp_path, capsys):
    target = tmp_path / "board_pins.h"
    argv = sys.argv
    sys.argv = ["build_pin_map.py", str(target)]
    try:
        assert module.main() == 0
    finally:
        sys.argv = argv

    header = target.read_text(encoding="utf-8")
    assert "inline constexpr int PIN_STATUS_LED = 2;" in header
    assert "static_assert" in header

    from pinguard import persistence

    restored = persistence.load(target.with_suffix(".json"), module.build().profile)
    assert restored.pin_for("status_led") == 2


def test_main_prints_the_report_when_given_no_path(module, capsys):
    argv = sys.argv
    sys.argv = ["build_pin_map.py"]
    try:
        assert module.main() == 0
    finally:
        sys.argv = argv
    out = capsys.readouterr().out
    assert "rejected: GPIO18 is reserved by display" in out
    assert "#pragma once" in out
