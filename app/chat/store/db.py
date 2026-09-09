"""快捷喊话子系统 SQLite 存储（seraphine_chat.db）.

用户资产库：话术 / 分组 / 发送日志。与 seraphine_cache.db 物理分离 ——
缓存库 schema bump 会 DROP 重建（见 persistent_cache.py），话术是
本工具唯一的不可再生资产，本库铁律：**只增不删，永不 DROP 重建**。
"""
import os
import sqlite3
import threading
from typing import List, Optional

from app.common.config import LOCAL_PATH

TAG = "ChatDb"
DB_NAME = "seraphine_chat.db"
SCHEMA_VERSION = 1


class ChatDb:
    def __init__(self, db_path: str = ""):
        self._path = db_path or os.path.join(LOCAL_PATH, DB_NAME)
        # RLock：repo 的复合操作（如 next_phrase_in_group）持锁后会再调
        # 用自身查询方法，普通 Lock 会死锁。
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            if self._path != ":memory:":
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._init_schema()
        return self._conn

    def _init_schema(self):
        c = self._conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        row = c.execute(
            "SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is None:
            self._create_tables()
            c.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                      (str(SCHEMA_VERSION),))
            self._conn.commit()
        elif int(row["value"]) < SCHEMA_VERSION:
            # 只增不删：升级仅补建缺失的表/索引，绝不 DROP。
            # 列级变更用 ALTER TABLE ADD COLUMN（逐列 try，已存在则跳过）。
            self._create_tables()
            c.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                      (str(SCHEMA_VERSION),))
            self._conn.commit()
        c.close()

    def _create_tables(self):
        c = self._conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS pack (
                id TEXT PRIMARY KEY,
                name TEXT, version INTEGER,
                source TEXT,
                enabled INTEGER DEFAULT 1, readonly INTEGER DEFAULT 0,
                sort INTEGER, updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS group_t (
                id TEXT PRIMARY KEY,
                pack_id TEXT NOT NULL,
                name TEXT NOT NULL,
                hotkey TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                sort INTEGER,
                cycle_idx INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_group_pack ON group_t(pack_id);

            CREATE TABLE IF NOT EXISTS phrase (
                id TEXT PRIMARY KEY,
                pack_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                content TEXT NOT NULL,
                scope TEXT DEFAULT 'team',
                enabled INTEGER DEFAULT 1,
                dirty INTEGER DEFAULT 0,
                usage_count INTEGER DEFAULT 0,
                last_used REAL,
                sort INTEGER, updated_at REAL,
                FOREIGN KEY(group_id) REFERENCES group_t(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_phrase_group ON phrase(group_id);
            CREATE INDEX IF NOT EXISTS idx_phrase_enabled ON phrase(enabled);

            CREATE TABLE IF NOT EXISTS send_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                text TEXT NOT NULL,
                channel TEXT NOT NULL,
                ok INTEGER NOT NULL,
                detail TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_send_log_ts ON send_log(ts DESC);
        """)
        self._conn.commit()
        c.close()

    def table_names(self) -> List[str]:
        with self._lock:
            c = self.conn().cursor()
            rows = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            c.close()
        return [r["name"] for r in rows]

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
