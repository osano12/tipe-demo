from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import cv2
import httpx
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.ai.pipeline import WastePipeline

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DB_PATH = ROOT / "db" / "app.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
STATIC_DIR = ROOT / "app" / "static"
CAPTURES_DIR = ROOT / "data" / "captures"
LOGGER = logging.getLogger("smart_waste.api")
ALLOWED_LABELS = {"bio", "recyclable", "waste", "inconnu"}


class Runtime:
    """Centralise l'état mutable et les ressources partagées du serveur."""

    def __init__(self) -> None:
        self.camera_mode = os.getenv("CAMERA_MODE", "webcam").lower()
        self.camera_index = int(os.getenv("CAMERA_INDEX", "0"))
        self.esp32_url = os.getenv("ESP32_CAPTURE_URL", "http://esp32-cam.local/capture")
        self.ai_provider = os.getenv("AI_PROVIDER", "ollama").lower()
        self.ai_model = os.getenv("AI_MODEL") or None
        self.state_lock = threading.Lock()
        self.frame_lock = threading.Lock()
        self.analysis_lock = threading.Lock()
        self.last_result = "waiting"
        self.latest_frame = None
        self.camera = None
        self.camera_thread = None
        self.camera_running = False
        self.pipeline: WastePipeline | None = None

    def initialize(self) -> None:
        """Prépare les dossiers, la base, le pipeline et la caméra."""
        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as connection:
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        try:
            self.pipeline = WastePipeline(db_path=ROOT / "db" / "waste_cache.sqlite3", provider=self.ai_provider, model=self.ai_model, gemini_api_key=os.getenv("GEMINI_API_KEY", ""), memory_path=ROOT / "memory_store" / "learned_objects.json", dataset_dir=ROOT / "data" / "dataset")
        except Exception:
            LOGGER.exception("Le pipeline IA n'a pas pu démarrer")
        if self.camera_mode == "webcam":
            self.start_camera()

    def start_camera(self) -> None:
        """Démarre une unique boucle de lecture webcam en arrière-plan."""
        if self.camera_running:
            return
        self.camera = cv2.VideoCapture(self.camera_index)
        if not self.camera.isOpened():
            self.camera.release()
            self.camera = None
            LOGGER.warning("Webcam %s indisponible", self.camera_index)
            return
        self.camera_running = True
        self.camera_thread = threading.Thread(target=self._camera_loop, daemon=True, name="camera-reader")
        self.camera_thread.start()

    def _camera_loop(self) -> None:
        """Conserve seulement la trame webcam la plus récente pour limiter la latence."""
        while self.camera_running and self.camera is not None:
            success, frame = self.camera.read()
            if success:
                with self.frame_lock:
                    self.latest_frame = frame

    def get_frame(self):
        """Retourne une copie sûre de la dernière trame webcam."""
        with self.frame_lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def set_action(self, action: str) -> None:
        """Met à jour atomiquement l'action exposée à l'Arduino."""
        with self.state_lock:
            self.last_result = action

    def shutdown(self) -> None:
        """Arrête proprement la caméra et les connexions persistantes."""
        self.camera_running = False
        if self.camera_thread:
            self.camera_thread.join(timeout=2)
        if self.camera:
            self.camera.release()
        if self.pipeline:
            self.pipeline.close()


runtime = Runtime()


def database_rows(query: str, parameters: tuple = ()) -> list[dict]:
    """Exécute une lecture SQLite courte et retourne des dictionnaires."""
    with sqlite3.connect(DB_PATH, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def process_image(device: str) -> None:
    """Capture, classe et persiste un événement sans bloquer l'API."""
    try:
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        image_file = CAPTURES_DIR / filename
        if runtime.camera_mode == "webcam":
            frame = runtime.get_frame()
            if frame is None or not cv2.imwrite(str(image_file), frame):
                raise RuntimeError("Aucune image webcam disponible.")
        else:
            response = httpx.get(runtime.esp32_url, timeout=8)
            response.raise_for_status()
            image_file.write_bytes(response.content)
        result = runtime.pipeline.classify_frame(image_file) if runtime.pipeline else {"categorie": "inconnu", "confiance": 0.0, "error": "Pipeline IA indisponible"}
        label = str(result.get("categorie", "inconnu")).lower()
        label = label if label in ALLOWED_LABELS else "inconnu"
        confidence = max(0.0, min(1.0, float(result.get("confiance", 0.0))))
        with sqlite3.connect(DB_PATH, timeout=10) as connection:
            connection.execute("INSERT INTO waste_events(timestamp, label, confidence, source, image_path, extra_json) VALUES (?, ?, ?, ?, ?, ?)", (datetime.now(timezone.utc).isoformat(), label, confidence, device, f"/captures/{filename}", json.dumps(result, ensure_ascii=False, default=str)))
        runtime.set_action(label)
    except Exception:
        LOGGER.exception("Échec du traitement d'image")
        runtime.set_action("inconnu")
    finally:
        runtime.analysis_lock.release()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Gère le démarrage et l'arrêt des ressources applicatives."""
    runtime.initialize()
    yield
    runtime.shutdown()


app = FastAPI(title="Poubelle IA - TIPE", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def home():
    """Sert le tableau de bord principal."""
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    """Expose l'état réel des composants principaux."""
    return {"status": "online", "camera": "online" if runtime.camera_mode == "esp32" or runtime.get_frame() is not None else "offline", "camera_mode": runtime.camera_mode, "ai": "online" if runtime.pipeline else "offline", "ai_provider": runtime.ai_provider, "last_action": runtime.last_result, "busy": runtime.analysis_lock.locked()}


@app.get("/api/rank")
def stats():
    """Retourne le nombre d'événements par catégorie."""
    rows = database_rows("SELECT label, COUNT(*) AS count FROM waste_events GROUP BY label")
    return {"items": rows}


@app.get("/api/events")
def events(limit: int = Query(20, ge=1, le=100)):
    """Retourne les événements récents avec une limite bornée."""
    return {"items": database_rows("SELECT * FROM waste_events ORDER BY id DESC LIMIT ?", (limit,))}


@app.post("/api/arduino/event", status_code=202)
def arduino_event(background_tasks: BackgroundTasks):
    """Planifie l'analyse déclenchée par le capteur Arduino."""
    if not runtime.analysis_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Une analyse est déjà en cours.")
    runtime.set_action("processing")
    background_tasks.add_task(process_image, "arduino_r4")
    return {"status": "accepted"}


@app.post("/api/debug/simulate-pir", status_code=202)
def simulate_pir(background_tasks: BackgroundTasks):
    """Planifie une analyse manuelle pour la démonstration."""
    if not runtime.analysis_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Une analyse est déjà en cours.")
    runtime.set_action("processing")
    background_tasks.add_task(process_image, "simulation")
    return {"status": "accepted"}


@app.get("/api/arduino/get_action")
def get_action():
    """Livre une fois la dernière décision de tri à l'Arduino."""
    with runtime.state_lock:
        action = runtime.last_result
        if action not in {"processing", "waiting"}:
            runtime.last_result = "waiting"
    return {"action": action}


@app.get("/api/db/download")
def download_database():
    """Télécharge une copie de la base d'événements."""
    return FileResponse(DB_PATH, filename="app.db", media_type="application/vnd.sqlite3")


@app.get("/camera/stream")
async def camera_stream():
    """Diffuse la webcam ou relaie le flux MJPEG de l'ESP32."""
    if runtime.camera_mode == "esp32":
        async def esp32_frames():
            """Relaie progressivement les octets du flux ESP32."""
            stream_url = runtime.esp32_url.replace("/capture", "/stream")
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", stream_url) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes(8192):
                        yield chunk
        return StreamingResponse(esp32_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    async def webcam_frames():
        """Encode à 20 images par seconde la trame webcam la plus fraîche."""
        while True:
            frame = runtime.get_frame()
            if frame is not None:
                success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if success:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            await asyncio.sleep(0.05)
    return StreamingResponse(webcam_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/captures", StaticFiles(directory=CAPTURES_DIR, check_dir=False), name="captures")


def parse_args() -> argparse.Namespace:
    """Lit les options de lancement local sans Docker."""
    parser = argparse.ArgumentParser(description="Serveur de la poubelle IA")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--camera", choices=["webcam", "esp32"])
    parser.add_argument("--ai", choices=["ollama", "gemini"])
    parser.add_argument("--model")
    return parser.parse_args()


def main() -> None:
    """Applique la configuration CLI et lance Uvicorn."""
    args = parse_args()
    if args.camera:
        runtime.camera_mode = args.camera
    if args.ai:
        runtime.ai_provider = args.ai
    if args.model:
        runtime.ai_model = args.model
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
