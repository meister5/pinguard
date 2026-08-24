"""Board profiles: what pins exist and what each one can do.

A profile describes the *chip*. An overlay describes what a particular board did
with it - the display bus, the SD card, the keyboard controller. Keeping them
separate matters because the chip's constraints are fixed and well documented,
while a board's wiring changes between revisions and is exactly the thing an
end user needs to be able to correct without touching library code.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .capabilities import Capability, parse_all
from .errors import ProfileError, UnknownPin


@dataclass(frozen=True)
class PinSpec:
    """One pin on the board."""

    number: int
    capabilities: frozenset[Capability] = field(default_factory=frozenset)
    name: str = ""
    reserved_by: str = ""
    reserved_reason: str = ""
    strapping: str = ""  # non-empty means it is a strapping pin; the text says why it matters
    adc_unit: str = ""  # "adc1" / "adc2" where it matters which
    caveats: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    notes: str = ""

    @property
    def reserved(self) -> bool:
        return bool(self.reserved_by)

    @property
    def label(self) -> str:
        return self.name or f"GPIO{self.number}"

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def capability_names(self) -> tuple[str, ...]:
        return tuple(sorted(item.value for item in self.capabilities))

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "number": self.number,
            "capabilities": list(self.capability_names()),
        }
        for key in ("name", "reserved_by", "reserved_reason", "strapping", "adc_unit", "notes"):
            value = getattr(self, key)
            if value:
                data[key] = value
        if self.caveats:
            data["caveats"] = list(self.caveats)
        if self.aliases:
            data["aliases"] = list(self.aliases)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PinSpec:
        if "number" not in data:
            raise ProfileError("every pin needs a number")
        try:
            capabilities = parse_all(data.get("capabilities", []))
        except ValueError as exc:
            raise ProfileError(f"pin {data['number']}: {exc}") from exc
        return cls(
            number=int(data["number"]),
            capabilities=capabilities,
            name=data.get("name", ""),
            reserved_by=data.get("reserved_by", ""),
            reserved_reason=data.get("reserved_reason", ""),
            strapping=data.get("strapping", ""),
            adc_unit=data.get("adc_unit", ""),
            caveats=tuple(data.get("caveats", ())),
            aliases=tuple(data.get("aliases", ())),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class BoardProfile:
    """A named set of pins, plus the caveats that apply to them."""

    name: str
    display_name: str = ""
    description: str = ""
    voltage: float = 3.3
    pins: tuple[PinSpec, ...] = ()
    caveats: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        seen: set[int] = set()
        for pin in self.pins:
            if pin.number in seen:
                raise ProfileError(f"{self.name}: GPIO{pin.number} appears twice")
            seen.add(pin.number)
        object.__setattr__(self, "pins", tuple(sorted(self.pins, key=lambda p: p.number)))

    # -- lookup ----------------------------------------------------------

    def __iter__(self) -> Iterator[PinSpec]:
        return iter(self.pins)

    def __len__(self) -> int:
        return len(self.pins)

    def __contains__(self, number: object) -> bool:
        return any(pin.number == number for pin in self.pins)

    def pin(self, number: int) -> PinSpec:
        for spec in self.pins:
            if spec.number == number:
                return spec
        raise UnknownPin(
            f"{self.display_name or self.name} has no GPIO{number}. "
            f"Available: {', '.join(str(p.number) for p in self.pins[:12])}..."
        )

    def numbers(self) -> tuple[int, ...]:
        return tuple(pin.number for pin in self.pins)

    def free(self) -> tuple[PinSpec, ...]:
        """Pins the board has not already committed to something."""
        return tuple(pin for pin in self.pins if not pin.reserved)

    def with_capability(
        self, capability: Capability, *, include_reserved: bool = False
    ) -> tuple[PinSpec, ...]:
        return tuple(
            pin
            for pin in self.pins
            if pin.supports(capability) and (include_reserved or not pin.reserved)
        )

    # -- composition -----------------------------------------------------

    def reserve(self, number: int, owner: str, reason: str = "") -> BoardProfile:
        """Return a copy with one more pin committed."""
        spec = self.pin(number)
        updated = replace(spec, reserved_by=owner, reserved_reason=reason)
        pins = tuple(updated if p.number == number else p for p in self.pins)
        return replace(self, pins=pins)

    def apply(self, overlay: Overlay) -> BoardProfile:
        """Layer a board's wiring onto a chip profile."""
        profile = self
        for number, (owner, reason) in overlay.reservations.items():
            profile = profile.reserve(number, owner, reason)
        merged = dict(profile.caveats)
        merged.update(overlay.caveats)
        return replace(
            profile,
            name=overlay.name or profile.name,
            display_name=overlay.display_name or profile.display_name,
            description=overlay.description or profile.description,
            caveats=merged,
        )

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "voltage": self.voltage,
            "caveats": dict(self.caveats),
            "pins": [pin.to_dict() for pin in self.pins],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BoardProfile:
        if "name" not in data:
            raise ProfileError("a profile needs a name")
        return cls(
            name=data["name"],
            display_name=data.get("display_name", ""),
            description=data.get("description", ""),
            voltage=float(data.get("voltage", 3.3)),
            pins=tuple(PinSpec.from_dict(item) for item in data.get("pins", [])),
            caveats=dict(data.get("caveats", {})),
        )

    @classmethod
    def load(cls, path: str | Path) -> BoardProfile:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileError(f"{path}: {exc}") from exc
        except OSError as exc:
            raise ProfileError(f"cannot read {path}: {exc}") from exc
        return cls.from_dict(data)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    def fingerprint(self) -> str:
        """A stable hash of the pin layout.

        Stored alongside saved assignments so that restoring a pin map onto a
        different board revision fails loudly instead of quietly driving the
        wrong pins.
        """
        payload = json.dumps(
            [[pin.number, sorted(pin.capability_names()), pin.reserved_by] for pin in self.pins],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Overlay:
    """What a board did with a chip's pins.

    Overlays are data. A board revision that moves the display CS pin is a JSON
    edit, not a code change, which is the difference between a user fixing it in
    a minute and filing an issue.
    """

    name: str = ""
    display_name: str = ""
    description: str = ""
    base: str = ""
    reservations: dict[int, tuple[str, str]] = field(default_factory=dict)
    caveats: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Overlay:
        reservations: dict[int, tuple[str, str]] = {}
        raw = data.get("reserve", {})
        if not isinstance(raw, dict):
            raise ProfileError("'reserve' must be an object keyed by pin number")

        for key, value in raw.items():
            try:
                number = int(key)
            except (TypeError, ValueError) as exc:
                raise ProfileError(f"{key!r} is not a pin number") from exc
            if isinstance(value, str):
                reservations[number] = (value, "")
            elif isinstance(value, dict):
                owner = value.get("owner") or value.get("by")
                if not owner:
                    raise ProfileError(f"pin {number}: a reservation needs an owner")
                reservations[number] = (owner, value.get("reason", ""))
            else:
                raise ProfileError(f"pin {number}: expected an owner name or an object")

        return cls(
            name=data.get("name", ""),
            display_name=data.get("display_name", ""),
            description=data.get("description", ""),
            base=data.get("base", ""),
            reservations=reservations,
            caveats=dict(data.get("caveats", {})),
        )

    @classmethod
    def load(cls, path: str | Path) -> Overlay:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileError(f"{path}: {exc}") from exc
        except OSError as exc:
            raise ProfileError(f"cannot read {path}: {exc}") from exc
        return cls.from_dict(data)

    def owners(self) -> Iterable[str]:
        return {owner for owner, _ in self.reservations.values()}
