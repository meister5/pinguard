"""Invariants that must hold for every built-in profile.

These are deliberately data-driven: adding a new chip profile picks up the whole
suite, so a profile that forgets to mark its flash pins fails here rather than
on someone's desk.
"""

import pytest

from pinguard import profiles
from pinguard.capabilities import Capability
from pinguard.errors import ProfileError

ALL = profiles.available()


@pytest.fixture(params=ALL)
def profile(request):
    return profiles.load(request.param)


def test_every_profile_is_listed():
    assert set(ALL) == {"esp32", "esp32s3", "raspberry-pi-5"}


def test_profiles_have_pins_and_a_display_name(profile):
    assert len(profile) > 0
    assert profile.display_name
    assert profile.description


def test_pin_numbers_are_unique_and_sorted(profile):
    numbers = profile.numbers()
    assert list(numbers) == sorted(numbers)
    assert len(set(numbers)) == len(numbers)


def test_every_pin_can_at_least_be_read(profile):
    for pin in profile:
        assert pin.supports(Capability.INPUT), f"GPIO{pin.number} cannot even be an input"


def test_every_caveat_code_has_text(profile):
    for pin in profile:
        for code in pin.caveats:
            assert code in profile.caveats, f"GPIO{pin.number} cites undefined caveat {code!r}"


def test_reserved_pins_say_why(profile):
    for pin in profile:
        if pin.reserved:
            assert pin.reserved_reason, f"GPIO{pin.number} is reserved without a reason"


def test_adc_unit_is_only_set_on_adc_pins(profile):
    for pin in profile:
        if pin.adc_unit:
            assert pin.supports(Capability.ADC)
        if pin.supports(Capability.ADC):
            assert pin.adc_unit in ("adc1", "adc2", "")


def test_profiles_round_trip_through_json(profile, tmp_path):
    from pinguard.board import BoardProfile

    path = tmp_path / f"{profile.name}.json"
    profile.save(path)
    assert BoardProfile.load(path) == profile


def test_load_returns_the_same_object_each_time():
    assert profiles.load("esp32") is profiles.load("esp32")


def test_aliases_resolve():
    assert profiles.load("esp32-s3").name == "esp32s3"
    assert profiles.load("ESP32_S3").name == "esp32s3"
    assert profiles.load("pi5").name == "raspberry-pi-5"
    assert profiles.load(" RPi5 ").name == "raspberry-pi-5"


def test_unknown_profile_lists_what_is_available():
    with pytest.raises(ProfileError) as info:
        profiles.load("stm32")
    assert "esp32" in str(info.value)


# -- chip specifics ------------------------------------------------------


def test_esp32_flash_pins_are_reserved():
    esp32 = profiles.load("esp32")
    for number in range(6, 12):
        assert esp32.pin(number).reserved_by == "flash"
    assert all(pin.number not in range(6, 12) for pin in esp32.free())


def test_esp32_input_only_pins_cannot_output():
    esp32 = profiles.load("esp32")
    for number in range(34, 40):
        pin = esp32.pin(number)
        assert not pin.supports(Capability.OUTPUT)
        assert not pin.supports(Capability.PULL_UP)
        assert "input only" in pin.notes


def test_esp32_gpio12_is_flagged_as_the_flash_voltage_strap():
    strapping = profiles.load("esp32").pin(12).strapping
    assert "1.8V" in strapping


def test_esp32_dac_pins():
    esp32 = profiles.load("esp32")
    dac = {pin.number for pin in esp32.with_capability(Capability.DAC)}
    assert dac == {25, 26}


def test_esp32_does_not_expose_unbonded_pins():
    esp32 = profiles.load("esp32")
    for absent in (20, 24, 28, 29, 30, 31, 40):
        assert absent not in esp32


def test_esp32s3_flash_pins_are_reserved():
    s3 = profiles.load("esp32s3")
    for number in range(26, 33):
        assert s3.pin(number).reserved_by == "flash"


def test_esp32s3_adc_units_split_at_ten():
    s3 = profiles.load("esp32s3")
    assert s3.pin(1).adc_unit == "adc1"
    assert s3.pin(10).adc_unit == "adc1"
    assert s3.pin(11).adc_unit == "adc2"
    assert s3.pin(20).adc_unit == "adc2"
    assert s3.pin(21).adc_unit == ""


def test_esp32s3_adc2_pins_carry_the_wifi_caveat():
    s3 = profiles.load("esp32s3")
    assert "adc2-wifi" in s3.pin(11).caveats
    assert "adc2-wifi" not in s3.pin(1).caveats


def test_esp32s3_usb_pins_are_flagged_but_usable():
    s3 = profiles.load("esp32s3")
    for number in (19, 20):
        assert "usb-jtag" in s3.pin(number).caveats
        assert not s3.pin(number).reserved


def test_esp32s3_has_no_dac():
    assert profiles.load("esp32s3").with_capability(Capability.DAC) == ()


def test_esp32s3_skips_the_unbonded_middle():
    s3 = profiles.load("esp32s3")
    for absent in (22, 23, 24, 25):
        assert absent not in s3
    assert 48 in s3


def test_pi_has_no_analog():
    pi = profiles.load("raspberry-pi-5")
    assert pi.with_capability(Capability.ADC, include_reserved=True) == ()
    assert pi.with_capability(Capability.DAC, include_reserved=True) == ()


def test_pi_hat_eeprom_pins_are_reserved():
    pi = profiles.load("raspberry-pi-5")
    assert pi.pin(0).reserved_by == "hat-eeprom"
    assert pi.pin(1).reserved_by == "hat-eeprom"


def test_pi_spi_is_only_on_the_pins_that_have_it():
    pi = profiles.load("raspberry-pi-5")
    spi = {pin.number for pin in pi.with_capability(Capability.SPI)}
    assert spi == {7, 8, 9, 10, 11, 16, 17, 18, 19, 20, 21}
    assert not pi.pin(22).supports(Capability.SPI)


def test_pi_pwm_is_only_on_four_pins():
    pi = profiles.load("raspberry-pi-5")
    pwm = {pin.number for pin in pi.with_capability(Capability.PWM)}
    assert pwm == {12, 13, 18, 19}


def test_pi_pins_carry_their_header_position():
    pi = profiles.load("raspberry-pi-5")
    assert "pin 3" in pi.pin(2).aliases
    assert "pin 40" in pi.pin(21).aliases


def test_pi_records_the_power_on_pull_direction():
    pi = profiles.load("raspberry-pi-5")
    assert "pull-up" in pi.pin(4).notes
    assert "pull-down" in pi.pin(17).notes


def test_pi_stops_at_gpio27():
    pi = profiles.load("raspberry-pi-5")
    assert 27 in pi
    assert 28 not in pi
