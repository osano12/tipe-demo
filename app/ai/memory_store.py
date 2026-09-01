from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


"""Memoire persistante des objets appris (JSON simple, lisible et portable)."""
"""Ici on stocke les objets appris dans un fichier JSON, avec une structure simple pour faciliter la lecture et la maintenance. 
Chaque objet appris est identifié par son dHash, et on dedoublonne pour éviter les entrées redondantes.
On peut facilement ajouter de nouveaux objets appris, et le systÃ¨me gÃ¨re automatiquement les mises Ã  jour du fichier de mémoire."""


LOGGER = logging.getLogger("smart_waste.ai.memory_store")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEMORY_PATH = PROJECT_ROOT / "memory_store" / "learned_objects.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_memory_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"version": 1, "updated_at": _utc_now_iso(), "objects": []}
    objects = payload.get("objects")
    if not isinstance(objects, list):
        objects = []
    return {
        "version": int(payload.get("version") or 1),
        "updated_at": str(payload.get("updated_at") or _utc_now_iso()),
        "objects": objects,
    }


def load_memory(memory_path: str | Path = DEFAULT_MEMORY_PATH) -> dict[str, Any]:
    path = Path(memory_path)
    if not path.exists():
        return {"version": 1, "updated_at": _utc_now_iso(), "objects": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.warning("Memoire JSON illisible, reinitialisation logique: %s", path)
        return {"version": 1, "updated_at": _utc_now_iso(), "objects": []}
    return _normalize_memory_payload(data)


def save_memory(data: dict[str, Any], memory_path: str | Path = DEFAULT_MEMORY_PATH) -> Path:
    path = Path(memory_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _normalize_memory_payload(data)
    payload["updated_at"] = _utc_now_iso()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class LearnedObjectMemoryStore:
    """Stocke les objets appris dans un fichier JSON et dedoublonne par dHash."""

    def __init__(
        self,
        memory_path: str | Path = DEFAULT_MEMORY_PATH,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.logger = logger or LOGGER
        self.memory_path = Path(memory_path)
        self._data = load_memory(self.memory_path)
        self._known_dhashes: set[str] = set()
        self._rebuild_index()
        self.logger.info(
            "Memoire chargee: %s objets appris (%s)",
            len(self._data.get("objects", [])),
            self.memory_path,
        )

    def _rebuild_index(self) -> None:
        self._known_dhashes.clear()
        for item in self._data.get("objects", []):
            if isinstance(item, dict):
                dhash = str(item.get("dhash") or "").strip()
                if dhash:
                    self._known_dhashes.add(dhash)

    def load_memory(self) -> dict[str, Any]:
        self._data = load_memory(self.memory_path)
        self._rebuild_index()
        return self._data

    def save_memory(self) -> Path:
        path = save_memory(self._data, self.memory_path)
        return path

    @property
    def count(self) -> int:
        return len(self._data.get("objects", []))

    def add_new_object(self, dhash: str, result: dict[str, Any]) -> bool:
        dhash_value = str(dhash or "").strip()
        if not dhash_value:
            return False
        if dhash_value in self._known_dhashes:
            return False

        category = str(result.get("categorie") or "inconnu").strip().lower()
        if category == "inconnu":
            return False

        entry = {
            "dhash": dhash_value,
            "objet": str(result.get("objet") or "objet inconnu"),
            "matiere": str(result.get("matiere") or "inconnue"),
            "categorie": category,
            "confiance": float(result.get("confiance") or 0.0),
            "source": str(result.get("source") or "llm"),
            "created_at": _utc_now_iso(),
        }
        self._data.setdefault("objects", []).append(entry)
        self._known_dhashes.add(dhash_value)
        self.save_memory()
        self.logger.info("Nouvel objet appris memorise (dHash=%s, categorie=%s)", dhash_value, category)
        return True


def add_new_object(dhash: str, result: dict[str, Any], memory_path: str | Path = DEFAULT_MEMORY_PATH) -> bool:
    store = LearnedObjectMemoryStore(memory_path)
    return store.add_new_object(dhash, result)
