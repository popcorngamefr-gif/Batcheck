"""
Coeur de batcheck : schema normalise + orchestration des modules.

Idee directrice : chaque module (ios, android, host...) renvoie une liste de
DeviceReading. On ne ment jamais sur ce qui est lisible. Si une donnee n'est pas
exposee par l'appareil, le champ reste None et on le note dans `unavailable`.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


# Les champs "batterie" qu'on cherche a remplir pour chaque appareil.
# Tout est optionnel : un gadget USB lambda n'en remplira aucun, un iPhone en
# remplira beaucoup. C'est justement ce contraste qu'on veut rendre visible.
BATTERY_FIELDS = (
    "charge_percent",      # niveau instantane (0-100)
    "cycles",              # nombre de cycles de charge
    "health_percent",      # capacite actuelle / capacite d'origine * 100
    "capacity_now_mah",    # capacite courante a pleine charge (mAh)
    "design_capacity_mah", # capacite d'origine en sortie d'usine (mAh)
    "voltage_mv",          # tension (mV)
    "current_ma",          # courant instantane (mA), negatif = decharge
    "temperature_c",       # temperature (degres C)
    "is_charging",         # bool
)


@dataclass
class DeviceReading:
    """Une lecture normalisee pour un appareil donne."""

    # --- Identite ---
    device_id: str                       # identifiant stable (serial, udid, "host"...)
    name: str                            # nom lisible ("iPhone de Tristan", "Logitech...")
    kind: str                            # "phone_ios" | "phone_android" | "host" | "hid" | "ups" | "unknown"
    transport: str                       # "usb" | "internal" | "hid" | "bluetooth"
    source_module: str                   # quel module a produit la lecture

    # --- Etat batterie (tout optionnel) ---
    charge_percent: Optional[float] = None
    cycles: Optional[int] = None
    health_percent: Optional[float] = None
    capacity_now_mah: Optional[float] = None
    design_capacity_mah: Optional[float] = None
    voltage_mv: Optional[float] = None
    current_ma: Optional[float] = None
    temperature_c: Optional[float] = None
    is_charging: Optional[bool] = None

    # --- Honnetete ---
    # Champs qu'on a SU lire (utile pour l'UI : "voila ce que cet objet accepte de dire").
    exposed: list[str] = field(default_factory=list)
    # Champs qu'on a cherche mais que l'appareil n'expose pas (avec raison courte).
    unavailable: dict[str, str] = field(default_factory=dict)
    # Avertissements / notes (ex: "FullChargeCapacity bloquee depuis iOS 12.2").
    notes: list[str] = field(default_factory=list)
    # Erreurs non bloquantes rencontrees pour cet appareil.
    errors: list[str] = field(default_factory=list)

    read_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def set(self, field_name: str, value, note: Optional[str] = None) -> None:
        """Renseigne un champ batterie et le marque comme expose."""
        if field_name not in BATTERY_FIELDS:
            raise KeyError(f"Champ inconnu : {field_name}")
        if value is None:
            return
        setattr(self, field_name, value)
        if field_name not in self.exposed:
            self.exposed.append(field_name)
        self.unavailable.pop(field_name, None)
        if note:
            self.notes.append(note)

    def mark_unavailable(self, field_name: str, reason: str) -> None:
        """Note qu'un champ a ete cherche mais n'est pas exposable."""
        if field_name not in BATTERY_FIELDS:
            raise KeyError(f"Champ inconnu : {field_name}")
        if field_name not in self.exposed:
            self.unavailable[field_name] = reason

    def finalize(self) -> "DeviceReading":
        """Complete `unavailable` pour tout champ ni expose ni deja note."""
        for f in BATTERY_FIELDS:
            if f not in self.exposed and f not in self.unavailable:
                self.unavailable[f] = "non expose par l'appareil"
        return self

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanResult:
    """Resultat global d'un scan : tous les appareils + meta."""

    devices: list[DeviceReading] = field(default_factory=list)
    host_os: str = field(default_factory=lambda: f"{platform.system()} {platform.release()}")
    scanned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    module_errors: dict[str, str] = field(default_factory=dict)  # module -> erreur fatale

    def to_dict(self) -> dict:
        return {
            "scanned_at": self.scanned_at,
            "host_os": self.host_os,
            "module_errors": self.module_errors,
            "device_count": len(self.devices),
            "devices": [d.finalize().to_dict() for d in self.devices],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def scan(include_host: bool = True,
         include_ios: bool = True,
         include_android: bool = True,
         deep: bool = False) -> ScanResult:
    """
    Lance tous les modules disponibles et agrege le resultat.

    Chaque module est isole : s'il plante ou si sa dependance manque, on note
    l'erreur dans module_errors et on continue. Aucun module ne peut faire
    tomber le scan entier.

    deep : transmis aux modules qui le supportent (ex: iOS sysdiagnose).
    """
    result = ScanResult()

    # Import paresseux : un module dont la dependance manque ne doit pas
    # empecher les autres de tourner.
    if include_host:
        _run_module(result, "host")
    if include_ios:
        _run_module(result, "ios", deep=deep)
    if include_android:
        _run_module(result, "android")

    return result


def _run_module(result: ScanResult, module_name: str, **kwargs) -> None:
    try:
        mod = __import__(f"batcheck.modules.{module_name}", fromlist=["read"])
    except Exception as exc:  # noqa: BLE001
        result.module_errors[module_name] = f"import impossible : {exc}"
        return

    try:
        # On ne passe que les kwargs que la signature du module accepte,
        # pour rester souple si un module ignore 'deep'.
        import inspect
        accepted = inspect.signature(mod.read).parameters
        call_kwargs = {k: v for k, v in kwargs.items() if k in accepted}
        readings = mod.read(**call_kwargs)
        result.devices.extend(readings)
    except Exception as exc:  # noqa: BLE001
        result.module_errors[module_name] = f"erreur d'execution : {exc}"
