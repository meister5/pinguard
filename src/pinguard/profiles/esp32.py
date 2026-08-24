"""ESP32 (original) chip profile.

Sources: ESP32 datasheet section 2.2 and the technical reference manual.

The original ESP32 has more sharp edges than the S3: six pins have no output
driver at all, six more belong to the flash, ADC2 stops working once Wi-Fi
starts, and GPIO12 is sampled at reset to choose the flash voltage - pulling it
high on a 3.3V module is a well-known way to make a board stop booting.
"""

from __future__ import annotations

from ..board import BoardProfile, PinSpec
from ..capabilities import BUS, DIGITAL, INPUT_ONLY, Capability

#: GPIO34-39 have no output driver. Configuring one as an output does not fail;
#: the write succeeds and the pin never moves, which is the worst way for a
#: mistake to present itself.
_INPUT_ONLY = frozenset({34, 35, 36, 37, 38, 39})

_FLASH_PINS = {
    6: "SD_CLK",
    7: "SD_DATA_0",
    8: "SD_DATA_1",
    9: "SD_DATA_2",
    10: "SD_DATA_3",
    11: "SD_CMD",
}

_STRAPPING = {
    0: "boot mode select; held low enters download mode",
    2: "must be low or floating at reset",
    5: "SDIO slave timing; has an internal pull-up",
    12: "MTDI/flash voltage select; pulling this high sets VDD_SDIO to 1.8V and "
    "a 3.3V flash will not boot",
    15: "silences the boot log when pulled low; has an internal pull-up",
}

_ADC2 = frozenset({0, 2, 4, 12, 13, 14, 15, 25, 26, 27})
_ADC1 = frozenset({32, 33, 34, 35, 36, 37, 38, 39})
_TOUCH = frozenset({0, 2, 4, 12, 13, 14, 15, 27, 32, 33})
_DAC = {25: "DAC1", 26: "DAC2"}

_CAVEATS = {
    "adc2-wifi": "ADC2 cannot be read while Wi-Fi is active; this is a hardware "
    "limitation, not a driver one",
    "input-only": "GPIO34-39 have no output driver and no internal pull resistors",
    "psram": "GPIO16 and GPIO17 are used by the PSRAM on WROVER modules",
    "console": "GPIO1 and GPIO3 are the default UART0 console; using them means "
    "giving up serial output",
}


def _capabilities(number: int) -> frozenset[Capability]:
    if number in _INPUT_ONLY:
        caps = set(INPUT_ONLY)
        if number in _ADC1:
            caps.add(Capability.ADC)
        return frozenset(caps)

    caps = set(DIGITAL) | set(BUS)
    if number in _ADC1 or number in _ADC2:
        caps.add(Capability.ADC)
    if number in _TOUCH:
        caps.add(Capability.TOUCH)
    if number in _DAC:
        caps.add(Capability.DAC)
    return frozenset(caps)


def build() -> BoardProfile:
    pins: list[PinSpec] = []
    # 20, 24 and 28-31 are not bonded out.
    for number in [*range(0, 20), 21, 22, 23, 25, 26, 27, *range(32, 40)]:
        caveats: list[str] = []
        if number in _ADC2:
            caveats.append("adc2-wifi")
        if number in _INPUT_ONLY:
            caveats.append("input-only")
        if number in (16, 17):
            caveats.append("psram")
        if number in (1, 3):
            caveats.append("console")

        aliases: list[str] = []
        if number in _DAC:
            aliases.append(_DAC[number])
        if number == 21:
            aliases.append("SDA (default)")
        if number == 22:
            aliases.append("SCL (default)")
        if number == 1:
            aliases.append("U0TXD")
        if number == 3:
            aliases.append("U0RXD")

        pins.append(
            PinSpec(
                number=number,
                capabilities=_capabilities(number),
                reserved_by="flash" if number in _FLASH_PINS else "",
                reserved_reason=(
                    f"in-package SPI flash ({_FLASH_PINS[number]})" if number in _FLASH_PINS else ""
                ),
                strapping=_STRAPPING.get(number, ""),
                adc_unit="adc1" if number in _ADC1 else ("adc2" if number in _ADC2 else ""),
                caveats=tuple(caveats),
                aliases=tuple(aliases),
                notes="input only, no output driver" if number in _INPUT_ONLY else "",
            )
        )

    return BoardProfile(
        name="esp32",
        display_name="ESP32",
        description="Espressif ESP32 (original) chip profile",
        voltage=3.3,
        pins=tuple(pins),
        caveats=_CAVEATS,
    )
