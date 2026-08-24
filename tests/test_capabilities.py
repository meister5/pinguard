import pytest

from pinguard.capabilities import BUS, DIGITAL, INPUT_ONLY, Capability, parse, parse_all


def test_capability_stringifies_to_its_value():
    assert str(Capability.PULL_UP) == "pull_up"
    assert f"{Capability.ADC}" == "adc"


def test_parse_accepts_a_capability_unchanged():
    assert parse(Capability.SPI) is Capability.SPI


def test_parse_is_case_insensitive():
    assert parse("PWM") is Capability.PWM


def test_parse_names_the_alternatives_when_it_fails():
    with pytest.raises(ValueError) as info:
        parse("analog")
    message = str(info.value)
    assert "analog" in message
    assert "adc" in message


def test_parse_all_returns_a_frozenset():
    result = parse_all(["input", "output"])
    assert result == frozenset({Capability.INPUT, Capability.OUTPUT})
    assert isinstance(result, frozenset)


def test_input_only_has_no_output():
    assert Capability.OUTPUT not in INPUT_ONLY
    assert Capability.INPUT in INPUT_ONLY


def test_digital_and_bus_do_not_overlap():
    assert not (DIGITAL & BUS)
