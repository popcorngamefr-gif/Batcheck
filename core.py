"""
Module HOST : la batterie de la machine qui fait tourner batcheck.

C'est le cas le plus facile : l'OS expose deja tout. On lit la meme source que
coconutBattery (IOKit sur Mac), /sys/class/power_supply sur Linux, WMI sur Windows.
Aucune dependance externe : on utilise les outils systeme presents par defaut.
"""

from __future__ import annotations

import platform
import subprocess
from typing import Optional

from batcheck.core import DeviceReading


def read() -> list[DeviceReading]:
    system = platform.system()
    if system == "Darwin":
        return _read_macos()
    if system == "Linux":
        return _read_linux()
    if system == "Windows":
        return _read_windows()
    r = DeviceReading(
        device_id="host", name=f"Machine ({system})", kind="host",
        transport="internal", source_module="host",
    )
    r.errors.append(f"OS non supporte par le module host : {system}")
    return [r]


# ---------------------------------------------------------------- macOS -----
def _read_macos() -> list[DeviceReading]:
    r = DeviceReading(
        device_id="host", name="Mac (batterie interne)", kind="host",
        transport="internal", source_module="host",
    )
    try:
        # ioreg expose AppleSmartBattery : meme source que coconutBattery.
        out = subprocess.run(
            ["ioreg", "-r", "-c", "AppleSmartBattery"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        r.errors.append(f"ioreg indisponible : {exc}")
        return [r]

    def grab(key: str) -> Optional[str]:
        # Lignes du type :  "CycleCount" = 253
        for line in out.splitlines():
            if f'"{key}"' in line and "=" in line:
                return line.split("=", 1)[1].strip()
        return None

    cycles = grab("CycleCount")
    if cycles and cycles.isdigit():
        r.set("cycles", int(cycles))

    cur = grab("AppleRawCurrentCapacity") or grab("CurrentCapacity")
    design = grab("DesignCapacity")
    maxcap = grab("AppleRawMaxCapacity") or grab("MaxCapacity")
    if cur and cur.isdigit():
        r.set("capacity_now_mah", int(cur))
    if design and design.isdigit():
        r.set("design_capacity_mah", int(design))
    if maxcap and design and maxcap.isdigit() and design.isdigit() and int(design):
        r.set("health_percent", round(100 * int(maxcap) / int(design), 1))

    volt = grab("Voltage")
    if volt and volt.isdigit():
        r.set("voltage_mv", int(volt))
    amp = grab("InstantAmperage") or grab("Amperage")
    if amp:
        try:
            r.set("current_ma", int(amp))
        except ValueError:
            pass
    charging = grab("IsCharging")
    if charging is not None:
        r.set("is_charging", charging.lower() == "yes")

    return [r]


# ---------------------------------------------------------------- Linux -----
def _read_linux() -> list[DeviceReading]:
    import glob
    import os

    readings: list[DeviceReading] = []
    for path in glob.glob("/sys/class/power_supply/*"):
        ps_type = _cat(os.path.join(path, "type"))
        if ps_type != "Battery":
            continue  # on ignore les adaptateurs secteur

        name = os.path.basename(path)
        r = DeviceReading(
            device_id=f"host:{name}", name=f"Batterie {name}", kind="host",
            transport="internal", source_module="host",
        )

        cap = _cat(os.path.join(path, "capacity"))
        if cap and cap.isdigit():
            r.set("charge_percent", int(cap))

        cyc = _cat(os.path.join(path, "cycle_count"))
        if cyc and cyc.isdigit() and int(cyc) > 0:
            r.set("cycles", int(cyc))
        elif cyc is not None:
            r.mark_unavailable("cycles", "compteur present mais a 0 (souvent non gere)")

        full = _cat(os.path.join(path, "charge_full")) or _cat(os.path.join(path, "energy_full"))
        design = (_cat(os.path.join(path, "charge_full_design"))
                  or _cat(os.path.join(path, "energy_full_design")))
        if full and full.isdigit():
            r.set("capacity_now_mah", round(int(full) / 1000, 1))  # uAh -> mAh
        if design and design.isdigit():
            r.set("design_capacity_mah", round(int(design) / 1000, 1))
        if full and design and full.isdigit() and design.isdigit() and int(design):
            r.set("health_percent", round(100 * int(full) / int(design), 1))

        volt = _cat(os.path.join(path, "voltage_now"))
        if volt and volt.isdigit():
            r.set("voltage_mv", round(int(volt) / 1000, 1))  # uV -> mV
        status = _cat(os.path.join(path, "status"))
        if status:
            r.set("is_charging", status.lower() == "charging")

        readings.append(r)

    if not readings:
        r = DeviceReading(
            device_id="host", name="Machine Linux", kind="host",
            transport="internal", source_module="host",
        )
        r.notes.append("aucune batterie trouvee sous /sys/class/power_supply (machine fixe ?)")
        readings.append(r)
    return readings


def _cat(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


# -------------------------------------------------------------- Windows -----
def _read_windows() -> list[DeviceReading]:
    r = DeviceReading(
        device_id="host", name="PC Windows (batterie interne)", kind="host",
        transport="internal", source_module="host",
    )
    try:
        # Niveau de charge simple via WMI.
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Battery).EstimatedChargeRemaining"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
        if out and out.isdigit():
            r.set("charge_percent", int(out))
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        r.errors.append(f"PowerShell/WMI indisponible : {exc}")

    # Les cycles/sante fiables sous Windows passent par `powercfg /batteryreport`
    # (rapport HTML/XML a parser). A brancher en v2.
    r.mark_unavailable("cycles", "necessite parsing de powercfg /batteryreport (TODO v2)")
    r.mark_unavailable("health_percent", "necessite parsing de powercfg /batteryreport (TODO v2)")
    return [r]
