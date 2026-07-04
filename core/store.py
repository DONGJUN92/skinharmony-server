"""개인 성분 기억 저장소 (SQLite).

서버는 Stateless — 상태는 이 DB에만 존재. user_key(닉네임)로 사용자 구분.
인증 마찰 최소화 설계: PlayMCP '인증 사용하지 않음' 모드에서 닉네임 기반 경량 개인화.
(user_key, canonical_id) PK upsert → 멱등(idempotent).
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

DB_PATH = Path(os.environ.get("SKINHARMONY_DB", Path(__file__).resolve().parent.parent / "user_prefs.sqlite"))
_KEY_RE = re.compile(r"[^0-9a-zA-Z가-힣_]")


def _clean_key(user_key: str) -> str:
    return _KEY_RE.sub("", (user_key or "").strip())[:32]


class PrefStore:
    def __init__(self, db_path: Path | None = None):
        self.path = db_path or DB_PATH
        with closing(self._conn()) as conn, conn as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS user_ingredients (
                    user_key     TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    preference   TEXT NOT NULL CHECK(preference IN ('AVOID','PREFER')),
                    reason       TEXT,
                    updated_at   INTEGER NOT NULL,
                    PRIMARY KEY (user_key, canonical_id)
                )"""
            )

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def save(self, user_key: str, canonical_id: str, display_name: str,
             preference: str, reason: str | None = None) -> bool:
        key = _clean_key(user_key)
        if not key:
            return False
        with closing(self._conn()) as conn, conn as c:
            c.execute(
                """INSERT INTO user_ingredients (user_key, canonical_id, display_name, preference, reason, updated_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(user_key, canonical_id)
                   DO UPDATE SET preference=excluded.preference, reason=excluded.reason,
                                 display_name=excluded.display_name, updated_at=excluded.updated_at""",
                (key, canonical_id, display_name, preference, reason, int(time.time())),
            )
        return True

    def get_prefs(self, user_key: str) -> dict[str, str]:
        """canonical_id -> 'AVOID'|'PREFER'"""
        key = _clean_key(user_key)
        if not key:
            return {}
        with closing(self._conn()) as conn, conn as c:
            rows = c.execute(
                "SELECT canonical_id, preference FROM user_ingredients WHERE user_key=?", (key,)
            ).fetchall()
        return dict(rows)

    def list_prefs(self, user_key: str) -> list[tuple[str, str, str | None]]:
        """(display_name, preference, reason) 목록"""
        key = _clean_key(user_key)
        if not key:
            return []
        with closing(self._conn()) as conn, conn as c:
            return c.execute(
                "SELECT display_name, preference, reason FROM user_ingredients WHERE user_key=? ORDER BY updated_at DESC LIMIT 50",
                (key,),
            ).fetchall()
