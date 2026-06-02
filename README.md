# batcheck

Lecture **honnête** de l'état batterie des appareils branchés (machine hôte, iPhone/iPad, Android).
Le principe directeur : ne jamais inventer une donnée. Si un appareil n'expose pas une info,
batcheck le dit clairement (`unavailable`) au lieu de bricoler une valeur fausse.

C'est aussi la base d'un guide ouvert : montrer, appareil par appareil, **ce qu'un objet accepte
de dire sur sa batterie, et ce qui reste une boîte noire**.

## Démarrage rapide (interface web)

```bash
cd batcheck
./run.sh          # macOS / Linux   (ou : run.bat sur Windows)
```

Ça lance le serveur local et ouvre `http://127.0.0.1:8765` dans le navigateur.
Aucune dépendance requise pour lire la machine hôte. Branche un iPhone/Android et
clique sur **scanner**.

Pas envie des scripts ? `python server.py` puis ouvre l'URL à la main.

### Pourquoi un serveur local et pas un site hébergé

Le navigateur n'a pas l'accès système pour parler usbmux (iPhone) ou adb (Android).
C'est donc le backend Python, qui tourne sur ta machine, qui fait la lecture et la
sert en JSON sur `/api/scan`. L'UI ne fait que l'afficher. Tu peux héberger la page
seule quelque part, mais elle sera alors limitée à la lecture directe navigateur
(batterie de la machine + niveau HID), pas les iPhone/Android.

## Installation des lectures avancées

```bash
pip install -r requirements.txt   # pymobiledevice3 pour iOS
# + adb (Android platform-tools) dans le PATH pour Android
```

## Usage CLI (sans interface)

```bash
python -m batcheck                # scan complet, tableau lisible
python -m batcheck --json         # sortie JSON normalisée (pour brancher une UI)
python -m batcheck --only host    # un seul module : host | ios | android
python -m batcheck --deep         # iOS : tente cycles + vraie santé (lent, voir plus bas)
```

## Ce qui est réellement lisible (la réalité technique)

| Appareil | Niveau | Cycles | Santé | Comment |
|---|---|---|---|---|
| Machine hôte (Mac) | oui | **oui** | oui | IOKit `AppleSmartBattery` via `ioreg` |
| Machine hôte (Linux) | oui | si exposé | oui | `/sys/class/power_supply` |
| Machine hôte (Windows) | oui | v2 | v2 | WMI ; cycles via `powercfg /batteryreport` (à parser) |
| iPhone / iPad | oui | **--deep** | --deep | pymobiledevice3 : live + sysdiagnose |
| Android | oui | selon constructeur | selon constructeur | adb : `dumpsys` + sysfs |
| Batterie externe, chargeur, câble | non | non | non | rien n'est exposé via USB |
| Écouteurs, souris, petits gadgets | parfois (%) | non | non | HID `Battery` quand présent |

### Pourquoi ce n'est pas une web app

usbmux/lockdown (iOS) et adb (Android) ont besoin d'un accès système (libusb, pairing record,
daemon adb). Un navigateur en WebHID/WebUSB ne pourra jamais lire un iPhone ni sortir un cycle
count. D'où le choix d'un cœur Python en CLI. Une UI web viendra par-dessus, en lisant le JSON
produit par `--json` (et pas l'USB en direct).

## Le cas iOS en détail

Deux canaux, exactement comme coconutBattery :

1. **Live** (rapide, `python -m batcheck`) : le diagnostic relay lit `IOPMPowerSource` dans
   l'IORegistry du téléphone. Donne tension, courant, température, capacité instantanée, niveau.
   **Limite connue** : depuis iOS 12.2, `FullChargeCapacity` renvoie souvent 100 et le cycle
   count n'est pas exposé par ce canal. batcheck le signale au lieu de mentir.

2. **Deep** (`--deep`, lent) : récupère un sysdiagnose et parse le log `BatteryBDC`
   (`BDC_Daily_*.csv`, champ `BatteryCycleCount`). C'est l'approche de
   [3dnow/BatteryCycleiOS](https://github.com/3dnow/BatteryCycleiOS). Le pull + parsing est
   stubé dans `modules/ios.py` (`_read_deep_battery`) : c'est le premier morceau à finir en v2.

Prérequis iOS : téléphone déverrouillé + « Faire confiance à cet ordinateur » accepté.
iOS ≥ 17 : certains services développeur réclament un tunnel (`pymobiledevice3 remote start-tunnel`).

## Le cas Android en détail

- `adb shell dumpsys battery` : niveau, tension, température, `charge counter` (mAh instantané),
  état de charge. Quasi toujours dispo dès que le débogage USB est autorisé.
- `cat /sys/class/power_supply/battery/cycle_count` et `charge_full` : cycles + capacité pleine,
  **quand le constructeur les expose**. Samsung les restreint souvent (root requis), Pixel récents
  les donnent plus volontiers. Sinon : estimation façon AccuBattery (au programme v2).

## Architecture

```
batcheck/
  server.py          # serveur local (stdlib) : /api/scan + sert l'UI
  run.sh / run.bat   # lanceurs (ouvrent le navigateur)
  requirements.txt   # deps optionnelles (pymobiledevice3)
  web/
    index.html       # console de diagnostic (consomme /api/scan)
  batcheck/
    core.py          # schéma DeviceReading + ScanResult, orchestration isolée
    __main__.py      # CLI (tableau + JSON)
    modules/
      host.py        # macOS / Linux / Windows
      ios.py         # pymobiledevice3 (live + deep)
      android.py     # adb (dumpsys + sysfs)
```

Chaque module expose une seule fonction `read()` qui renvoie une liste de `DeviceReading`.
Pour ajouter un appareil (UPS HID, périphérique HID...), il suffit d'écrire un nouveau module
dans `modules/` et de l'ajouter dans `core.scan()`. Plug-and-play.

Le schéma `DeviceReading` garde trois listes clés pour l'honnêteté :
`exposed` (ce qu'on a su lire), `unavailable` (cherché mais non exposable, avec la raison),
`notes` (limites et avertissements). C'est ce contraste qui fait le sel du guide.

## Feuille de route

- [ ] iOS deep : finir le pull sysdiagnose + parsing CSV `BatteryBDC`
- [ ] Windows : parser `powercfg /batteryreport` pour cycles + santé
- [ ] Module HID : lire le `Battery` usage page des périphériques (souris, casque, UPS)
- [ ] Android : estimation de santé façon AccuBattery quand sysfs est muet
- [ ] UI web qui consomme le JSON de `--json`

## Note licences

Vérifier les conditions de `pymobiledevice3` et des outils référencés avant redistribution.
Ce dépôt n'embarque pas leur code, il les appelle.
