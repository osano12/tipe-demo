"""Sauvegarde de dataset auto-enrichi (image + metadata JSON)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("smart_waste.ai.dataset_store")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_DIR = PROJECT_ROOT / "data" / "dataset"


def _sanitize_fragment(value: Any, default: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    chars: list[str] = []
    for ch in text:
        if ch.isalnum() or ch in {"-", "_"}:
            chars.append(ch)
        elif ch in {" ", "/"}:
            chars.append("_")
    cleaned = "".join(chars).strip("_")
    return cleaned or default


def _confidence_fragment(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        number = 0.0
    return f"{max(0.0, min(1.0, number)):.3f}"


class DatasetStore:
    def __init__(
        self,
        dataset_dir: str | Path = DEFAULT_DATASET_DIR,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.logger = logger or LOGGER
        self.dataset_dir = Path(dataset_dir)
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

    def save_sample(
        self,
        *,
        image: Any,
        result: dict[str, Any],
        dhash: str,
        source: str,
    ) -> dict[str, str]:
        category = _sanitize_fragment(result.get("categorie"), "inconnu")
        material = _sanitize_fragment(result.get("matiere"), "inconnue")
        source_name = _sanitize_fragment(source, "llm")
        conf = _confidence_fragment(result.get("confiance"))
        dhash_text = _sanitize_fragment(dhash, "nodhash")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        basename = f"{timestamp}_{source_name}_c{conf}_{dhash_text}"

        out_dir = self.dataset_dir / category / material
        out_dir.mkdir(parents=True, exist_ok=True)

        image_path = out_dir / f"{basename}.jpg"
        meta_path = out_dir / f"{basename}.json"

        image.save(image_path, format="JPEG", quality=92, optimize=True)

        metadata = {
            "objet": result.get("objet"),
            "matiere": result.get("matiere"),
            "categorie": result.get("categorie"),
            "confiance": float(result.get("confiance") or 0.0),
            "source": source,
            "cache_hit": bool(result.get("cache_hit")),
            "dhash": dhash,
            "llm_time_seconds": float(result.get("llm_time_seconds") or 0.0),
            "is_new_object": bool(result.get("is_new_object")),
            "saved_at_local": datetime.now().isoformat(timespec="seconds"),
        }
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        self.logger.info("Dataset enrichi: %s", image_path)
        return {"image_path": str(image_path), "metadata_path": str(meta_path)}


def save_dataset_sample(
    *,
    image: Any,
    result: dict[str, Any],
    dhash: str,
    source: str,
    dataset_dir: str | Path = DEFAULT_DATASET_DIR,
    logger: logging.Logger | None = None,
) -> dict[str, str]:
    store = DatasetStore(dataset_dir, logger=logger)
    return store.save_sample(image=image, result=result, dhash=dhash, source=source)

