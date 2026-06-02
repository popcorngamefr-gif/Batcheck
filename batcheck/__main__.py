"""
CLI batcheck.

Usage :
    python -m batcheck                 # scan complet, tableau lisible
    python -m batcheck --json          # sortie JSON normalisee (pour une UI)
    python -m batcheck --deep          # tente cycles/sante iOS via sysdiagnose (lent)
    python -m batcheck --only host     # un seul module (host|ios|android)
"""

from __future__ import annotations

import argparse
import sys

from batcheck.core import scan, BATTERY_FIELDS


_LABELS = {
    "charge_percent": "Charge",
    "cycles": "Cycles",
    "health_percent": "Sante",
    "capacity_now_mah": "Capacite actuelle",
    "design_capacity_mah": "Capacite d'origine",
    "voltage_mv": "Tension",
    "current_ma": "Courant",
    "temperature_c": "Temperature",
    "is_charging": "En charge",
}
_UNITS = {
    "charge_percent": "%", "health_percent": "%",
    "capacity_now_mah": "mAh", "design_capacity_mah": "mAh",
    "voltage_mv": "mV", "current_ma": "mA", "temperature_c": "C",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="batcheck", description=__doc__)
    parser.add_argument("--json", action="store_true", help="sortie JSON brute")
    parser.add_argument("--deep", action="store_true",
                        help="iOS : tente cycles/sante via sysdiagnose (lent)")
    parser.add_argument("--only", choices=["host", "ios", "android"],
                        help="ne lancer qu'un seul module")
    args = parser.parse_args(argv)

    kwargs = dict(include_host=True, include_ios=True, include_android=True, deep=args.deep)
    if args.only:
        kwargs = {f"include_{args.only}": True,
                  "deep": args.deep,
                  **{f"include_{m}": False
                     for m in ("host", "ios", "android") if m != args.only}}

    result = scan(**kwargs)

    if args.json:
        print(result.to_json())
        return 0

    _print_table(result)
    return 0


def _fmt(reading, field_name: str) -> str:
    if field_name in reading.exposed:
        val = getattr(reading, field_name)
        if field_name == "is_charging":
            return "oui" if val else "non"
        unit = _UNITS.get(field_name, "")
        return f"{val}{(' ' + unit) if unit else ''}"
    return "—"


def _print_table(result) -> None:
    print(f"\nbatcheck · {result.host_os} · {result.scanned_at}")
    print("=" * 64)

    if not result.devices:
        print("Aucun appareil detecte.")
    for d in result.devices:
        d.finalize()
        print(f"\n▸ {d.name}  [{d.kind} / {d.transport}]")
        print(f"  id: {d.device_id}")
        for f in BATTERY_FIELDS:
            print(f"    {_LABELS[f]:<20} {_fmt(d, f)}")
        if d.notes:
            for n in d.notes:
                print(f"  · note  : {n}")
        if d.errors:
            for e in d.errors:
                print(f"  ! erreur: {e}")

    if result.module_errors:
        print("\nModules indisponibles :")
        for mod, err in result.module_errors.items():
            print(f"  - {mod}: {err}")
    print()


if __name__ == "__main__":
    sys.exit(main())
