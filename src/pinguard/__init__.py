"""pinguard - catch GPIO mistakes before they reach hardware.

Microcontroller pin assignment fails quietly. Configuring an ESP32 input-only
pin as an output succeeds and the pin never moves. Driving a flash pin corrupts
instruction fetch. Two libraries claiming the same pin produce a bus conflict
that looks like a flaky sensor. None of these raise; they just behave oddly.

pinguard makes the assignment explicit and checks it:

    >>> from pinguard import PinRegistry, load_profile
    >>> registry = PinRegistry(load_profile("esp32"))
    >>> registry.claim(2, "status_led", requires=["output"])
    Assignment(pin=2, role='status_led', capabilities=(<Capability.OUTPUT: 'output'>,), note='')
    >>> registry.claim(34, "relay", requires=["output"])
    Traceback (most recent call last):
        ...
    pinguard.errors.CapabilityUnavailable: GPIO34 does not support output; it supports adc, input, interrupt

Then export the result so the firmware and the checks cannot disagree.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .board import BoardProfile, Overlay, PinSpec
from .capabilities import BUS, DIGITAL, INPUT_ONLY, Capability
from .errors import (
    CapabilityUnavailable,
    PersistenceError,
    PinConflict,
    PinGuardError,
    PinReserved,
    ProfileError,
    UnknownPin,
)
from .profiles import available_profiles, load_profile
from .registry import Advisory, Assignment, PinRegistry, registry_for

__all__ = [
    "Advisory",
    "Assignment",
    "BUS",
    "BoardProfile",
    "Capability",
    "CapabilityUnavailable",
    "DIGITAL",
    "INPUT_ONLY",
    "Overlay",
    "PersistenceError",
    "PinConflict",
    "PinGuardError",
    "PinRegistry",
    "PinReserved",
    "PinSpec",
    "ProfileError",
    "UnknownPin",
    "__version__",
    "available_profiles",
    "load_profile",
    "registry_for",
]
