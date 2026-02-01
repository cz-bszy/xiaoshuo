"""TemporalFactStore: SQLite-backed fact store with temporal validity."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Fact:
    subject: str
    predicate: str
    object_value: Any
    qualifiers: Optional[Dict[str, Any]] = None
    valid_from_chapter: int = 0
    valid_to_chapter: Optional[int] = None
    source_chapter: int = 0
    confidence: float = 1.0
    hard_flag: bool = True


class TemporalFactStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT UNIQUE,
                type TEXT,
                aliases TEXT,
                rename_events TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT,
                predicate TEXT,
                object_value TEXT,
                qualifiers TEXT,
                valid_from_chapter INTEGER,
                valid_to_chapter INTEGER,
                source_chapter INTEGER,
                confidence REAL,
                hard_flag INTEGER
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS fact_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_id INTEGER,
                chapter_num INTEGER,
                action TEXT,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conn.commit()
        self._ensure_column("entities", "rename_events", "TEXT")

    def _ensure_column(self, table: str, column: str, col_type: str):
        cur = self.conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cur.fetchall()}
        if column not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            self.conn.commit()

    def upsert_entity(
        self,
        canonical_name: str,
        entity_type: str,
        aliases: Optional[List[str]] = None,
        rename_events: Optional[List[Dict[str, Any]]] = None,
    ):
        cur = self.conn.cursor()
        aliases_json = json.dumps(aliases or [], ensure_ascii=False)
        rename_json = json.dumps(rename_events or [], ensure_ascii=False)
        cur.execute(
            "INSERT OR IGNORE INTO entities (canonical_name, type, aliases, rename_events) VALUES (?, ?, ?, ?)",
            (canonical_name, entity_type, aliases_json, rename_json),
        )
        cur.execute(
            "UPDATE entities SET aliases = ?, rename_events = ? WHERE canonical_name = ?",
            (aliases_json, rename_json, canonical_name),
        )
        self.conn.commit()

    def get_entity_aliases(self, canonical_name: str) -> List[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT aliases FROM entities WHERE canonical_name = ?", (canonical_name,))
        row = cur.fetchone()
        if not row:
            return []
        try:
            return json.loads(row["aliases"] or "[]")
        except Exception:
            return []

    def add_rename_event(self, canonical_name: str, chapter_num: int, new_name: str, reason: str = ""):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT aliases, rename_events FROM entities WHERE canonical_name = ?",
            (canonical_name,),
        )
        row = cur.fetchone()
        aliases = json.loads(row["aliases"] or "[]") if row else []
        rename_events = json.loads(row["rename_events"] or "[]") if row else []

        if new_name not in aliases:
            aliases.append(new_name)
        rename_events.append(
            {"chapter": chapter_num, "new_name": new_name, "reason": reason}
        )

        self.upsert_entity(canonical_name, "character", aliases, rename_events)

    def get_rename_events(self, canonical_name: str) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT rename_events FROM entities WHERE canonical_name = ?", (canonical_name,))
        row = cur.fetchone()
        if not row:
            return []
        try:
            return json.loads(row["rename_events"] or "[]")
        except Exception:
            return []

    def upsert_facts(self, chapter_num: int, extracted_facts: List[Fact]):
        cur = self.conn.cursor()
        for fact in extracted_facts:
            # invalidate existing
            cur.execute(
                """
                UPDATE facts
                SET valid_to_chapter = ?
                WHERE subject = ? AND predicate = ? AND valid_to_chapter IS NULL
                """,
                (chapter_num, fact.subject, fact.predicate),
            )
            # insert new
            cur.execute(
                """
                INSERT INTO facts (subject, predicate, object_value, qualifiers, valid_from_chapter, valid_to_chapter, source_chapter, confidence, hard_flag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact.subject,
                    fact.predicate,
                    json.dumps(fact.object_value, ensure_ascii=False),
                    json.dumps(fact.qualifiers or {}, ensure_ascii=False),
                    fact.valid_from_chapter or chapter_num,
                    fact.valid_to_chapter,
                    fact.source_chapter or chapter_num,
                    fact.confidence,
                    1 if fact.hard_flag else 0,
                ),
            )
            fact_id = cur.lastrowid
            cur.execute(
                "INSERT INTO fact_events (fact_id, chapter_num, action, reason) VALUES (?, ?, ?, ?)",
                (fact_id, chapter_num, "upsert", "chapter_commit"),
            )
        self.conn.commit()

    def invalidate_fact(self, fact_id: int, chapter_num: int, reason: str):
        cur = self.conn.cursor()
        cur.execute("UPDATE facts SET valid_to_chapter = ? WHERE fact_id = ?", (chapter_num, fact_id))
        cur.execute(
            "INSERT INTO fact_events (fact_id, chapter_num, action, reason) VALUES (?, ?, ?, ?)",
            (fact_id, chapter_num, "invalidate", reason),
        )
        self.conn.commit()

    def query_facts(self, chapter_num: int, filters: Optional[Dict[str, Any]] = None, hard_only: bool = True) -> List[Fact]:
        filters = filters or {}
        clauses = ["valid_from_chapter <= ?", "(valid_to_chapter IS NULL OR valid_to_chapter >= ?)"]
        params: List[Any] = [chapter_num, chapter_num]

        if hard_only:
            clauses.append("hard_flag = 1")
        if "subject" in filters:
            clauses.append("subject = ?")
            params.append(filters["subject"])
        if "predicate" in filters:
            clauses.append("predicate = ?")
            params.append(filters["predicate"])

        query = "SELECT * FROM facts WHERE " + " AND ".join(clauses)
        cur = self.conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()

        facts: List[Fact] = []
        for row in rows:
            facts.append(
                Fact(
                    subject=row["subject"],
                    predicate=row["predicate"],
                    object_value=json.loads(row["object_value"] or "null"),
                    qualifiers=json.loads(row["qualifiers"] or "{}"),
                    valid_from_chapter=row["valid_from_chapter"],
                    valid_to_chapter=row["valid_to_chapter"],
                    source_chapter=row["source_chapter"],
                    confidence=row["confidence"],
                    hard_flag=bool(row["hard_flag"]),
                )
            )
        return facts

    def get_snapshot(self, chapter_num: int) -> Dict[str, Any]:
        facts = self.query_facts(chapter_num, hard_only=True)
        snapshot: Dict[str, Dict[str, Any]] = {}
        for fact in facts:
            snapshot.setdefault(fact.subject, {})[fact.predicate] = fact.object_value
        return snapshot

    def close(self):
        self.conn.close()
