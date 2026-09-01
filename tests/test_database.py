from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.init_db import init_db

ROOT = Path(__file__).resolve().parents[1]


class DatabaseTests(unittest.TestCase):
    """Vérifie que le schéma crée une base exploitable depuis un clone neuf."""

    def test_schema_is_idempotent(self) -> None:
        """Initialise deux fois la même base sans erreur ni perte de structure."""
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "app.db"
            schema = ROOT / "db" / "schema.sql"
            init_db(database, schema)
            init_db(database, schema)
            with sqlite3.connect(database) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertIn("waste_events", tables)
            self.assertIn("system_events", tables)


if __name__ == "__main__":
    unittest.main()
