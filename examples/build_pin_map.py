"""Assign the pins for a small ESP32 project, and get told when it is wrong.

Run it:

    python examples/build_pin_map.py

The point of the example is the two failures in the middle. Both are the kind of
mistake that produces no error at all on real hardware: one drives a pin the
board already gave to the display, the other configures an input-only pin as an
output and then wonders why the relay never clicks.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pinguard import (  # noqa: E402  # noqa: E402
    CapabilityUnavailable,
    Overlay,
    PinRegistry,
    PinReserved,
    export,
    load_profile,
    persistence,
)

HERE = Path(__file__).resolve().parent


def build() -> PinRegistry:
    """Layer the board's wiring onto the chip, then claim what the project needs."""
    profile = load_profile("esp32").apply(Overlay.load(HERE / "handheld.json"))
    registry = PinRegistry(profile)

    # The obvious ones first.
    registry.claim(2, "status_led", requires=["output"])
    registry.claim(13, "button_a", requires=["input", "pull_up"])
    registry.claim(14, "button_b", requires=["input", "pull_up"])

    # A temperature sensor on I2C. Nothing surprising here.
    registry.claim_bus("i2c", "sensor", sda=21, scl=22)

    return registry


def show_the_two_mistakes(registry: PinRegistry) -> list[str]:
    """Make the failures that hardware would have swallowed."""
    caught: list[str] = []

    # GPIO18 is the display clock on this board. On hardware, driving it makes
    # the screen tear and the SD card time out, and nothing reports an error.
    try:
        registry.claim(18, "buzzer", requires=["output"])
    except PinReserved as exc:
        caught.append(str(exc))

    # GPIO34 has no output driver. gpio_set_level() returns ESP_OK and the pin
    # stays where it was.
    try:
        registry.claim(34, "relay", requires=["output"])
    except CapabilityUnavailable as exc:
        caught.append(str(exc))

    return caught


def main() -> int:
    registry = build()

    print(registry.report())
    print()

    for message in show_the_two_mistakes(registry):
        print(f"rejected: {message}")
    print()

    # Neither failed claim left anything behind.
    relay_pin = registry.suggest("output", count=1)[0]
    registry.claim(relay_pin, "relay", requires=["output"])
    print(f"relay moved to GPIO{relay_pin}, which can actually drive it")
    print()

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    header = export.to_cpp_header(registry)
    if out is not None:
        out.write_text(header, encoding="utf-8")
        persistence.save(registry, out.with_suffix(".json"))
        print(f"wrote {out} and {out.with_suffix('.json')}")
    else:
        print(header)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
