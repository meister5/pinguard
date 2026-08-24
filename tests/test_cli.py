import json
from pathlib import Path

import pytest

from pinguard import persistence, profiles
from pinguard.cli import main, resolve_profile
from pinguard.errors import ProfileError
from pinguard.registry import PinRegistry

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def pin_map(tmp_path):
    registry = PinRegistry(profiles.load("esp32"))
    registry.claim(23, "status_led", requires=["output"])
    registry.claim_bus("i2c", "sensor", sda=21, scl=22)
    path = tmp_path / "pins.json"
    persistence.save(registry, path)
    return path


def test_version(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert "pinguard" in capsys.readouterr().out


def test_no_command_is_a_usage_error():
    with pytest.raises(SystemExit) as info:
        main([])
    assert info.value.code == 2


def test_profiles_lists_every_builtin(capsys):
    code, out, _ = run(capsys, "profiles")
    assert code == 0
    for name in profiles.available():
        assert name in out


def test_pins_defaults_to_free_pins(capsys):
    code, out, _ = run(capsys, "pins", "esp32")
    assert code == 0
    assert "GPIO23" in out
    assert "GPIO6" not in out  # flash


def test_pins_all_includes_the_reserved_ones(capsys):
    code, out, _ = run(capsys, "pins", "esp32", "--all")
    assert code == 0
    assert "reserved: flash" in out


def test_pins_filters_by_capability(capsys):
    code, out, _ = run(capsys, "pins", "raspberry-pi-5", "--capability", "pwm")
    assert code == 0
    assert out.count("GPIO") == 4


def test_pins_rejects_an_unknown_capability():
    with pytest.raises(SystemExit) as info:
        main(["pins", "esp32", "--capability", "analog"])
    assert info.value.code == 2


def test_pins_marks_strapping_and_caveats(capsys):
    _, out, _ = run(capsys, "pins", "esp32", "--all")
    assert "strapping" in out
    assert "adc2-wifi" in out


def test_show_prints_the_detail(capsys):
    code, out, _ = run(capsys, "show", "esp32", "12")
    assert code == 0
    assert "strapping" in out
    assert "1.8V" in out
    assert "adc unit      adc2" in out


def test_show_reports_a_reserved_pin(capsys):
    code, out, _ = run(capsys, "show", "esp32", "6")
    assert code == 0
    assert "reserved by   flash" in out


def test_show_of_a_missing_pin_fails(capsys):
    code, _, err = run(capsys, "show", "esp32", "99")
    assert code == 1
    assert "no GPIO99" in err


def test_show_lists_header_aliases(capsys):
    _, out, _ = run(capsys, "show", "raspberry-pi-5", "2")
    assert "pin 3" in out


def test_suggest_prints_a_usable_pin(capsys):
    code, out, _ = run(capsys, "suggest", "esp32", "output", "-n", "2")
    assert code == 0
    assert len(out.strip().splitlines()) == 2


def test_suggest_fails_when_nothing_qualifies(capsys):
    code, out, err = run(capsys, "suggest", "raspberry-pi-5", "dac")
    assert code == 1
    assert out == ""
    assert "no free pin" in err


def test_check_reports_a_valid_map(capsys, pin_map):
    code, out, _ = run(capsys, "check", str(pin_map))
    assert code == 0
    assert "status_led" in out
    assert "3 pins claimed" in out


def test_check_rejects_a_map_from_another_board(capsys, pin_map):
    code, _, err = run(capsys, "check", str(pin_map), "--profile", "esp32s3")
    assert code == 1
    assert "saved for profile" in err


def test_check_strict_fails_on_advisories(capsys, tmp_path):
    registry = PinRegistry(profiles.load("esp32"))
    registry.claim(12, "sensor", requires=["input"])
    path = tmp_path / "pins.json"
    persistence.save(registry, path)

    assert run(capsys, "check", str(path))[0] == 0
    code, _, err = run(capsys, "check", str(path), "--strict")
    assert code == 1
    assert "advisory" in err


def test_check_notices_a_changed_board(capsys, pin_map):
    data = json.loads(pin_map.read_text(encoding="utf-8"))
    data["fingerprint"] = "0" * 16
    pin_map.write_text(json.dumps(data), encoding="utf-8")

    code, _, err = run(capsys, "check", str(pin_map))
    assert code == 1
    assert "has changed since this map was saved" in err

    assert run(capsys, "check", str(pin_map), "--ignore-fingerprint")[0] == 0


def test_export_writes_a_header_to_stdout(capsys, pin_map):
    code, out, _ = run(capsys, "export", str(pin_map))
    assert code == 0
    assert "inline constexpr int PIN_STATUS_LED = 23;" in out


def test_export_writes_to_a_file(capsys, pin_map, tmp_path):
    target = tmp_path / "pins.h"
    code, out, err = run(capsys, "export", str(pin_map), "-o", str(target))
    assert code == 0
    assert out == ""
    assert "wrote" in err
    assert "PIN_STATUS_LED" in target.read_text(encoding="utf-8")


def test_export_supports_every_format(capsys, pin_map):
    for fmt in ("cpp", "python", "markdown"):
        code, out, _ = run(capsys, "export", str(pin_map), "--format", fmt)
        assert code == 0
        assert "status_led" in out.lower()


def test_export_rejects_an_unknown_format():
    with pytest.raises(SystemExit) as info:
        main(["export", "map.json", "--format", "rust"])
    assert info.value.code == 2


def test_a_missing_map_file_is_reported(capsys, tmp_path):
    code, _, err = run(capsys, "check", str(tmp_path / "absent.json"))
    assert code == 1
    assert "pinguard:" in err


# -- profile resolution --------------------------------------------------


def test_resolve_profile_accepts_a_builtin():
    assert resolve_profile("esp32").name == "esp32"


def test_resolve_profile_accepts_a_file(tmp_path):
    path = tmp_path / "custom.json"
    profiles.load("esp32").save(path)
    assert resolve_profile(str(path)).name == "esp32"


def test_resolve_profile_applies_an_overlay():
    board = resolve_profile("esp32", str(EXAMPLES / "handheld.json"))
    assert board.name == "handheld"
    assert board.pin(18).reserved_by == "display"


def test_resolve_profile_rejects_an_unknown_name():
    with pytest.raises(ProfileError):
        resolve_profile("stm32")


def test_the_overlay_flag_works_end_to_end(capsys):
    code, out, _ = run(capsys, "show", "esp32", "18", "--overlay", str(EXAMPLES / "handheld.json"))
    assert code == 0
    assert "reserved by   display" in out
    assert "ST7789 SCLK" in out
