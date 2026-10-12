"""읽기 전용 SQLite 색인을 통해 사전 근거를 조회하는 모듈이다."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from .normalization import normalize_surface
from .models import Entry, Evidence, Source


class DictionaryRepository:
    """활성 SQLite DB만 읽는 사전 저장소다."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def is_ready(self) -> bool:
        """DB 존재·읽기·무결성 여부만 확인하며 데이터를 변경하지 않는다."""
        try:
            with self._connect() as connection:
                return connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        except sqlite3.Error:
            return False

    def lookup(self, query: str, limit: int = 20) -> list[Entry]:
        """정규화한 표면형을 매개변수화한 정확 일치 색인 질의로 찾는다."""
        normalized = normalize_surface(query)
        if not normalized:
            return []
        statement = """
        SELECT sf.entry_id, sf.surface, de.payload_json, s.file_name, de.row_number, s.source_hash
        FROM surface_form sf JOIN dictionary_entry de ON de.entry_id = sf.entry_id
        JOIN source_file s ON s.id = de.source_file_id
        WHERE sf.normalized_form = ? ORDER BY sf.entry_id LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(statement, (normalized, limit)).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        """SQLite URI의 mode=ro로만 연결해 런타임 쓰기를 막는다."""
        return sqlite3.connect(f"file:{self.database_path}?mode=ro", uri=True)

    @staticmethod
    def _entry_from_row(row: tuple[str, str, str, str, int, str]) -> Entry:
        """SQLite 조인 결과와 보존된 원본 payload를 외부 근거 모델로 변환한다."""
        entry_id, surface, payload_json, file_name, row_number, source_hash = row
        payload = json.loads(payload_json)
        return Entry(entry_id, surface, Evidence(payload["어휘"], payload["발음"], payload["품사"], payload["뜻풀이"], Source(file_name, row_number, source_hash)))
