from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import cv2
import imagehash
import numpy as np
from PIL import Image

from .cache_store import WasteCacheStore
from .dataset_store import DatasetStore
from .llm_gemini import GeminiVisionClient
from .llm_ollama import OllamaVisionClient
from .memory_store import LearnedObjectMemoryStore

LOGGER = logging.getLogger("ia.pipeline")


class WastePipeline:
    """Orchestre le cache visuel, le fournisseur IA et l'apprentissage local."""

    def __init__(self, *, db_path: str | Path = "db/waste_cache.sqlite3", provider: str = "ollama", model: str | None = None, gemini_api_key: str = "", confidence_threshold: float = 0.70, memory_path: str | Path = "memory_store/learned_objects.json", dataset_dir: str | Path = "data/dataset", logger: logging.Logger | None = None) -> None:
        self.logger = logger or LOGGER
        self.provider = provider.strip().lower()
        self.confidence_threshold = float(confidence_threshold)
        self.cache = WasteCacheStore(db_path=db_path, logger=self.logger, enable_faiss=False)
        self.memory_store = LearnedObjectMemoryStore(memory_path=memory_path, logger=self.logger)
        self.dataset_store = DatasetStore(dataset_dir=dataset_dir, logger=self.logger)
        self.hash_threshold = 5
        self.enable_learning = True
        self._lock = threading.RLock()
        if self.provider == "gemini":
            self.vision = GeminiVisionClient(api_key=gemini_api_key, model=model or "gemini-2.5-flash", logger=self.logger)
        elif self.provider == "ollama":
            self.vision = OllamaVisionClient(model=model or "llava", logger=self.logger)
        else:
            raise ValueError("AI_PROVIDER doit valoir 'ollama' ou 'gemini'.")
        self.logger.info("Pipeline prêt avec le fournisseur %s", self.provider)

    def compute_dhash(self, image: Any) -> str:
        """Calcule une empreinte perceptuelle compacte de l'image."""
        return str(imagehash.dhash(image))

    def classify_pil_image(self, image: Any) -> dict[str, Any]:
        """Classe une image PIL en utilisant d'abord le cache perceptuel."""
        with self._lock:
            dhash = self.compute_dhash(image)
            hash_hit = self.cache.search_hash(dhash, max_hamming_distance=self.hash_threshold, min_confidence=self.confidence_threshold)
            if hash_hit:
                return self._format_result(hash_hit.row, "cache_hash", True, dhash)
            vision_result = self.vision.classify_image(image)
            saved_row = self.cache.insert(phash=dhash, embedding=None, objet=vision_result.get("objet", "objet inconnu"), matiere=vision_result.get("matiere", "inconnue"), categorie=vision_result.get("categorie", "inconnu"), confiance=vision_result.get("confiance", 0.0), source=self.provider)
            result = self._format_result(saved_row, self.provider, False, dhash)
            result["llm_time_seconds"] = vision_result.get("llm_time_seconds", 0.0)
            if self.enable_learning and result["categorie"] != "inconnu":
                result["is_new_object"] = self.memory_store.add_new_object(dhash, result)
                self.dataset_store.save_sample(image=image, result=result, dhash=dhash, source=self.provider)
            return result

    def classify_frame(self, image_input: str | Path | np.ndarray) -> dict[str, Any]:
        """Charge une image depuis un chemin ou une matrice OpenCV puis la classe."""
        try:
            frame = cv2.imread(str(image_input)) if isinstance(image_input, (str, Path)) else image_input
            if frame is None or frame.size == 0:
                raise ValueError("Image vide ou illisible.")
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            return self.classify_pil_image(image)
        except Exception as exc:
            self.logger.exception("Échec du pipeline de classification")
            return {"categorie": "inconnu", "confiance": 0.0, "error": str(exc)}

    def _format_result(self, row: dict[str, Any], source: str, cache_hit: bool, dhash: str) -> dict[str, Any]:
        """Normalise une ligne de cache en résultat public."""
        return {"categorie": row.get("categorie", "inconnu"), "confiance": float(row.get("confiance", 0.0)), "objet": row.get("objet", "objet inconnu"), "matiere": row.get("matiere", "inconnue"), "source": source, "cache_hit": cache_hit, "dhash": dhash}

    def close(self) -> None:
        """Libère les ressources persistantes du pipeline."""
        self.cache.close()
