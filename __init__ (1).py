"""
Module Android : telephone branche en USB avec le debogage USB active, via adb.

Aucune dependance Python : on appelle le binaire `adb` du systeme. Si adb n'est
pas installe ou pas dans le PATH, le module se signale proprement.

Ce qu'on lit :
  - `adb shell dumpsys battery` : niveau, tension, temperature, "charge counter"
    (capacite instantanee en mAh selon le niveau courant), etat de charge.
  - `cat /sys/class/power_supply/battery/cycle_count` et `charge_full` :
    cycles + capacite a pleine charge QUAND le constructeur les expose.
    Beaucoup (ex: Samsung) restreignent ces chemins -> on note l'indispo.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from batcheck.core import DeviceReading

_ADB_TIMEOUT = 10


def read() -> list[DeviceReading]:
    if shutil.which("adb") is None:
        placeholder = DeviceReading(
            device_id="android:status", name="Android", kind="module_status",
            transport="usb", source_module="android",
        )
        placeholder.notes.append(
            "adb introuvable dans le PATH. Installer platform-tools, activer le "
            "debogage USB, et accepter l'autorisation sur le telephone."
        )
        return [placeholder]

    serials = _list_devices()
    if not serials:
        placeholder = DeviceReading(
            device_id="android:status", name="Android", kind="module_status",
            transport="usb", source_module="android",
        )
        placeholder.notes.append(
            "aucun Android autorise. Branche le telephone, active le debogage "
            "USB et accepte l'autorisation a l'ecran."
        )
        return [placeholder]

    return [_read_one(serial) for serial in serials]


def _list_devices() -> list[str]:
    out = _adb_raw(["devices"])
    serials: list[str] = []
    if not out:
        return serials
    for line in out.splitlines()[1:]:  # on saute l'entete "List of devices attached"
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":  # ignore "unauthorized"/"offline"
            serials.append(parts[0])
    return serials


def _read_one(serial: str) -> DeviceReading:
    model = _adb_shell(serial, "getprop ro.product.model") or "Android"
    r = DeviceReading(
        device_id=f"android:{serial}", name=model.strip(), kind="phone_android",
        transport="usb", source_module="android",
    )

    # --- dumpsys battery : toujours dispo, donne l'essentiel instantane ---
    dump = _adb_shell(serial, "dumpsys battery") or ""
    fields = _parse_dumpsys(dump)

    if "level" in fields:
        r.set("charge_percent", fields["level"])
    if "voltage" in fields:
        r.set("voltage_mv", fields["voltage"])
    if "temperature" in fields:
        # dumpsys donne la temp en dixiemes de degre C
        r.set("temperature_c", round(fields["temperature"] / 10, 1))
    if "charge counter" in fields:
        # uAh -> mAh ; capacite a l'instant T, depend du niveau courant
        r.set("capacity_now_mah", round(fields["charge counter"] / 1000, 1),
              note="capacite instantanee (depend du niveau de charge actuel)")
    if "status" in fields:
        # 2 = charging dans l'enum BatteryManager
        r.set("is_charging", fields["status"] == 2)

    # --- sysfs : cycles + pleine capacite, si le constructeur expose ---
    cyc = _adb_shell(serial, "cat /sys/class/power_supply/battery/cycle_count")
    if cyc and cyc.strip().isdigit() and int(cyc.strip()) > 0:
        r.set("cycles", int(cyc.strip()))
    else:
        r.mark_unavailable(
            "cycles",
            "chemin sysfs absent ou restreint (frequent : Samsung sans root). "
            "Estimation possible facon AccuBattery en v2.",
        )

    full = _adb_shell(serial, "cat /sys/class/power_supply/battery/charge_full")
    design = _adb_shell(serial, "cat /sys/class/power_supply/battery/charge_full_design")
    full_v = _to_int(full)
    design_v = _to_int(design)
    if full_v:
        r.set("design_capacity_mah", round(design_v / 1000, 1)) if design_v else None
        r.set("capacity_now_mah", round(full_v / 1000, 1),
              note="capacite a pleine charge (sysfs charge_full)")
    if full_v and design_v and design_v:
        r.set("health_percent", round(100 * full_v / design_v, 1))
    elif "health_percent" not in r.exposed:
        r.mark_unavailable("health_percent", "charge_full/charge_full_design non exposes")

    return r


# ---------------------------------------------------------------- utils -----
def _parse_dumpsys(text: str) -> dict:
    """Transforme la sortie 'cle: valeur' de dumpsys battery en dict typed."""
    fields: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.strip().partition(":")
        key = key.strip().lower()
        val = val.strip()
        if val.lstrip("-").isdigit():
            fields[key] = int(val)
    return fields


def _to_int(val: Optional[str]) -> Optional[int]:
    if val and val.strip().lstrip("-").isdigit():
        return int(val.strip())
    return None


def _adb_raw(args: list[str]) -> Optional[str]:
    try:
        res = subprocess.run(
            ["adb", *args], capture_output=True, text=True, timeout=_ADB_TIMEOUT,
        )
        return res.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def _adb_shell(serial: str, command: str) -> Optional[str]:
    return _adb_raw(["-s", serial, "shell", command])
