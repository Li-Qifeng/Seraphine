"""app/chat/store 层契约测试：DB schema / Repo CRUD / 循环游标 / send_log / seed 幂等与升级合并。

纯 sqlite，无 Qt/Win32 依赖（db 路径注入 tmp 文件）。
"""
import time

import pytest

from app.chat.store.db import ChatDb
from app.chat.store.repo import ChatRepo
from app.chat.store.seed import BUILTIN_PACK, ensure_seed


@pytest.fixture()
def repo(tmp_path):
    db = ChatDb(str(tmp_path / "chat_test.db"))
    r = ChatRepo(db)
    yield r
    db.close()


@pytest.fixture()
def seeded(repo):
    ensure_seed(repo)
    return repo


# ---------- DB schema ----------

class TestSchema:
    def test_tables_created(self, repo):
        names = repo.db.table_names()
        for t in ("meta", "pack", "group_t", "phrase", "send_log"):
            assert t in names

    def test_reopen_keeps_data(self, tmp_path):
        path = str(tmp_path / "x.db")
        r1 = ChatRepo(ChatDb(path))
        r1.upsert_group("g1", "分组一", hotkey="Alt+1", sort=1)
        r1.db.close()
        r2 = ChatRepo(ChatDb(path))
        g = r2.get_group("g1")
        assert g is not None and g["name"] == "分组一" and g["hotkey"] == "Alt+1"
        r2.db.close()

    def test_no_drop_on_version_bump(self, tmp_path):
        """schema_version 变化时不得 DROP 用户数据（只增不删铁律）。"""
        path = str(tmp_path / "y.db")
        r1 = ChatRepo(ChatDb(path))
        r1.upsert_group("g1", "用户分组", hotkey="", sort=1)
        r1.upsert_phrase("p1", "g1", "自定义话术", sort=1)
        r1.db.close()
        # 用更高 SCHEMA_VERSION 重开
        import app.chat.store.db as db_mod
        old = db_mod.SCHEMA_VERSION
        db_mod.SCHEMA_VERSION = old + 1
        try:
            r2 = ChatRepo(ChatDb(path))
            assert r2.get_group("g1") is not None
            assert r2.get_phrase("p1") is not None
            r2.db.close()
        finally:
            db_mod.SCHEMA_VERSION = old


# ---------- 分组 / 话术 CRUD ----------

class TestCrud:
    def test_group_crud(self, repo):
        repo.upsert_group("g1", "对线", hotkey="Alt+1", sort=1)
        repo.upsert_group("g1", "对线改", hotkey="Alt+2", sort=2)
        g = repo.get_group("g1")
        assert g["name"] == "对线改" and g["hotkey"] == "Alt+2" and g["sort"] == 2
        assert len(repo.list_groups()) == 1
        repo.delete_group("g1")
        assert repo.get_group("g1") is None

    def test_phrase_crud_and_cascade(self, repo):
        repo.upsert_group("g1", "对线", hotkey="", sort=1)
        repo.upsert_phrase("p1", "g1", "中路 miss", sort=1)
        repo.upsert_phrase("p2", "g1", "打野来下", sort=2)
        assert [p["content"] for p in repo.list_phrases("g1")] == ["中路 miss", "打野来下"]
        p = repo.get_phrase("p1")
        assert p["enabled"] == 1 and p["dirty"] == 0 and p["usage_count"] == 0
        repo.set_phrase_enabled("p2", False)
        assert [p["id"] for p in repo.list_phrases("g1", enabled_only=True)] == ["p1"]
        repo.delete_group("g1")  # 级联删话术
        assert repo.list_phrases("g1") == []

    def test_phrase_update_marks_dirty(self, repo):
        repo.upsert_group("g1", "g", hotkey="", sort=1)
        repo.upsert_phrase("p1", "g1", "原文", sort=1)
        repo.update_phrase_content("p1", "用户改过的")
        p = repo.get_phrase("p1")
        assert p["content"] == "用户改过的" and p["dirty"] == 1

    def test_search(self, repo):
        repo.upsert_group("g1", "g", hotkey="", sort=1)
        repo.upsert_phrase("p1", "g1", "集合打龙", sort=1)
        repo.upsert_phrase("p2", "g1", "中路消失", sort=2)
        assert [p["id"] for p in repo.search_phrases("打龙")] == ["p1"]
        assert len(repo.search_phrases("路")) == 1
        assert repo.search_phrases("") == []

    def test_record_use(self, repo):
        repo.upsert_group("g1", "g", hotkey="", sort=1)
        repo.upsert_phrase("p1", "g1", "x", sort=1)
        repo.record_use("p1")
        repo.record_use("p1")
        assert repo.get_phrase("p1")["usage_count"] == 2

    def test_list_hotkey_bindings(self, repo):
        repo.upsert_group("g1", "a", hotkey="Alt+1", sort=1)
        repo.upsert_group("g2", "b", hotkey="Alt+2", sort=2)
        repo.upsert_group("g3", "c", hotkey="", sort=3)
        bindings = repo.list_hotkey_bindings()
        assert bindings == {"Alt+1": "g1", "Alt+2": "g2"}


# ---------- 循环游标 ----------

class TestCycle:
    def test_cycle_wraps(self, seeded):
        groups = seeded.list_groups()
        gid = groups[0]["id"]
        n = len(seeded.list_phrases(gid, enabled_only=True))
        assert n > 1
        seen = []
        for _ in range(n + 1):
            p = seeded.next_phrase_in_group(gid)
            seen.append(p["id"])
        assert seen[0] == seen[n]  # 转完一圈回到第一条
        assert len(set(seen[:n])) == n  # 一圈内不重复

    def test_cycle_skips_disabled(self, seeded):
        gid = seeded.list_groups()[0]["id"]
        phrases = seeded.list_phrases(gid, enabled_only=True)
        seeded.set_phrase_enabled(phrases[0]["id"], False)
        p = seeded.next_phrase_in_group(gid)
        assert p["id"] != phrases[0]["id"]

    def test_cycle_empty_group_returns_none(self, repo):
        repo.upsert_group("g9", "空", hotkey="", sort=9)
        assert repo.next_phrase_in_group("g9") is None

    def test_peek_does_not_advance(self, seeded):
        gid = seeded.list_groups()[0]["id"]
        a = seeded.peek_next_phrase(gid)
        b = seeded.peek_next_phrase(gid)
        assert a is not None and a["id"] == b["id"]
        c = seeded.next_phrase_in_group(gid)
        assert c["id"] == a["id"]


# ---------- send_log ----------

class TestSendLog:
    def test_add_and_query(self, repo):
        repo.add_send_log("集合打龙", channel="ingame", ok=True)
        repo.add_send_log("bp 消息", channel="lcu", ok=False, detail="no conversation")
        rows = repo.list_send_logs(limit=10)
        assert len(rows) == 2
        assert rows[0]["text"] == "bp 消息"  # 最新在前
        assert rows[0]["ok"] == 0 and rows[0]["detail"] == "no conversation"
        assert rows[1]["channel"] == "ingame" and rows[1]["ok"] == 1

    def test_prune_30_days(self, repo):
        old_ts = time.time() - 31 * 86400
        repo.add_send_log("旧", channel="ingame", ok=True, ts=old_ts)
        repo.add_send_log("新", channel="ingame", ok=True)
        repo.prune_send_logs(days=30)
        rows = repo.list_send_logs(limit=10)
        assert len(rows) == 1 and rows[0]["text"] == "新"


# ---------- seed ----------

class TestSeed:
    def test_seed_content_shape(self, seeded):
        groups = seeded.list_groups()
        assert len(groups) == len(BUILTIN_PACK["groups"])
        total = sum(len(seeded.list_phrases(g["id"])) for g in groups)
        assert total == sum(len(g["phrases"]) for g in BUILTIN_PACK["groups"])
        # 默认热键 Alt+1..Alt+N 落库
        bindings = seeded.list_hotkey_bindings()
        assert bindings.get("Alt+1") == groups[0]["id"]

    def test_seed_idempotent(self, seeded):
        before = [(g["id"], g["name"]) for g in seeded.list_groups()]
        ensure_seed(seeded)
        after = [(g["id"], g["name"]) for g in seeded.list_groups()]
        assert before == after

    def test_seed_upgrade_preserves_dirty(self, seeded):
        gid = seeded.list_groups()[0]["id"]
        p = seeded.list_phrases(gid)[0]
        seeded.update_phrase_content(p["id"], "用户自定义内容")
        # 模拟内置包升级（版本 +1，内容变化）
        import copy
        new_pack = copy.deepcopy(BUILTIN_PACK)
        new_pack["version"] = BUILTIN_PACK["version"] + 1
        new_pack["groups"][0]["phrases"][0]["content"] = "官方新文案"
        ensure_seed(seeded, pack=new_pack)
        # dirty=1 的保留用户版；未改过的更新为官方新文案
        assert seeded.get_phrase(p["id"])["content"] == "用户自定义内容"
        others = [x for x in seeded.list_phrases(gid) if x["id"] != p["id"]]
        assert all(x["dirty"] == 0 for x in others)

    def test_seed_upgrade_disables_removed(self, seeded):
        import copy
        gid = seeded.list_groups()[0]["id"]
        removed_id = seeded.list_phrases(gid)[-1]["id"]
        new_pack = copy.deepcopy(BUILTIN_PACK)
        new_pack["version"] = BUILTIN_PACK["version"] + 1
        new_pack["groups"][0]["phrases"] = new_pack["groups"][0]["phrases"][:-1]
        ensure_seed(seeded, pack=new_pack)
        p = seeded.get_phrase(removed_id)
        assert p is not None and p["enabled"] == 0  # 只标记不物理删除

    def test_user_pack_untouched_by_seed(self, seeded):
        seeded.upsert_group("u1", "我的分组", hotkey="Alt+9", sort=99)
        seeded.upsert_phrase("up1", "u1", "用户话术", sort=1)
        ensure_seed(seeded)
        assert seeded.get_group("u1") is not None
        assert seeded.get_phrase("up1")["enabled"] == 1
