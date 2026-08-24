"""What a pin can be asked to do."""

from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    PULL_UP = "pull_up"
    PULL_DOWN = "pull_down"
    OPEN_DRAIN = "open_drain"
    INTERRUPT = "interrupt"
    ADC = "adc"
    DAC = "dac"
    PWM = "pwm"
    TOUCH = "touch"
    I2C = "i2c"
    SPI = "spi"
    UART = "uart"
    I2S = "i2s"

    def __str__(self) -> str:
        return self.value


#: What most digital pins can do, as a shorthand for building profiles.
DIGITAL = frozenset(
    {
        Capability.INPUT,
        Capability.OUTPUT,
        Capability.PULL_UP,
        Capability.PULL_DOWN,
        Capability.OPEN_DRAIN,
        Capability.INTERRUPT,
        Capability.PWM,
    }
)

#: A pin that can only ever be read. On the ESP32 these have no output driver at
#: all, so configuring one as an output fails silently in hardware - the write
#: succeeds and the pin never moves.
INPUT_ONLY = frozenset({Capability.INPUT, Capability.INTERRUPT})

#: Peripheral roles, which the ESP32 family can route to most pins through the
#: GPIO matrix but which a Raspberry Pi can only do on specific pins.
BUS = frozenset({Capability.I2C, Capability.SPI, Capability.UART, Capability.I2S})


def parse(value: str | Capability) -> Capability:
    if isinstance(value, Capability):
        return value
    try:
        return Capability(value.lower())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in Capability)
        raise ValueError(f"unknown capability {value!r}; expected one of {allowed}") from exc


def parse_all(values: list[str] | tuple[str, ...] | frozenset[str]) -> frozenset[Capability]:
    return frozenset(parse(value) for value in values)
