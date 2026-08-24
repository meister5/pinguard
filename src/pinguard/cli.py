"""Command line front end.

Everything here is a thin wrapper over the library; the checks live in
``PinRegistry`` so that a project which imports pinguard gets exactly the same
answers as one that shells out to it.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__, export, persistence, profiles
from .board import BoardProfile, Overlay
from .capabilities import Capability
from .errors import PinGuardError, ProfileError
from .registry import PinRegistry

EXIT_OK = 0
EXIT_ERROR = 1


def resolve_profile(name: str, overlay_path: str | None = None) -> BoardProfile:
    """Accept a built-in name or a path to a profile JSON, then layer an overlay."""
    if name and (name.endswith(".json") or Path(name).exists()):
        profile = BoardProfile.load(name)
    else:
        profile = profiles.load(name)
    if overlay_path:
        profile = profile.apply(Overlay.load(overlay_path))
    return profile


def _pin_row(profile: BoardProfile, number: int) -> str:
    spec = profile.pin(number)
    status = f"reserved: {spec.reserved_by}" if spec.reserved else "free"
    caps = ", ".join(spec.capability_names())
    flags = []
    if spec.strapping:
        flags.append("strapping")
    if spec.caveats:
        flags.extend(spec.caveats)
    suffix = f"  ({'; '.join(flags)})" if flags else ""
    return f"  GPIO{number:<3} {status:<24} {caps}{suffix}"


def cmd_profiles(args: argparse.Namespace) -> int:
    for name in profiles.available():
        profile = profiles.load(name)
        print(f"{name:<16} {profile.display_name:<16} {len(profile)} pins  {profile.description}")
    return EXIT_OK


def cmd_pins(args: argparse.Namespace) -> int:
    profile = resolve_profile(args.profile, args.overlay)
    if args.capability:
        capability = Capability(args.capability)
        specs = profile.with_capability(capability, include_reserved=args.all)
        print(f"{profile.display_name or profile.name}: pins supporting {capability.value}")
    else:
        specs = profile.pins if args.all else profile.free()
        print(f"{profile.display_name or profile.name}: {len(specs)} pins")
    for spec in specs:
        print(_pin_row(profile, spec.number))
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    profile = resolve_profile(args.profile, args.overlay)
    spec = profile.pin(args.pin)
    print(f"GPIO{spec.number} on {profile.display_name or profile.name}")
    print(f"  capabilities  {', '.join(spec.capability_names())}")
    if spec.aliases:
        print(f"  also known as {', '.join(spec.aliases)}")
    if spec.adc_unit:
        print(f"  adc unit      {spec.adc_unit}")
    if spec.reserved:
        detail = f" - {spec.reserved_reason}" if spec.reserved_reason else ""
        print(f"  reserved by   {spec.reserved_by}{detail}")
    if spec.strapping:
        print(f"  strapping     {spec.strapping}")
    if spec.notes:
        print(f"  notes         {spec.notes}")
    for code in spec.caveats:
        print(f"  caveat        {profile.caveats.get(code, code)}")
    return EXIT_OK


def cmd_suggest(args: argparse.Namespace) -> int:
    profile = resolve_profile(args.profile, args.overlay)
    registry = PinRegistry(profile)
    picks = registry.suggest(*args.capabilities, count=args.count)
    if not picks:
        wanted = ", ".join(args.capabilities) or "anything"
        print(f"no free pin on {profile.name} supports {wanted}", file=sys.stderr)
        return EXIT_ERROR
    for number in picks:
        print(_pin_row(profile, number).strip())
    return EXIT_OK


def _registry_from_map(args: argparse.Namespace) -> PinRegistry:
    pin_map = persistence.loads(Path(args.map).read_text(encoding="utf-8"))
    name = args.profile or pin_map.profile
    profile = resolve_profile(name, args.overlay)
    return persistence.restore(
        pin_map,
        profile,
        ignore_fingerprint=args.ignore_fingerprint,
    )


def cmd_check(args: argparse.Namespace) -> int:
    registry = _registry_from_map(args)
    print(registry.report())
    if registry.advisories and args.strict:
        print(f"\n{len(registry.advisories)} advisory/advisories, --strict given", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    registry = _registry_from_map(args)
    text = export.render(registry, args.format)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pinguard",
        description="Check GPIO assignments against a board before they reach hardware.",
    )
    parser.add_argument("--version", action="version", version=f"pinguard {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_profile_args(sub: argparse.ArgumentParser, positional: bool = True) -> None:
        if positional:
            sub.add_argument("profile", help="built-in profile name or path to a profile JSON")
        else:
            sub.add_argument("--profile", help="override the profile named in the map")
        sub.add_argument("--overlay", help="board overlay JSON to layer on top")

    listing = subparsers.add_parser("profiles", help="list the built-in board profiles")
    listing.set_defaults(func=cmd_profiles)

    pins = subparsers.add_parser("pins", help="list a board's pins")
    add_profile_args(pins)
    pins.add_argument(
        "--capability", choices=[c.value for c in Capability], help="filter by capability"
    )
    pins.add_argument("--all", action="store_true", help="include pins the board has reserved")
    pins.set_defaults(func=cmd_pins)

    show = subparsers.add_parser("show", help="everything known about one pin")
    add_profile_args(show)
    show.add_argument("pin", type=int)
    show.set_defaults(func=cmd_show)

    suggest = subparsers.add_parser("suggest", help="pick free pins that can do a job")
    add_profile_args(suggest)
    suggest.add_argument("capabilities", nargs="+", choices=[c.value for c in Capability])
    suggest.add_argument("-n", "--count", type=int, default=1)
    suggest.set_defaults(func=cmd_suggest)

    check = subparsers.add_parser("check", help="re-validate a saved pin map")
    check.add_argument("map", help="pin map JSON")
    add_profile_args(check, positional=False)
    check.add_argument("--ignore-fingerprint", action="store_true")
    check.add_argument("--strict", action="store_true", help="treat advisories as failures")
    check.set_defaults(func=cmd_check)

    exporter = subparsers.add_parser("export", help="generate constants from a saved pin map")
    exporter.add_argument("map", help="pin map JSON")
    add_profile_args(exporter, positional=False)
    exporter.add_argument("--ignore-fingerprint", action="store_true")
    exporter.add_argument("-f", "--format", choices=sorted(export.FORMATS), default="cpp")
    exporter.add_argument("-o", "--output", help="write here instead of stdout")
    exporter.set_defaults(func=cmd_export)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (PinGuardError, ProfileError, ValueError) as exc:
        print(f"pinguard: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        print(f"pinguard: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
