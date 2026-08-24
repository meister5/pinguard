"""The part that says no.

A registry holds one board profile and the set of roles that have been given
pins on it. Every claim is checked against three separate questions:

1. does the pin exist on this board?
2. has the board already committed it to something (flash, display, EEPROM)?
3. can the pin actually do what the role needs?

Failing any of them raises. Advisories - strapping pins, ADC2 under Wi-Fi, the
serial console - do not raise, because they are legitimate choices that just
need to be deliberate ones. They are collected and reported instead.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .board import BoardProfile, PinSpec
from .capabilities import Capability, parse
from .errors import (
    CapabilityUnavailable,
    PinConflict,
    PinReserved,
)


@dataclass(frozen=True)
class Assignment:
    """One role holding one pin."""

    pin: int
    role: str
    capabilities: tuple[Capability, ...] = ()
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"pin": self.pin, "role": self.role}
        if self.capabilities:
            data["capabilities"] = [c.value for c in self.capabilities]
        if self.note:
            data["note"] = self.note
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Assignment:
        return cls(
            pin=int(data["pin"]),
            role=str(data["role"]),
            capabilities=tuple(parse(c) for c in data.get("capabilities", ())),
            note=str(data.get("note", "")),
        )


@dataclass(frozen=True)
class Advisory:
    """Something worth knowing about a claim that is not an error."""

    pin: int
    role: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"GPIO{self.pin} ({self.role}): {self.message}"


#: Capabilities a bus role implies for each of its lines. Kept here rather than
#: in the caller so that "claim an I2C bus" means the same thing everywhere.
BUS_LINES: dict[str, tuple[str, ...]] = {
    "i2c": ("sda", "scl"),
    "spi": ("sck", "mosi", "miso", "cs"),
    "uart": ("tx", "rx"),
    "i2s": ("bclk", "lrclk", "din", "dout"),
}


class PinRegistry:
    """Tracks which role owns which pin on one board."""

    def __init__(self, profile: BoardProfile) -> None:
        self.profile = profile
        self._by_pin: dict[int, Assignment] = {}
        self._by_role: dict[str, Assignment] = {}
        self._advisories: list[Advisory] = []

    # -- introspection ---------------------------------------------------

    def __len__(self) -> int:
        return len(self._by_pin)

    def __iter__(self) -> Iterator[Assignment]:
        return iter(sorted(self._by_pin.values(), key=lambda a: a.pin))

    def __contains__(self, item: object) -> bool:
        if isinstance(item, int):
            return item in self._by_pin
        if isinstance(item, str):
            return item in self._by_role
        return False

    @property
    def assignments(self) -> tuple[Assignment, ...]:
        return tuple(self)

    @property
    def advisories(self) -> tuple[Advisory, ...]:
        return tuple(self._advisories)

    def roles(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_role))

    def pin_for(self, role: str) -> int:
        try:
            return self._by_role[role].pin
        except KeyError as exc:
            known = ", ".join(sorted(self._by_role)) or "nothing yet"
            raise KeyError(f"no pin claimed for {role!r}; claimed roles: {known}") from exc

    def role_for(self, pin: int) -> str:
        assignment = self._by_pin.get(pin)
        return assignment.role if assignment else ""

    def free(self) -> tuple[PinSpec, ...]:
        """Pins the board has not committed and no role has claimed."""
        return tuple(pin for pin in self.profile.free() if pin.number not in self._by_pin)

    # -- claiming --------------------------------------------------------

    def claim(
        self,
        pin: int,
        role: str,
        *,
        requires: Iterable[str | Capability] = (),
        allow_reserved: bool = False,
        note: str = "",
    ) -> Assignment:
        """Give ``role`` exclusive use of ``pin``.

        ``requires`` names what the role will do with the pin. Checking it here
        is the difference between finding out at import time and finding out
        because an output pin never moved.
        """
        if not role:
            raise ValueError("a claim needs a role name")

        spec = self.profile.pin(pin)  # raises UnknownPin

        if spec.reserved and not allow_reserved:
            raise PinReserved(pin, spec.reserved_by, spec.reserved_reason)

        existing = self._by_pin.get(pin)
        if existing is not None:
            if existing.role == role:
                return existing
            raise PinConflict(pin, existing.role, role)

        held = self._by_role.get(role)
        if held is not None:
            raise PinConflict(held.pin, role, role)

        wanted = tuple(parse(item) for item in requires)
        for capability in wanted:
            if not spec.supports(capability):
                raise CapabilityUnavailable(pin, capability.value, spec.capability_names())

        assignment = Assignment(pin=pin, role=role, capabilities=wanted, note=note)
        self._by_pin[pin] = assignment
        self._by_role[role] = assignment
        self._record_advisories(spec, assignment, allow_reserved=allow_reserved)
        return assignment

    def claim_bus(
        self,
        kind: str,
        prefix: str,
        **lines: int,
    ) -> tuple[Assignment, ...]:
        """Claim every line of a bus at once, or none of them.

        Partial failure is the thing to avoid here: a half-claimed SPI bus is a
        worse state than a rejected one, so this rolls back on any error.
        """
        capability = parse(kind)
        known = BUS_LINES.get(capability.value)
        if known is not None:
            unexpected = [name for name in lines if name not in known]
            if unexpected:
                raise ValueError(
                    f"{capability.value} has no line called {unexpected[0]!r}; "
                    f"expected {', '.join(known)}"
                )
        if not lines:
            raise ValueError(f"claim_bus({kind!r}) needs at least one line")

        order = known or tuple(lines)
        claimed: list[Assignment] = []
        try:
            for name in order:
                if name not in lines:
                    continue
                claimed.append(self.claim(lines[name], f"{prefix}.{name}", requires=(capability,)))
        except Exception:
            for assignment in claimed:
                self.release(assignment.role)
            raise
        return tuple(claimed)

    def release(self, role: str) -> None:
        """Give a role's pin back. Releasing something unclaimed is not an error."""
        assignment = self._by_role.pop(role, None)
        if assignment is None:
            return
        self._by_pin.pop(assignment.pin, None)
        self._advisories = [item for item in self._advisories if item.role != role]

    def release_pin(self, pin: int) -> None:
        assignment = self._by_pin.get(pin)
        if assignment is not None:
            self.release(assignment.role)

    def clear(self) -> None:
        self._by_pin.clear()
        self._by_role.clear()
        self._advisories.clear()

    # -- suggestions -----------------------------------------------------

    def suggest(
        self,
        *requires: str | Capability,
        count: int = 1,
        avoid_strapping: bool = True,
        avoid_caveats: bool = True,
    ) -> tuple[int, ...]:
        """Pick pins that would satisfy a claim, best first.

        Ordering is deliberate rather than numeric: plain pins come before ones
        carrying a caveat, and strapping pins come last, so the first suggestion
        is the one least likely to cost someone an afternoon.
        """
        wanted = tuple(parse(item) for item in requires)
        candidates = [
            spec for spec in self.free() if all(spec.supports(capability) for capability in wanted)
        ]

        def rank(spec: PinSpec) -> tuple[int, int, int]:
            strapping_penalty = 1 if (spec.strapping and avoid_strapping) else 0
            caveat_penalty = 1 if (spec.caveats and avoid_caveats) else 0
            return (strapping_penalty, caveat_penalty, spec.number)

        candidates.sort(key=rank)
        return tuple(spec.number for spec in candidates[:count])

    def conflicts(self) -> tuple[str, ...]:
        """Every reason to look twice at the current assignment, as plain text."""
        return tuple(str(item) for item in self._advisories)

    # -- state -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.name,
            "fingerprint": self.profile.fingerprint(),
            "assignments": [item.to_dict() for item in self],
        }

    def apply(self, assignments: Iterable[Assignment], *, allow_reserved: bool = False) -> None:
        """Re-apply a saved set of claims, re-running every check."""
        for item in assignments:
            self.claim(
                item.pin,
                item.role,
                requires=item.capabilities,
                allow_reserved=allow_reserved,
                note=item.note,
            )

    def report(self) -> str:
        lines = [f"{self.profile.display_name or self.profile.name} ({len(self)} pins claimed)"]
        for assignment in self:
            spec = self.profile.pin(assignment.pin)
            caps = ", ".join(c.value for c in assignment.capabilities)
            detail = f" [{caps}]" if caps else ""
            lines.append(f"  GPIO{assignment.pin:<3} {assignment.role}{detail}")
            if spec.aliases:
                lines.append(f"          also known as {', '.join(spec.aliases)}")
        if self._advisories:
            lines.append("")
            lines.append("Advisories:")
            lines.extend(f"  {item}" for item in self._advisories)
        return "\n".join(lines)

    # -- internals -------------------------------------------------------

    def _record_advisories(
        self, spec: PinSpec, assignment: Assignment, *, allow_reserved: bool
    ) -> None:
        if spec.strapping:
            self._add(
                spec.number, assignment.role, "strapping", f"strapping pin - {spec.strapping}"
            )
        if spec.reserved and allow_reserved:
            self._add(
                spec.number,
                assignment.role,
                "reserved-override",
                f"claimed over the board's reservation by {spec.reserved_by}"
                + (f" ({spec.reserved_reason})" if spec.reserved_reason else ""),
            )
        for code in spec.caveats:
            message = self.profile.caveats.get(code, code)
            self._add(spec.number, assignment.role, code, message)
        if spec.notes:
            self._add(spec.number, assignment.role, "note", spec.notes)

    def _add(self, pin: int, role: str, code: str, message: str) -> None:
        self._advisories.append(Advisory(pin=pin, role=role, code=code, message=message))


def registry_for(profile: BoardProfile, **claims: int) -> PinRegistry:
    """Convenience constructor: ``registry_for(profile, led=2, button=15)``."""
    registry = PinRegistry(profile)
    for role, pin in claims.items():
        registry.claim(pin, role)
    return registry


__all__ = [
    "Advisory",
    "Assignment",
    "BUS_LINES",
    "PinRegistry",
    "registry_for",
]
