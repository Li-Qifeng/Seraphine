"""话术库数据访问层：分组 / 话术 CRUD、组内循环游标、热键绑定清单、发送日志。

所有方法线程安全（共享 ChatDb.lock）；返回 dict（sqlite3.Row 转 dict）。
"""
import time
from typing import Dict, List, Optional

from app.chat.store.db import ChatDb


class ChatRepo:
    def __init__(self, db: ChatDb):
        self.db = db

    # ---------- 分组 ----------

    def upsert_group(self, group_id: str, name: str, hotkey: str = "",
                     sort: int = 0, pack_id: str = "user", enabled: bool = True):
        with self.db.lock:
            self.db.conn().execute("""
                INSERT INTO group_t (id, pack_id, name, hotkey, enabled, sort)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, hotkey=excluded.hotkey,
                    enabled=excluded.enabled, sort=excluded.sort
            """, (group_id, pack_id, name, hotkey, 1 if enabled else 0, sort))
            self.db.conn().commit()

    def update_group_fields(self, group_id: str, name=None, hotkey=None,
                            sort=None, enabled=None):
        """局部更新（seed 升级用：保留用户改过的 hotkey）。"""
        sets, params = [], []
        if name is not None:
            sets.append("name=?")
            params.append(name)
        if hotkey is not None:
            sets.append("hotkey=?")
            params.append(hotkey)
        if sort is not None:
            sets.append("sort=?")
            params.append(sort)
        if enabled is not None:
            sets.append("enabled=?")
            params.append(1 if enabled else 0)
        if not sets:
            return
        params.append(group_id)
        with self.db.lock:
            self.db.conn().execute(
                f"UPDATE group_t SET {', '.join(sets)} WHERE id=?", params)
            self.db.conn().commit()

    def get_group(self, group_id: str) -> Optional[dict]:
        with self.db.lock:
            c = self.db.conn().cursor()
            row = c.execute("SELECT * FROM group_t WHERE id=?", (group_id,)).fetchone()
            c.close()
        return dict(row) if row else None

    def get_group_by_hotkey(self, hotkey: str) -> Optional[dict]:
        with self.db.lock:
            c = self.db.conn().cursor()
            row = c.execute(
                "SELECT * FROM group_t WHERE hotkey=? AND enabled=1",
                (hotkey,)).fetchone()
            c.close()
        return dict(row) if row else None

    def list_groups(self, enabled_only: bool = False) -> List[dict]:
        sql = "SELECT * FROM group_t"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY sort, id"
        with self.db.lock:
            c = self.db.conn().cursor()
            rows = c.execute(sql).fetchall()
            c.close()
        return [dict(r) for r in rows]

    def delete_group(self, group_id: str):
        with self.db.lock:
            self.db.conn().execute("DELETE FROM group_t WHERE id=?", (group_id,))
            self.db.conn().commit()  # phrase 由外键 ON DELETE CASCADE 清理

    # ---------- 话术 ----------

    def upsert_phrase(self, phrase_id: str, group_id: str, content: str,
                      sort: int = 0, pack_id: str = "user", scope: str = "team"):
        with self.db.lock:
            self.db.conn().execute("""
                INSERT INTO phrase (id, pack_id, group_id, content, scope, sort, updated_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    group_id=excluded.group_id, content=excluded.content,
                    scope=excluded.scope, sort=excluded.sort,
                    updated_at=excluded.updated_at
            """, (phrase_id, pack_id, group_id, content, scope, sort, time.time()))
            self.db.conn().commit()

    def get_phrase(self, phrase_id: str) -> Optional[dict]:
        with self.db.lock:
            c = self.db.conn().cursor()
            row = c.execute("SELECT * FROM phrase WHERE id=?", (phrase_id,)).fetchone()
            c.close()
        return dict(row) if row else None

    def list_phrases(self, group_id: str, enabled_only: bool = False) -> List[dict]:
        sql = "SELECT * FROM phrase WHERE group_id=?"
        if enabled_only:
            sql += " AND enabled=1"
        sql += " ORDER BY sort, id"
        with self.db.lock:
            c = self.db.conn().cursor()
            rows = c.execute(sql, (group_id,)).fetchall()
            c.close()
        return [dict(r) for r in rows]

    def update_phrase_content(self, phrase_id: str, content: str):
        """用户编辑话术：标记 dirty=1，内置词库升级时不覆盖。"""
        with self.db.lock:
            self.db.conn().execute(
                "UPDATE phrase SET content=?, dirty=1, updated_at=? WHERE id=?",
                (content, time.time(), phrase_id))
            self.db.conn().commit()

    def set_phrase_enabled(self, phrase_id: str, enabled: bool):
        with self.db.lock:
            self.db.conn().execute(
                "UPDATE phrase SET enabled=? WHERE id=?",
                (1 if enabled else 0, phrase_id))
            self.db.conn().commit()

    def delete_phrase(self, phrase_id: str):
        with self.db.lock:
            self.db.conn().execute("DELETE FROM phrase WHERE id=?", (phrase_id,))
            self.db.conn().commit()

    def search_phrases(self, keyword: str) -> List[dict]:
        if not keyword:
            return []
        with self.db.lock:
            c = self.db.conn().cursor()
            rows = c.execute("""
                SELECT * FROM phrase WHERE content LIKE ?
                ORDER BY usage_count DESC, sort LIMIT 50
            """, (f"%{keyword}%",)).fetchall()
            c.close()
        return [dict(r) for r in rows]

    def record_use(self, phrase_id: str):
        with self.db.lock:
            self.db.conn().execute("""
                UPDATE phrase SET usage_count=usage_count+1, last_used=? WHERE id=?
            """, (time.time(), phrase_id))
            self.db.conn().commit()

    # ---------- 热键绑定清单 ----------

    def list_hotkey_bindings(self) -> Dict[str, str]:
        """{hotkey: group_id}，仅启用分组且 hotkey 非空。"""
        with self.db.lock:
            c = self.db.conn().cursor()
            rows = c.execute(
                "SELECT hotkey, id FROM group_t WHERE hotkey != '' AND enabled=1"
            ).fetchall()
            c.close()
        return {r["hotkey"]: r["id"] for r in rows}

    # ---------- 组内循环 ----------

    def _enabled_phrases(self, group_id: str) -> List[dict]:
        return self.list_phrases(group_id, enabled_only=True)

    def next_phrase_in_group(self, group_id: str) -> Optional[dict]:
        """取组内下一条并推进游标（按 sort 固定顺序循环）。"""
        with self.db.lock:
            group = self.get_group(group_id)
            if not group:
                return None
            phrases = self._enabled_phrases(group_id)
            if not phrases:
                return None
            idx = (group["cycle_idx"] or 0) % len(phrases)
            phrase = phrases[idx]
            self.db.conn().execute(
                "UPDATE group_t SET cycle_idx=? WHERE id=?",
                ((idx + 1) % len(phrases), group_id))
            self.db.conn().commit()
        return phrase

    def peek_next_phrase(self, group_id: str) -> Optional[dict]:
        """预览下一条但不推进游标（设置页"下一条"展示用）。"""
        group = self.get_group(group_id)
        if not group:
            return None
        phrases = self._enabled_phrases(group_id)
        if not phrases:
            return None
        return phrases[(group["cycle_idx"] or 0) % len(phrases)]

    def reset_cycle(self, group_id: str):
        with self.db.lock:
            self.db.conn().execute(
                "UPDATE group_t SET cycle_idx=0 WHERE id=?", (group_id,))
            self.db.conn().commit()

    # ---------- 发送日志 ----------

    def add_send_log(self, text: str, channel: str, ok: bool,
                     detail: str = "", ts: Optional[float] = None):
        with self.db.lock:
            self.db.conn().execute("""
                INSERT INTO send_log (ts, text, channel, ok, detail)
                VALUES (?,?,?,?,?)
            """, (ts if ts is not None else time.time(), text, channel,
                  1 if ok else 0, detail))
            self.db.conn().commit()

    def list_send_logs(self, limit: int = 100) -> List[dict]:
        with self.db.lock:
            c = self.db.conn().cursor()
            rows = c.execute(
                "SELECT * FROM send_log ORDER BY ts DESC, id DESC LIMIT ?",
                (limit,)).fetchall()
            c.close()
        return [dict(r) for r in rows]

    def prune_send_logs(self, days: int = 30):
        cutoff = time.time() - days * 86400
        with self.db.lock:
            self.db.conn().execute("DELETE FROM send_log WHERE ts < ?", (cutoff,))
            self.db.conn().commit()

    # ---------- 内置包元信息 ----------

    def get_meta(self, key: str) -> Optional[str]:
        with self.db.lock:
            c = self.db.conn().cursor()
            row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            c.close()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str):
        with self.db.lock:
            self.db.conn().execute(
                "INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))
            self.db.conn().commit()
