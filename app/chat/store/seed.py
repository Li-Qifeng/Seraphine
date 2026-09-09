"""内置话术库 seed：首次启动导入 + 版本升级合并。

升级合并语义（用户资产保护）：
- 用户改过的条目（dirty=1）保留用户版；
- 未改动的覆盖为新版；新增直接追加；
- 官方删除的条目只标记 enabled=0，不物理删除（用户可能已习惯其位置）；
- 用户自建分组 / 话术（pack_id='user'）一律不动。
"""
import time
from typing import Optional

from app.common.logger import logger
from app.chat.store.repo import ChatRepo

TAG = "ChatSeed"
BUILTIN_PACK_ID = "builtin.zh-CN"
META_KEY = "builtin_pack_version"

BUILTIN_PACK = {
    "id": BUILTIN_PACK_ID,
    "version": 1,
    "groups": [
        {
            "id": "b.g1", "name": "对线", "hotkey": "Alt+1", "sort": 1,
            "phrases": [
                {"id": "b.g1.p1", "content": "中路消失，小心", "sort": 1},
                {"id": "b.g1.p2", "content": "敌人不见了，可能去游走了", "sort": 2},
                {"id": "b.g1.p3", "content": "打野来上路抓一波", "sort": 3},
                {"id": "b.g1.p4", "content": "我有TP，可以支援", "sort": 4},
                {"id": "b.g1.p5", "content": "稳住发育，等我装备", "sort": 5},
            ],
        },
        {
            "id": "b.g2", "name": "打野", "hotkey": "Alt+2", "sort": 2,
            "phrases": [
                {"id": "b.g2.p1", "content": "打野来下，可以越塔", "sort": 1},
                {"id": "b.g2.p2", "content": "对面打野在上半区", "sort": 2},
                {"id": "b.g2.p3", "content": "帮我看一下蓝buff", "sort": 3},
                {"id": "b.g2.p4", "content": "龙坑有眼，排一下", "sort": 4},
                {"id": "b.g2.p5", "content": "这波我来抓，等我", "sort": 5},
            ],
        },
        {
            "id": "b.g3", "name": "团战", "hotkey": "Alt+3", "sort": 3,
            "phrases": [
                {"id": "b.g3.p1", "content": "集合，准备团", "sort": 1},
                {"id": "b.g3.p2", "content": "先秒对面C位", "sort": 2},
                {"id": "b.g3.p3", "content": "保护后排，别冲动", "sort": 3},
                {"id": "b.g3.p4", "content": "我开团，跟上", "sort": 4},
                {"id": "b.g3.p5", "content": "打不过，先撤", "sort": 5},
            ],
        },
        {
            "id": "b.g4", "name": "资源", "hotkey": "Alt+4", "sort": 4,
            "phrases": [
                {"id": "b.g4.p1", "content": "集合打龙", "sort": 1},
                {"id": "b.g4.p2", "content": "大龙逼团，别单带", "sort": 2},
                {"id": "b.g4.p3", "content": "先锋放了，换小龙", "sort": 3},
                {"id": "b.g4.p4", "content": "对面在打龙，快来看", "sort": 4},
                {"id": "b.g4.p5", "content": "守一下塔，别掉高地", "sort": 5},
            ],
        },
        {
            "id": "b.g5", "name": "礼貌", "hotkey": "Alt+5", "sort": 5,
            "phrases": [
                {"id": "b.g5.p1", "content": "我的，这波没打好", "sort": 1},
                {"id": "b.g5.p2", "content": "没事，稳住能赢", "sort": 2},
                {"id": "b.g5.p3", "content": "漂亮！", "sort": 3},
                {"id": "b.g5.p4", "content": "辛苦了", "sort": 4},
                {"id": "b.g5.p5", "content": "加油，别放弃", "sort": 5},
            ],
        },
    ],
}


def ensure_seed(repo: ChatRepo, pack: Optional[dict] = None):
    """导入 / 升级内置话术包，幂等。

    版本 >= 包版本时直接返回；否则按 dirty 语义合并。
    """
    pack = pack or BUILTIN_PACK
    current = repo.get_meta(META_KEY)
    if current is not None and int(current) >= pack["version"]:
        return

    logger.info(f"seeding builtin pack v{pack['version']} (current={current})", TAG)
    repo.db.conn().execute("""
        INSERT INTO pack (id, name, version, source, readonly, sort, updated_at)
        VALUES (?,?,?,?,1,1,?)
        ON CONFLICT(id) DO UPDATE SET version=excluded.version, updated_at=excluded.updated_at
    """, (pack["id"], "内置话术", pack["version"], "builtin", time.time()))
    repo.db.conn().commit()

    pack_group_ids = set()
    for g in pack["groups"]:
        pack_group_ids.add(g["id"])
        existing = repo.get_group(g["id"])
        if existing is None:
            repo.upsert_group(g["id"], g["name"], hotkey=g["hotkey"],
                              sort=g["sort"], pack_id=pack["id"])
        else:
            # 升级：更新名称与排序，保留用户改过的 hotkey
            repo.update_group_fields(g["id"], name=g["name"], sort=g["sort"])

        pack_phrase_ids = set()
        for p in g["phrases"]:
            pack_phrase_ids.add(p["id"])
            existing_p = repo.get_phrase(p["id"])
            if existing_p is None:
                repo.upsert_phrase(p["id"], g["id"], p["content"],
                                   sort=p["sort"], pack_id=pack["id"])
            elif not existing_p["dirty"]:
                repo.upsert_phrase(p["id"], g["id"], p["content"],
                                   sort=p["sort"], pack_id=pack["id"])
            # dirty=1 → 保留用户版

        # 官方删除的条目标记 enabled=0（只动内置包的）
        for old in repo.list_phrases(g["id"]):
            if old["pack_id"] == pack["id"] and old["id"] not in pack_phrase_ids:
                repo.set_phrase_enabled(old["id"], False)

    # 官方删除的整组：禁用组及其内置话术
    for old_g in repo.list_groups():
        if old_g["pack_id"] == pack["id"] and old_g["id"] not in pack_group_ids:
            repo.update_group_fields(old_g["id"], enabled=False)
            for old_p in repo.list_phrases(old_g["id"]):
                if old_p["pack_id"] == pack["id"]:
                    repo.set_phrase_enabled(old_p["id"], False)

    repo.set_meta(META_KEY, str(pack["version"]))
    logger.info(f"builtin pack v{pack['version']} seeded", TAG)


def reset_builtin_pack(repo: ChatRepo, pack: Optional[dict] = None):
    """强制重置内置话术包为官方默认预设（重置内容与默认热键，清除 dirty 标记）。"""
    pack = pack or BUILTIN_PACK
    logger.info(f"resetting builtin pack v{pack['version']}", TAG)
    for g in pack["groups"]:
        repo.upsert_group(g["id"], g["name"], hotkey=g["hotkey"],
                          sort=g["sort"], pack_id=pack["id"])
        repo.update_group_fields(g["id"], enabled=True, hotkey=g["hotkey"])
        for p in g["phrases"]:
            repo.upsert_phrase(p["id"], g["id"], p["content"],
                               sort=p["sort"], pack_id=pack["id"])
            with repo.db.lock:
                repo.db.conn().execute(
                    "UPDATE phrase SET dirty=0, enabled=1, content=? WHERE id=?",
                    (p["content"], p["id"]))
                repo.db.conn().commit()
    repo.set_meta(META_KEY, str(pack["version"]))


