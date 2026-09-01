from __future__ import annotations

import base64
import io
import json
import logging
import time
from typing import Any

import requests

from .llm_ollama import build_prompt, extract_first_json, fallback_result, validate_ollama_json

LOGGER = logging.getLogger("ia.llm_gemini")


class GeminiVisionClient:
    """Classe une image avec l'API Gemini et renvoie le format commun du pipeline."""

    def __init__(self, *, api_key: str, model: str = "gemini-2.5-flash", timeout_seconds: float = 60.0, max_image_side: int = 1024, jpeg_quality: int = 85, logger: logging.Logger | None = None) -> None:
        if not api_key.strip():
            raise ValueError("GEMINI_API_KEY est obligatoire avec le fournisseur Gemini.")
        self.api_key = api_key.strip()
        self.model = model
        self.timeout_seconds = float(timeout_seconds)
        self.max_image_side = int(max_image_side)
        self.jpeg_quality = int(jpeg_quality)
        self.logger = logger or LOGGER

    def _encode_image(self, image: Any) -> str:
        """Redimensionne et encode une image PIL en JPEG base64."""
        prepared = image.copy()
        if prepared.mode != "RGB":
            prepared = prepared.convert("RGB")
        prepared.thumbnail((self.max_image_side, self.max_image_side))
        buffer = io.BytesIO()
        prepared.save(buffer, format="JPEG", quality=self.jpeg_quality, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def classify_image(self, image: Any) -> dict[str, Any]:
        """Envoie l'image à Gemini et valide sa réponse JSON."""
        started = time.perf_counter()
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": build_prompt("court")}, {"inline_data": {"mime_type": "image/jpeg", "data": self._encode_image(image)}}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 256},
        }
        try:
            response = requests.post(endpoint, headers={"x-goog-api-key": self.api_key}, json=payload, timeout=(5, self.timeout_seconds))
            response.raise_for_status()
            body = response.json()
            candidates = body.get("candidates") or []
            parts = candidates[0]["content"]["parts"] if candidates else []
            content = "".join(str(part.get("text", "")) for part in parts)
            parsed = json.loads(extract_first_json(content))
            result = validate_ollama_json(parsed)
            result["raw"] = content
            result["llm_time_seconds"] = round(time.perf_counter() - started, 3)
            return result
        except Exception as exc:
            self.logger.exception("Échec de la classification Gemini")
            result = fallback_result(type(exc).__name__)
            result["llm_time_seconds"] = round(time.perf_counter() - started, 3)
            return result
