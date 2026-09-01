from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


def parse_args() -> argparse.Namespace:
    """Lit l'adresse de l'ESP32 et les paramètres du diagnostic."""
    parser = argparse.ArgumentParser(description="Teste la capture JPEG d'une ESP32-CAM")
    parser.add_argument("url", nargs="?", default="http://esp32-cam.local/capture")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def resolve_host(url: str) -> tuple[str, str]:
    """Valide l'URL et résout son nom d'hôte."""
    parsed = urlparse(url if "://" in url else f"http://{url}/capture")
    if not parsed.hostname:
        raise ValueError("URL ESP32 invalide.")
    normalized = parsed.geturl()
    if parsed.path in {"", "/"}:
        normalized = normalized.rstrip("/") + "/capture"
    return normalized, socket.gethostbyname(parsed.hostname)


def main() -> int:
    """Vérifie la résolution réseau, la réponse HTTP et le contenu JPEG."""
    args = parse_args()
    try:
        url, address = resolve_host(args.url)
        print(f"ESP32 résolue : {address}")
        response = requests.get(url, timeout=args.timeout)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "image/jpeg" not in content_type.lower() and not response.content.startswith(b"\xff\xd8"):
            raise RuntimeError(f"La réponse n'est pas une image JPEG ({content_type or 'type inconnu'}).")
        print(f"Capture valide : {len(response.content)} octets")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(response.content)
            print(f"Image enregistrée : {args.output}")
        return 0
    except Exception as exc:
        print(f"Diagnostic échoué : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
