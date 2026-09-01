from __future__ import annotations

import argparse
import os
import platform
import sys

import uvicorn


def parse_args() -> argparse.Namespace:
    """Lit les options communes de lancement Windows et Ubuntu."""
    parser = argparse.ArgumentParser(description="Lance la poubelle IA sur Windows ou Ubuntu")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--camera", choices=["webcam", "esp32"], default="webcam")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--ai", choices=["ollama", "gemini"], default="ollama")
    parser.add_argument("--model")
    parser.add_argument("--esp32-url")
    parser.add_argument("--reload", action="store_true")
    return parser.parse_args()


def validate_environment(args: argparse.Namespace) -> None:
    """Vérifie les prérequis de configuration avant le démarrage."""
    if args.ai == "gemini" and not os.getenv("GEMINI_API_KEY", "").strip():
        raise SystemExit("Erreur : définissez GEMINI_API_KEY avant de lancer le mode Gemini.")
    if args.camera == "esp32" and not (args.esp32_url or os.getenv("ESP32_CAPTURE_URL")):
        raise SystemExit("Erreur : utilisez --esp32-url ou définissez ESP32_CAPTURE_URL.")


def configure_environment(args: argparse.Namespace) -> None:
    """Transmet la configuration commune au serveur avec des variables portables."""
    os.environ["CAMERA_MODE"] = args.camera
    os.environ["CAMERA_INDEX"] = str(args.camera_index)
    os.environ["AI_PROVIDER"] = args.ai
    if args.model:
        os.environ["AI_MODEL"] = args.model
    if args.esp32_url:
        os.environ["ESP32_CAPTURE_URL"] = args.esp32_url


def main() -> None:
    """Détecte le système, valide la configuration et lance le serveur commun."""
    args = parse_args()
    validate_environment(args)
    configure_environment(args)
    system = platform.system()
    if system not in {"Linux", "Windows"}:
        print(f"Avertissement : système {system} non testé.", file=sys.stderr)
    print(f"Poubelle IA · {system} · {args.ai} · caméra {args.camera}")
    print(f"Interface : http://{args.host}:{args.port}")
    uvicorn.run("app.api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
