"""SQLite 持久缓存: 战绩/对局详情/战犯评级.

仅做离线降级展示用, 不替代 LCU 数据源.
"""
import json
import os
import sqlite3
import threading
from json import JSONDecodeError
from typing import Optional

from app.common.config import LOCAL_PATH
TAG = "PersistentCache"
DB_NAME = "seraphine_cache.db"
SCHEMA_VERSION = 1
MAX_GAMES_PER_PUUID = 1000
MAX_GAME_DETAILS = 500


class PersistentCache:
    def __init__(self, db_path: str = ""):
        self._path = db_path or os.path.join(LOCAL_PATH, DB_NAME)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._init_schema()
        return self._conn

    def _init_schema(self):
        c = self._conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        version = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if version is None:
            self._create_tables()
            c.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                      (str(SCHEMA_VERSION),))
            self._conn.commit()
        elif int(version["value"]) < SCHEMA_VERSION:
            self._drop_tables()
            self._create_tables()
            c.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                      (str(SCHEMA_VERSION),))
            self._conn.commit()
        c.close()

    def _create_tables(self):
        c = self._conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                game_id INTEGER NOT NULL,
                puuid TEXT NOT NULL,
                queue_id INTEGER,
                champion_id INTEGER,
                kills INTEGER, deaths INTEGER, assists INTEGER,
                win INTEGER, creation INTEGER, duration INTEGER,
                champion_level INTEGER, cs INTEGER, gold INTEGER,
                position TEXT, game_type TEXT, map_id INTEGER,
                remake INTEGER, time_str TEXT,
                game_json TEXT,
                updated_at REAL NOT NULL DEFAULT (julianday('now')),
                PRIMARY KEY (game_id, puuid)
            );
            CREATE INDEX IF NOT EXISTS idx_games_puuid ON games(puuid);
            CREATE INDEX IF NOT EXISTS idx_games_creation ON games(creation DESC);

            CREATE TABLE IF NOT EXISTS game_details (
                game_id INTEGER PRIMARY KEY,
                detail_json TEXT,
                updated_at REAL NOT NULL DEFAULT (julianday('now'))
            );

            CREATE TABLE IF NOT EXISTS verdicts (
                game_id INTEGER PRIMARY KEY,
                winner_rating TEXT,
                loser_rating TEXT,
                updated_at REAL NOT NULL DEFAULT (julianday('now'))
            );

            CREATE TABLE IF NOT EXISTS summoners (
                puuid TEXT PRIMARY KEY,
                game_name TEXT, tag_line TEXT,
                profile_icon TEXT, level INTEGER,
                updated_at REAL NOT NULL DEFAULT (julianday('now'))
            );
        """)
        self._conn.commit()
        c.close()

    def _drop_tables(self):
        c = self._conn.cursor()
        c.executescript("DROP TABLE IF EXISTS games; DROP TABLE IF EXISTS game_details; DROP TABLE IF EXISTS verdicts; DROP TABLE IF EXISTS summoners;")
        self._conn.commit()
        c.close()

    # ---- games (match history) ----

    def set_games(self, puuid: str, games: list) -> int:
        count = 0
        with self._lock:
            conn = self._get_conn()
            c = conn.cursor()
            for g in games:
                c.execute("""
                    INSERT OR REPLACE INTO games
                    (game_id, puuid, queue_id, champion_id,
                     kills, deaths, assists, win, creation, duration,
                     champion_level, cs, gold, position, game_type, map_id,
                     remake, time_str, game_json, updated_at)
                    VALUES (?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,julianday('now'))
                """, (
                    g["gameId"], puuid, g.get("queueId"), g.get("championId"),
                    g.get("kills", 0), g.get("deaths", 0), g.get("assists", 0),
                    1 if g.get("win") else 0, g.get("timeStamp", 0), g.get("duration"),
                    g.get("champLevel", 0), g.get("cs", 0), g.get("gold", 0),
                    g.get("position"), g.get("name"), g.get("map"),
                    1 if g.get("remake") else 0, g.get("time"),
                    json.dumps(g, ensure_ascii=False),
                ))
                count += 1
            self._prune_games_for_puuid(c, puuid)
            conn.commit()
            c.close()
        return count

    def get_games(self, puuid: str, limit: int = 20, offset: int = 0) -> list:
        with self._lock:
            c = self._get_conn().cursor()
            rows = c.execute("""
                SELECT game_json FROM games
                WHERE puuid=?
                ORDER BY creation DESC
                LIMIT ? OFFSET ?
            """, (puuid, limit, offset)).fetchall()
            c.close()
        result = []
        for row in rows:
            try:
                result.append(json.loads(row["game_json"]))
            except (JSONDecodeError, TypeError):
                pass
        return result

    def _prune_games_for_puuid(self, c: sqlite3.Cursor, puuid: str):
        c.execute("""
            DELETE FROM games WHERE game_id IN (
                SELECT game_id FROM games WHERE puuid=?
                ORDER BY creation DESC
                LIMIT -1 OFFSET ?
            )
        """, (puuid, MAX_GAMES_PER_PUUID))

    # ---- game details ----

    def set_game_detail(self, game_id: int, detail: dict):
        with self._lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO game_details
                (game_id, detail_json, updated_at)
                VALUES (?,?,julianday('now'))
            """, (game_id, json.dumps(detail, ensure_ascii=False)))
            self._prune_game_details(c)
            conn.commit()
            c.close()

    def get_game_detail(self, game_id: int) -> Optional[dict]:
        with self._lock:
            c = self._get_conn().cursor()
            row = c.execute(
                "SELECT detail_json FROM game_details WHERE game_id=?",
                (game_id,)
            ).fetchone()
            c.close()
        if row is None:
            return None
        try:
            return json.loads(row["detail_json"])
        except (JSONDecodeError, TypeError):
            return None

    def _prune_game_details(self, c: sqlite3.Cursor):
        c.execute("""
            DELETE FROM game_details WHERE game_id IN (
                SELECT game_id FROM game_details
                ORDER BY updated_at DESC
                LIMIT -1 OFFSET ?
            )
        """, (MAX_GAME_DETAILS,))

    # ---- verdicts ----

    def set_verdict(self, game_id: int, winner_rating: list, loser_rating: list):
        with self._lock:
            self._get_conn().execute("""
                INSERT OR REPLACE INTO verdicts
                (game_id, winner_rating, loser_rating, updated_at)
                VALUES (?,?,?,julianday('now'))
            """, (game_id,
                  json.dumps(winner_rating, ensure_ascii=False),
                  json.dumps(loser_rating, ensure_ascii=False)))
            self._get_conn().commit()

    def get_verdict(self, game_id: int) -> Optional[dict]:
        with self._lock:
            c = self._get_conn().cursor()
            row = c.execute(
                "SELECT winner_rating, loser_rating FROM verdicts WHERE game_id=?",
                (game_id,)
            ).fetchone()
            c.close()
        if row is None:
            return None
        try:
            return {
                "gameId": game_id,
                "winnerRating": json.loads(row["winner_rating"]),
                "loserRating": json.loads(row["loser_rating"]),
            }
        except (JSONDecodeError, TypeError):
            return None

    # ---- summoners ----

    def set_summoner(self, puuid: str, name: str = "", tag_line: str = "",
                     profile_icon: str = "", level: int = 0):
        with self._lock:
            self._get_conn().execute("""
                INSERT OR REPLACE INTO summoners
                (puuid, game_name, tag_line, profile_icon, level, updated_at)
                VALUES (?,?,?,?,?,julianday('now'))
            """, (puuid, name, tag_line, profile_icon, level))
            self._get_conn().commit()

    def get_summoner(self, puuid: str) -> Optional[dict]:
        with self._lock:
            c = self._get_conn().cursor()
            row = c.execute(
                "SELECT * FROM summoners WHERE puuid=?", (puuid,)
            ).fetchone()
            c.close()
        if row is None:
            return None
        return dict(row)

    def clear_all(self):
        with self._lock:
            c = self._get_conn().cursor()
            c.execute("DELETE FROM games")
            c.execute("DELETE FROM game_details")
            c.execute("DELETE FROM verdicts")
            c.execute("DELETE FROM summoners")
            self._get_conn().commit()
            c.close()

    # ---- close ----

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    # ---- stats ----

    def get_stats(self) -> dict:
        with self._lock:
            c = self._get_conn().cursor()
            games = c.execute("SELECT COUNT(*) as n FROM games").fetchone()["n"]
            details = c.execute("SELECT COUNT(*) as n FROM game_details").fetchone()["n"]
            verdicts = c.execute("SELECT COUNT(*) as n FROM verdicts").fetchone()["n"]
            c.close()
        return {"games": games, "game_details": details, "verdicts": verdicts}


cache = PersistentCache()

# ponytail: global lock, per-connection locks if contention measured
# ponytail: no migration framework, schema_version bump rebuilds tables
