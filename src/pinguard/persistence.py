"""Saving a pin map and getting the same board back.

The failure this guards against: you save an assignment on one board revision,
move the file to a board whose pins differ, restore it, and drive pins that now
belong to something else. Storing the profile fingerprint alongside the
assignments turns that into a refusal instead of a short circuit.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .board import BoardProfile
from .errors import PersistenceError, PinGuardError
from .registry import Assignment, PinRegistry

#: Bumped only when the on-disk shape changes in a way older readers cannot
#: handle. Refusing an unknown version beats guessing at it.
FORMAT_VERSION = 1


@dataclass(frozen=True)
class PinMap:
    """The serialisable form of a registry."""

    profile: str
    fingerprint: str
    assignments: tuple[Assignment, ...] = ()
    version: int = FORMAT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile": self.profile,
            "fingerprint": self.fingerprint,
            "assignments": [item.to_dict() for item in self.assignments],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PinMap:
        version = int(data.get("version", 0))
        if version != FORMAT_VERSION:
            raise PersistenceError(
                f"pin map format version {version} is not supported by this build "
                f"(expected {FORMAT_VERSION})"
            )
        for key in ("profile", "fingerprint"):
            if key not in data:
                raise PersistenceError(f"pin map is missing {key!r}")
        try:
            assignments = tuple(Assignment.from_dict(item) for item in data.get("assignments", ()))
        except (KeyError, TypeError, ValueError) as exc:
            raise PersistenceError(f"malformed assignment: {exc}") from exc
        return cls(
            profile=str(data["profile"]),
            fingerprint=str(data["fingerprint"]),
            assignments=assignments,
            version=version,
        )

    @classmethod
    def of(cls, registry: PinRegistry) -> PinMap:
        return cls(
            profile=registry.profile.name,
            fingerprint=registry.profile.fingerprint(),
            assignments=registry.assignments,
        )


def dumps(registry: PinRegistry, *, indent: int = 2) -> str:
    return json.dumps(PinMap.of(registry).to_dict(), indent=indent) + "\n"


def loads(text: str) -> PinMap:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PersistenceError(f"pin map is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PersistenceError("pin map must be a JSON object")
    return PinMap.from_dict(data)


def save(registry: PinRegistry, path: str | Path) -> None:
    """Write atomically, so an interrupted save cannot leave a truncated map."""
    target = Path(path)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(dumps(registry), encoding="utf-8")
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise PersistenceError(f"cannot write {target}: {exc}") from exc


def load(
    path: str | Path,
    profile: BoardProfile,
    *,
    ignore_fingerprint: bool = False,
    allow_reserved: bool = False,
) -> PinRegistry:
    """Restore a saved map onto ``profile``, re-checking every claim."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PersistenceError(f"cannot read {path}: {exc}") from exc
    return restore(
        loads(text), profile, ignore_fingerprint=ignore_fingerprint, allow_reserved=allow_reserved
    )


def restore(
    pin_map: PinMap,
    profile: BoardProfile,
    *,
    ignore_fingerprint: bool = False,
    allow_reserved: bool = False,
) -> PinRegistry:
    """Rebuild a registry from a map.

    Every claim goes back through ``PinRegistry.claim``, so a map saved against
    a profile that has since gained a reservation is rejected on load rather
    than silently trusted.
    """
    if pin_map.profile != profile.name and not ignore_fingerprint:
        raise PersistenceError(
            f"this map was saved for profile {pin_map.profile!r}, not {profile.name!r}"
        )
    if pin_map.fingerprint != profile.fingerprint() and not ignore_fingerprint:
        raise PersistenceError(
            f"profile {profile.name!r} has changed since this map was saved "
            f"(saved {pin_map.fingerprint}, current {profile.fingerprint()}). "
            "Re-check the assignments before restoring, or pass ignore_fingerprint=True."
        )

    registry = PinRegistry(profile)
    try:
        registry.apply(pin_map.assignments, allow_reserved=allow_reserved)
    except PinGuardError as exc:
        raise PersistenceError(f"saved map no longer fits this board: {exc}") from exc
    return registry


__all__ = [
    "FORMAT_VERSION",
    "PinMap",
    "dumps",
    "load",
    "loads",
    "restore",
    "save",
]
