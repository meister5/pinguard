"""Errors.

Each one names the pin and says why, because the entire point of this library
is to turn a class of silent hardware faults into a message you can read.
"""

from __future__ import annotations


class PinGuardError(Exception):
    """Base class for everything this package raises."""


class UnknownPin(PinGuardError):
    """The board has no such pin, or does not expose it."""


class PinReserved(PinGuardError):
    """The pin is committed to something on the board and cannot be reassigned.

    Flash, PSRAM, the display bus, the keyboard controller. Driving one of these
    is not a logic error that shows up as a wrong value - it is a bus contention
    that can take the board down, or in the flash case, brick the boot.
    """

    def __init__(self, pin: int, owner: str, reason: str = "") -> None:
        self.pin = pin
        self.owner = owner
        self.reason = reason
        detail = f": {reason}" if reason else ""
        super().__init__(f"GPIO{pin} is reserved by {owner}{detail}")


class PinConflict(PinGuardError):
    """Two roles want the same pin."""

    def __init__(self, pin: int, existing: str, requested: str) -> None:
        self.pin = pin
        self.existing = existing
        self.requested = requested
        super().__init__(
            f"GPIO{pin} is already claimed by {existing!r}; {requested!r} cannot have it"
        )


class CapabilityUnavailable(PinGuardError):
    """The pin exists and is free, but cannot do what was asked of it."""

    def __init__(self, pin: int, capability: str, available: tuple[str, ...] = ()) -> None:
        self.pin = pin
        self.capability = capability
        self.available = available
        options = ", ".join(available) if available else "nothing"
        super().__init__(f"GPIO{pin} does not support {capability}; it supports {options}")


class ProfileError(PinGuardError):
    """A board profile or overlay is malformed."""


class PersistenceError(PinGuardError):
    """Stored assignments could not be restored."""
