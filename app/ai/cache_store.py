"""Stockage de cache SQLite + FAISS pour le pipeline local de tri des déchets."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    import faiss  # type: ignore
except Exception as exc:  # pragma: no cover - dépendance optionnelle au runtime
    faiss = None  # type: ignore[assignment]
    _FAISS_IMPORT_ERROR = exc
else:
    _FAISS_IMPORT_ERROR = None


LOGGER = logging.getLogger("smart_waste.ai.cache_store")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS waste_cache (
  id INTEGER PRIMARY KEY,
  phash TEXT,
  embedding BLOB,
  objet TEXT,
  matiere TEXT,
  categorie TEXT,
  confiance REAL,
  source TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass
class CacheMatch:
    row: dict[str, Any]
    source: str
    hamming_distance: int | None = None
    similarity: float | None = None


def _require_faiss() -> None:
    if faiss is None:
        raise RuntimeError("faiss-cpu manquant (`pip install faiss-cpu`).") from _FAISS_IMPORT_ERROR


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _embedding_to_blob(embedding: np.ndarray) -> bytes:
    return np.asarray(embedding, dtype=np.float32).reshape(-1).tobytes()


def _blob_to_embedding(blob: bytes) -> np.ndarray:
    return np.asarray(np.frombuffer(blob, dtype=np.float32), dtype=np.float32)


def _hex_hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


class WasteCacheStore:
    """Métadonnées SQLite + index FAISS en mémoire (cosinus via produit scalaire)."""

    def __init__(
        self,
        db_path: str | Path,
        logger: logging.Logger | None = None,
        *,
        enable_faiss: bool = True,
    ) -> None:
        self.logger = logger or LOGGER
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.enable_faiss = bool(enable_faiss)

        if self.enable_faiss:
            _require_faiss()

        self._index: Any | None = None
        self._embedding_dim: int | None = None

        self._ensure_schema()
        if self.enable_faiss:
            self.rebuild_faiss_index()
        else:
            self.logger.info("FAISS desactive : cache embeddings ignore (mode leger)")

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema(self) -> None:
        self.conn.execute(CREATE_TABLE_SQL)
        self.conn.commit()

    def init_db(self) -> None:
        self._ensure_schema()
        if self.enable_faiss:
            self.rebuild_faiss_index()

    def _init_index(self, embedding_dim: int) -> None:
        _require_faiss()
        self._embedding_dim = int(embedding_dim)
        self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(self._embedding_dim))

    def _ensure_index_for_dim(self, embedding_dim: int) -> None:
        if self._index is None:
            self._init_index(embedding_dim)
            return
        if self._embedding_dim != int(embedding_dim):
            raise RuntimeError(
                f"Dimension embedding incompatible (cache={self._embedding_dim}, nouveau={embedding_dim})."
            )

    def rebuild_faiss_index(self) -> None:
        # Reconstruit l'index FAISS depuis SQLite au démarrage.
        if not self.enable_faiss:
            self._index = None
            self._embedding_dim = None
            return
        rows = self.conn.execute(
            "SELECT id, embedding FROM waste_cache WHERE embedding IS NOT NULL ORDER BY id"
        ).fetchall()

        self._index = None
        self._embedding_dim = None

        if not rows:
            self.logger.info("Index FAISS du cache : vide")
            return

        embeddings: list[np.ndarray] = []
        ids: list[int] = []
        for row in rows:
            blob = row["embedding"]
            if not blob:
                continue
            vec = _blob_to_embedding(blob)
            if vec.size == 0:
                continue
            embeddings.append(vec)
            ids.append(int(row["id"]))

        if not embeddings:
            self.logger.info("Index FAISS du cache : aucun embedding valide")
            return

        dim = int(embeddings[0].shape[0])
        self._init_index(dim)
        matrix = np.vstack(embeddings).astype(np.float32, copy=False)
        # Normalisation L2 -> IndexFlatIP devient équivalent Ã  une similarité cosinus.
        faiss.normalize_L2(matrix)
        ids_array = np.asarray(ids, dtype=np.int64)
        self._index.add_with_ids(matrix, ids_array)
        self.logger.info("Index FAISS reconstruit avec %s vecteurs (dim=%s)", len(ids), dim)

    def _get_row_by_id(self, row_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM waste_cache WHERE id = ?", (int(row_id),)).fetchone()
        return _row_to_dict(row)

    def search_hash(
        self,
        phash: str,
        *,
        max_hamming_distance: int = 5,
        min_confidence: float = 0.70,
    ) -> CacheMatch | None:
        # Recherche d'un doublon (ou quasi doublon) via distance de Hamming sur le dHash.
        rows = self.conn.execute(
            """
            SELECT * FROM waste_cache
            WHERE phash IS NOT NULL AND confiance >= ?
            ORDER BY created_at DESC
            """,
            (float(min_confidence),),
        ).fetchall()

        best: tuple[int, sqlite3.Row] | None = None
        for row in rows:
            candidate = str(row["phash"] or "")
            if not candidate:
                continue
            try:
                distance = _hex_hamming_distance(str(phash), candidate)
            except Exception:
                continue
            if distance <= max_hamming_distance and (best is None or distance < best[0]):
                best = (distance, row)
                if distance == 0:
                    break

        if best is None:
            return None

        distance, row = best
        row_dict = _row_to_dict(row)
        if row_dict is None:
            return None
        return CacheMatch(row=row_dict, source="hash", hamming_distance=distance)

    def search_embed(
        self,
        embedding: np.ndarray,
        *,
        min_similarity: float = 0.90,
        min_confidence: float = 0.70,
    ) -> CacheMatch | None:
        # Recherche de l'objet le plus proche dans FAISS (embedding CLIP déjÃ  normalisé).
        if not self.enable_faiss:
            return None
        if self._index is None:
            return None

        query = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
        if self._embedding_dim is None or query.shape[1] != self._embedding_dim:
            raise RuntimeError(
                f"Dimension embedding incompatible (cache={self._embedding_dim}, requete={query.shape[1]})."
            )

        faiss.normalize_L2(query)
        scores, ids = self._index.search(query, 1)
        row_id = int(ids[0][0])
        similarity = float(scores[0][0])

        if row_id < 0 or similarity < float(min_similarity):
            return None

        row = self._get_row_by_id(row_id)
        if row is None:
            return None
        if float(row.get("confiance") or 0.0) < float(min_confidence):
            return None
        return CacheMatch(row=row, source="faiss", similarity=similarity)

    def insert(
        self,
        *,
        phash: str,
        embedding: np.ndarray | None,
        objet: str,
        matiere: str,
        categorie: str,
        confiance: float,
        source: str,
    ) -> dict[str, Any]:
        # Stocke le résultat (et l'embedding si disponible) en base SQLite.
        embedding_blob: bytes | None = None
        embedding_array: np.ndarray | None = None

        if embedding is not None:
            embedding_array = np.asarray(embedding, dtype=np.float32).reshape(-1)
            if embedding_array.size > 0:
                embedding_blob = _embedding_to_blob(embedding_array)

        cursor = self.conn.execute(
            """
            INSERT INTO waste_cache (phash, embedding, objet, matiere, categorie, confiance, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(phash),
                embedding_blob,
                str(objet),
                str(matiere),
                str(categorie),
                float(confiance),
                str(source),
            ),
        )
        self.conn.commit()
        row_id = int(cursor.lastrowid)

        if self.enable_faiss and embedding_array is not None and embedding_array.size > 0:
            # Ajout immédiat dans FAISS pour éviter une reconstruction complÃ¨te de l'index.
            self._ensure_index_for_dim(int(embedding_array.shape[0]))
            vector = embedding_array.astype(np.float32, copy=False).reshape(1, -1)
            faiss.normalize_L2(vector)
            ids = np.asarray([row_id], dtype=np.int64)
            self._index.add_with_ids(vector, ids)

        row = self._get_row_by_id(row_id)
        if row is None:
            raise RuntimeError("Insertion cache echouee (relecture impossible).")
        self.logger.info(f"DEBUG SQL: Objet '{objet}' inséré avec ID {row_id} et Hash {phash}")
        return row


