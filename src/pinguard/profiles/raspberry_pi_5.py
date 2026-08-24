"""Raspberry Pi 5 40-pin header profile, in BCM numbering.

Sources: the Raspberry Pi 5 product brief, the BCM2711/RP1 peripheral
documentation and the standard 40-pin header pinout, which has been stable
since the B+.

The Pi is the opposite of the ESP32 family in the way that matters here: there
is no GPIO matrix, so a peripheral is only available on the pins whose alternate
function provides it. Asking for SPI on GPIO22 is not a routing decision, it is
a mistake, and this profile is what lets the registry say so.
"""

from __future__ import annotations

from ..board import BoardProfile, PinSpec
from ..capabilities import Capability

#: The Pi's pads have no open-drain mode and only four pins reach the PWM block,
#: so DIGITAL from capabilities.py would overstate what most of these pins do.
_BASE = frozenset(
    {
        Capability.INPUT,
        Capability.OUTPUT,
        Capability.PULL_UP,
        Capability.PULL_DOWN,
        Capability.INTERRUPT,
    }
)

#: Reserved for the HAT ID EEPROM (I2C0). The firmware probes these at boot to
#: identify an attached HAT; a HAT is entitled to assume nothing else drives them.
_HAT_EEPROM = {0: "ID_SD", 1: "ID_SC"}

_PWM = frozenset({12, 13, 18, 19})
_I2C = {0: "I2C0", 1: "I2C0", 2: "I2C1 SDA", 3: "I2C1 SCL"}
_SPI0 = {7: "SPI0 CE1", 8: "SPI0 CE0", 9: "SPI0 MISO", 10: "SPI0 MOSI", 11: "SPI0 SCLK"}
_SPI1 = {
    16: "SPI1 CE2",
    17: "SPI1 CE1",
    18: "SPI1 CE0",
    19: "SPI1 MISO",
    20: "SPI1 MOSI",
    21: "SPI1 SCLK",
}
_UART = {14: "UART0 TXD", 15: "UART0 RXD"}
_I2S = {18: "PCM CLK", 19: "PCM FS", 20: "PCM DIN", 21: "PCM DOUT"}

#: BCM number -> physical header position. Worth carrying because every wiring
#: mistake I have ever made started with reading one numbering as the other.
_HEADER = {
    2: 3,
    3: 5,
    4: 7,
    14: 8,
    15: 10,
    17: 11,
    18: 12,
    27: 13,
    22: 15,
    23: 16,
    24: 18,
    10: 19,
    9: 21,
    25: 22,
    11: 23,
    8: 24,
    7: 26,
    0: 27,
    1: 28,
    5: 29,
    6: 31,
    12: 32,
    13: 33,
    19: 35,
    16: 36,
    26: 37,
    20: 38,
    21: 40,
}

_CAVEATS = {
    "hat-eeprom": "GPIO0 and GPIO1 are the HAT ID EEPROM bus; the firmware reads "
    "them at boot and HATs assume nothing else drives them",
    "console": "GPIO14 and GPIO15 carry the serial console unless it has been "
    "disabled in config.txt",
    "extra-i2c": "further I2C buses can be moved onto other pins with device tree "
    "overlays; this profile lists the default routing only",
    "no-analog": "the Pi has no ADC or DAC on the header - analog input needs an "
    "external part such as an MCP3008",
    "pull-defaults": "GPIO0-8 power up with a pull-up, GPIO9-27 with a pull-down",
}


def _capabilities(number: int) -> frozenset[Capability]:
    caps = set(_BASE)
    if number in _PWM:
        caps.add(Capability.PWM)
    if number in _I2C:
        caps.add(Capability.I2C)
    if number in _SPI0 or number in _SPI1:
        caps.add(Capability.SPI)
    if number in _UART:
        caps.add(Capability.UART)
    if number in _I2S:
        caps.add(Capability.I2S)
    return frozenset(caps)


def _aliases(number: int) -> tuple[str, ...]:
    names = [name for table in (_I2C, _SPI0, _SPI1, _UART, _I2S) if (name := table.get(number))]
    if number in _HEADER:
        names.append(f"pin {_HEADER[number]}")
    return tuple(names)


def build() -> BoardProfile:
    pins: list[PinSpec] = []
    for number in range(0, 28):
        caveats: list[str] = ["pull-defaults"]
        if number in _HAT_EEPROM:
            caveats.append("hat-eeprom")
        if number in _UART:
            caveats.append("console")
        if number in _I2C:
            caveats.append("extra-i2c")

        pins.append(
            PinSpec(
                number=number,
                capabilities=_capabilities(number),
                reserved_by="hat-eeprom" if number in _HAT_EEPROM else "",
                reserved_reason=(
                    f"HAT identification EEPROM ({_HAT_EEPROM[number]})"
                    if number in _HAT_EEPROM
                    else ""
                ),
                caveats=tuple(caveats),
                aliases=_aliases(number),
                notes="powers up with a pull-up" if number <= 8 else "powers up with a pull-down",
            )
        )

    return BoardProfile(
        name="raspberry-pi-5",
        display_name="Raspberry Pi 5",
        description="Raspberry Pi 5 40-pin header, BCM numbering",
        voltage=3.3,
        pins=tuple(pins),
        caveats=_CAVEATS,
    )
