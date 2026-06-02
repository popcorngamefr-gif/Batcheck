"""
Serveur local batcheck : pont entre le coeur Python et l'UI web.

Zero dependance (http.server de la stdlib). Le navigateur ne peut pas lire un
iPhone ni lancer adb : c'est CE serveur, qui tourne en local avec l'acces
systeme, qui fait la lecture privilegiee et la sert en JSON a l'UI.

Lancer :
    python server.py
    -> ouvre http://127.0.0.1:8765 dans le navigateur

Routes :
    GET /                -> l'interface web (web/index.html)
    GET /api/scan        -> JSON normalise de tous les appareils
    GET /api/scan?deep=1 -> idem + tentative cycles/sante iOS (lent)
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


def _base_dir() -> str:
    """
    Dossier racine des ressources.
    - En mode "gele" (PyInstaller), les fichiers sont extraits dans sys._MEIPASS.
    - En mode normal, c'est le dossier de ce fichier.
    """
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# En mode normal on s'assure que le package batcheck est importable.
# En mode gele, il est deja embarque dans le binaire.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, _base_dir())

from batcheck.core import scan  # noqa: E402

HOST = "127.0.0.1"
PORT = 8765
WEB_DIR = os.path.join(_base_dir(), "web")


class Handler(BaseHTTPRequestHandler):
    # Logs plus discrets
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[batcheck] {fmt % args}\n")

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path

        if route in ("/", "/index.html"):
            return self._serve_file("index.html", "text/html; charset=utf-8")

        if route == "/api/scan":
            qs = parse_qs(parsed.query)
            deep = qs.get("deep", ["0"])[0] in ("1", "true", "yes")
            return self._serve_scan(deep)

        # Fichiers statiques eventuels dans web/ (css, js separes si besoin)
        safe = os.path.normpath(route).lstrip("/\\")
        candidate = os.path.join(WEB_DIR, safe)
        if os.path.isfile(candidate) and candidate.startswith(WEB_DIR):
            ctype = _guess_type(candidate)
            return self._serve_file(safe, ctype)

        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _serve_scan(self, deep: bool):
        try:
            result = scan(deep=deep)
            payload = result.to_json().encode("utf-8")
            self._send(200, payload, "application/json; charset=utf-8")
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self._send(500, body, "application/json; charset=utf-8")

    def _serve_file(self, relpath: str, ctype: str):
        path = os.path.join(WEB_DIR, relpath)
        try:
            with open(path, "rb") as fh:
                self._send(200, fh.read(), ctype)
        except OSError:
            self._send(404, b"Fichier introuvable", "text/plain; charset=utf-8")

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # UI servie depuis la meme origine : pas de CORS necessaire.
        self.end_headers()
        self.wfile.write(body)


def _guess_type(path: str) -> str:
    if path.endswith(".css"):
        return "text/css; charset=utf-8"
    if path.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if path.endswith(".json"):
        return "application/json; charset=utf-8"
    if path.endswith(".svg"):
        return "image/svg+xml"
    return "application/octet-stream"


def main(open_browser: bool = False):
    # Si le port est deja pris, on en cherche un libre (cas : double lancement).
    global PORT
    server = None
    for candidate in range(PORT, PORT + 10):
        try:
            server = ThreadingHTTPServer((HOST, candidate), Handler)
            PORT = candidate
            break
        except OSError:
            continue
    if server is None:
        print("  Impossible d'ouvrir un port local entre "
              f"{PORT} et {PORT + 9}.")
        return

    url = f"http://{HOST}:{PORT}"
    print(f"\n  batcheck en ligne  ->  {url}")
    print("  (Ctrl+C pour arreter)\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass  # pas de navigateur dispo : l'URL est affichee, c'est suffisant

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  arret.\n")
        server.shutdown()


if __name__ == "__main__":
    main()
