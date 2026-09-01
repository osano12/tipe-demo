"""Initialise la base SQLite locale de l'application web."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_DIR = ROOT / "db"
DEFAULT_DB_PATH = DB_DIR / "app.db"
SCHEMA_PATH = DB_DIR / "schema.sql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialiser la base SQLite locale")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Chemin de la base SQLite")
    parser.add_argument("--seed", action="store_true", help="Ajoute des données de test")
    return parser.parse_args()


def init_db(db_path: Path, schema_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema)
        conn.commit()


def seed_db(db_path: Path) -> None:
    now = datetime.now(timezone.utc)
    rows = []
    samples = [
        ("recyclable", 0.93, "seed"),
        ("bio", 0.88, "seed"),
        ("waste", 0.79, "seed"),
        ("inconnu", 0.42, "seed"),
    ]
    for idx in range(20):
        label, conf, source = samples[idx % len(samples)]
        ts = (now - timedelta(minutes=idx * 7)).isoformat()
        rows.append((ts, label, conf, source, None, '{"seed": true}'))

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO waste_events(timestamp, label, confidence, source, image_path, extra_json)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.execute(
            "INSERT INTO system_events(timestamp, type, payload_json) VALUES (?, ?, ?)",
            (now.isoformat(), "pir", "{\"value\":1,\"device\":\"seed\"}"),
        )
        conn.commit()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)

    init_db(db_path=db_path, schema_path=SCHEMA_PATH)
    print(f"Base initialisée: {db_path}")

    if args.seed:
        seed_db(db_path)
        print("Données de test insérées.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
