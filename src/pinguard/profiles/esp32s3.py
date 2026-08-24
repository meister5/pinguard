"""ESP32-S3 chip profile.

Sources: ESP32-S3 datasheet section 2.3 (pin definitions) and the technical
reference manual's IO MUX and strapping chapters. Board-specific wiring is not
here - layer an overlay for that.

The S3 routes most peripherals through the GPIO matrix, so I2C, SPI, UART and
I2S are available on any general-purpose pin rather than a fixed few. What is
*not* flexible is which pins the flash and PSRAM already own, which pins the
bootloader samples at reset, and which ADC unit a pin belongs to.
"""

from __future__ import annotations

from ..board import BoardProfile, PinSpec
from ..capabilities import BUS, DIGITAL, Capability

#: SPI0/SPI1 pins wired to the in-package flash. Driving one of these is not a
#: logic error you can debug - it interferes with instruction fetch.
_FLASH_PINS = {
    26: "SPICS1",
    27: "SPIHD",
    28: "SPIWP",
    29: "SPICS0",
    30: "SPICLK",
    31: "SPIQ",
    32: "SPID",
}

#: Sampled by the ROM bootloader at reset. Usable afterwards, but an external
#: pull in the wrong direction stops the board booting at all.
_STRAPPING = {
    0: "boot mode select; held low enters download mode",
    3: "JTAG signal source select; leave floating unless you mean it",
    45: "VDD_SPI voltage select; pulling high sets the flash rail to 1.8V",
    46: "boot mode and ROM message output; has an internal pull-down",
}

#: Octal-PSRAM parts also consume these. Quad-PSRAM and no-PSRAM parts do not,
#: so they are a caveat rather than a reservation - the module variant decides.
_OCTAL_PSRAM = (33, 34, 35, 36, 37)

_CAVEATS = {
    "adc2-wifi": "ADC2 cannot be read while Wi-Fi is active; the driver returns an error",
    "usb-jtag": "GPIO19 and GPIO20 are the USB D-/D+ lines on boards that expose native USB",
    "octal-psram": "GPIO33-37 are used by the flash/PSRAM bus on modules with octal PSRAM "
    "(ESP32-S3-WROOM-1 N8R8 and similar); check your module variant",
}


def _capabilities(number: int) -> frozenset[Capability]:
    caps = set(DIGITAL) | set(BUS)
    if 1 <= number <= 20:
        caps.add(Capability.ADC)
    if 1 <= number <= 14:
        caps.add(Capability.TOUCH)
    return frozenset(caps)


def _adc_unit(number: int) -> str:
    if 1 <= number <= 10:
        return "adc1"
    if 11 <= number <= 20:
        return "adc2"
    return ""


def build() -> BoardProfile:
    pins: list[PinSpec] = []
    # 22 through 25 are not bonded out on the S3.
    for number in [*range(0, 22), *range(26, 49)]:
        caveats: list[str] = []
        if _adc_unit(number) == "adc2":
            caveats.append("adc2-wifi")
        if number in (19, 20):
            caveats.append("usb-jtag")
        if number in _OCTAL_PSRAM:
            caveats.append("octal-psram")

        aliases: list[str] = []
        if number == 43:
            aliases.append("U0TXD")
        if number == 44:
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
                adc_unit=_adc_unit(number),
                caveats=tuple(caveats),
                aliases=tuple(aliases),
            )
        )

    return BoardProfile(
        name="esp32s3",
        display_name="ESP32-S3",
        description="Espressif ESP32-S3 chip profile (no board wiring applied)",
        voltage=3.3,
        pins=tuple(pins),
        caveats=_CAVEATS,
    )
