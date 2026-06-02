"""
Module iOS : iPhone / iPad branche en USB, via pymobiledevice3.

Deux canaux, comme coconutBattery :
  1) LIVE (rapide, sans interaction) : diagnostic relay -> IORegistry IOPMPowerSource.
     Donne tension / courant / temperature / capacite instantanee / niveau.
     LIMITE CONNUE : depuis iOS 12.2, FullChargeCapacity renvoie souvent 100,
     et le cycle count n'est PAS expose proprement par ce canal.

  2) CYCLES + VRAIE SANTE : il faut recuperer un sysdiagnose et parser le log
     BatteryBDC (CSV). C'est lourd a declencher, donc on le tente seulement si
     l'option deep=True est passee (voir read(deep=...)).

Dependance : `pip install pymobiledevice3`. Si absente, le module se signale
proprement sans casser le scan global. Pairing : l'utilisateur doit avoir
accepte "Faire confiance a cet ordinateur" sur le telephone.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Optional

from batcheck.core import DeviceReading

_MISSING_DEP_NOTE = (
    "pymobiledevice3 non installe. Faire : pip install pymobiledevice3, "
    "puis brancher l'iPhone et accepter 'Faire confiance a cet ordinateur'."
)


def _resolve(value):
    """
    pymobiledevice3 v4+ expose certaines fonctions en asynchrone : elles
    renvoient une coroutine. On la deroule ici pour rester compatible avec
    les versions sync ET async, sans planter.
    """
    if inspect.iscoroutine(value):
        return asyncio.run(value)
    return value


def _status(message: str, *, is_error: bool = False) -> DeviceReading:
    """Tuile d'etat du module (pas un appareil reel). Affichee calmement par l'UI."""
    r = DeviceReading(
        device_id="ios:status", name="iOS", kind="module_status",
        transport="usb", source_module="ios",
    )
    (r.errors if is_error else r.notes).append(message)
    return r


def read(deep: bool = False) -> list[DeviceReading]:
    """
    deep=False : lecture live uniquement (rapide).
    deep=True  : tente aussi cycles + sante via sysdiagnose (lent, plusieurs minutes).

    Cette fonction ne leve JAMAIS : toute panne devient une tuile d'etat calme,
    pour ne pas afficher d'erreur rouge alarmante quand rien n'est branche.
    """
    try:
        from pymobiledevice3.usbmux import list_devices
    except Exception:  # noqa: BLE001
        return [_status(_MISSING_DEP_NOTE)]

    try:
        devices = _resolve(list_devices())
    except Exception as exc:  # noqa: BLE001
        return [_status(f"usbmux indisponible (le service est-il lance ?) : {exc}",
                        is_error=True)]

    # Coroutine deja deroulee ; on s'assure que c'est bien iterable.
    try:
        devices = list(devices) if devices else []
    except TypeError:
        devices = []

    if not devices:
        # Aucun iPhone/iPad branche : on l'indique calmement plutot que silence total.
        return [_status("aucun iPhone ou iPad detecte. Branche l'appareil et "
                        "accepte 'Faire confiance a cet ordinateur'.")]

    readings: list[DeviceReading] = []
    for dev in devices:
        udid = getattr(dev, "serial", None) or getattr(dev, "udid", "inconnu")
        readings.append(_read_one(udid, deep=deep))
    return readings


def _read_one(udid: str, deep: bool) -> DeviceReading:
    r = DeviceReading(
        device_id=f"ios:{udid}", name="iPhone/iPad", kind="phone_ios",
        transport="usb", source_module="ios",
    )

    try:
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.diagnostics import DiagnosticsService
    except Exception as exc:  # noqa: BLE001
        r.errors.append(f"import pymobiledevice3 partiel : {exc}")
        return r

    try:
        lockdown = _resolve(create_using_usbmux(serial=udid))
        device_name = _resolve(lockdown.get_value(domain=None, key="DeviceName"))
        if device_name:
            r.name = str(device_name)
    except Exception as exc:  # noqa: BLE001
        r.errors.append(
            "pairing/lockdown impossible. L'iPhone doit etre deverrouille et "
            f"'Faire confiance' accepte. Detail : {exc}"
        )
        return r

    # ---- Canal 1 : LIVE via IORegistry IOPMPowerSource ----
    try:
        diag = DiagnosticsService(lockdown)
        battery = _resolve(diag.get_battery()) or {}
        _map_live_fields(r, battery)
    except Exception as exc:  # noqa: BLE001
        r.errors.append(f"lecture live (diagnostics) echouee : {exc}")

    # Cycles et sante ne sortent pas du canal live sur iOS recent : on le dit.
    if "cycles" not in r.exposed:
        r.mark_unavailable(
            "cycles",
            "non expose par le canal live IORegistry (iOS >= 12.2). "
            "Necessite un sysdiagnose : relancer avec --deep.",
        )
    if "health_percent" not in r.exposed:
        r.mark_unavailable(
            "health_percent",
            "FullChargeCapacity bloquee a 100 via le canal live depuis iOS 12.2.",
        )

    # ---- Canal 2 : CYCLES + SANTE via sysdiagnose (optionnel) ----
    if deep:
        try:
            _read_deep_battery(lockdown, r)
        except Exception as exc:  # noqa: BLE001
            r.errors.append(f"lecture deep (sysdiagnose) echouee : {exc}")

    return r


def _map_live_fields(r: DeviceReading, battery: dict) -> None:
    """
    Mappe le dict IOPMPowerSource vers nos champs normalises.
    Les cles varient selon iOS ; on tente plusieurs alias.
    """
    def pick(*keys):
        for k in keys:
            if k in battery and battery[k] is not None:
                return battery[k]
        return None

    pct = pick("CurrentCapacity", "BatteryCurrentCapacity")
    if isinstance(pct, (int, float)):
        r.set("charge_percent", float(pct))

    volt = pick("Voltage", "AppleRawBatteryVoltage")
    if isinstance(volt, (int, float)):
        r.set("voltage_mv", float(volt))

    amp = pick("InstantAmperage", "Amperage")
    if isinstance(amp, (int, float)):
        r.set("current_ma", float(amp))

    temp = pick("Temperature")
    if isinstance(temp, (int, float)):
        # IOReg renvoie souvent des centiemes de degre Kelvin/Celsius selon les modeles.
        r.set("temperature_c", round(temp / 100, 1) if temp > 1000 else float(temp))

    charging = pick("IsCharging")
    if isinstance(charging, bool):
        r.set("is_charging", charging)

    raw_now = pick("AppleRawCurrentCapacity")
    if isinstance(raw_now, (int, float)):
        r.set("capacity_now_mah", float(raw_now))


def _read_deep_battery(lockdown, r: DeviceReading) -> None:
    """
    Recupere un sysdiagnose et parse le log BatteryBDC pour le cycle count.
    Reimplemente l'approche de 3dnow/BatteryCycleiOS, mais en pull direct.

    NOTE : c'est le chemin lent (le telephone genere l'archive, plusieurs minutes).
    L'API exacte de CrashReports/Sysdiagnose varie selon la version de
    pymobiledevice3 : on encapsule et on remonte une note claire si indisponible.
    """
    try:
        from pymobiledevice3.services.crash_reports import CrashReportsManager
    except Exception as exc:  # noqa: BLE001
        r.notes.append(f"service sysdiagnose indisponible dans cette version : {exc}")
        return

    # Placeholder volontairement explicite : l'extraction reelle du .tar.gz et
    # le parsing du CSV BatteryBDC se branchent ici en v2 (cf. README).
    r.notes.append(
        "Lecture deep prevue : pull sysdiagnose -> extraction BDC_Daily_*.csv -> "
        "champ BatteryCycleCount. A finaliser (voir README, section iOS deep)."
    )
    _ = CrashReportsManager  # garde l'import "utilise" pour le lint
