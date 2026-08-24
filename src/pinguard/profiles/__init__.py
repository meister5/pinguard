"""Built-in chip profiles.

Only chips whose pin constraints are published and unambiguous live here. Board
wiring - which pin the display CS ended up on, what the keyboard controller
took - belongs in an overlay, because that is the part that changes between
board revisions and that a user has to be able to correct without a release.
"""

from __future__ import annotations

from functools import cache

from ..board import BoardProfile
from ..errors import ProfileError
from . import esp32, esp32s3, raspberry_pi_5

_BUILDERS = {
    "esp32": esp32.build,
    "esp32s3": esp32s3.build,
    "raspberry-pi-5": raspberry_pi_5.build,
}

#: Spellings people actually type.
_ALIASES = {
    "esp32-s3": "esp32s3",
    "esp32_s3": "esp32s3",
    "s3": "esp32s3",
    "rpi5": "raspberry-pi-5",
    "rpi-5": "raspberry-pi-5",
    "pi5": "raspberry-pi-5",
    "raspberry-pi5": "raspberry-pi-5",
    "raspberrypi5": "raspberry-pi-5",
}


def available() -> tuple[str, ...]:
    return tuple(sorted(_BUILDERS))


def canonical_name(name: str) -> str:
    key = name.strip().lower().replace(" ", "-")
    return _ALIASES.get(key, key)


@cache
def _built(key: str) -> BoardProfile:
    return _BUILDERS[key]()


def load(name: str) -> BoardProfile:
    """Look up a built-in profile by name.

    Profiles are immutable, so the same object is handed out every time; anything
    that changes a profile (``reserve``, ``apply``) returns a copy.
    """
    key = canonical_name(name)
    if key not in _BUILDERS:
        raise ProfileError(
            f"no built-in profile named {name!r}; try one of {', '.join(available())}"
        )
    return _built(key)


#: Names used by ``pinguard`` at package level, where "load" alone would be
#: ambiguous next to ``persistence.load``.
available_profiles = available
load_profile = load

__all__ = [
    "available",
    "available_profiles",
    "canonical_name",
    "load",
    "load_profile",
]
