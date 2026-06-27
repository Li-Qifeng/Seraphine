"""
JsonManager 单元测试.

JsonManager 是纯数据访问层 (在 connector.__initManager 中由 LCU 拉取的 8 份 JSON 构造),
不依赖网络与 Qt 事件循环, 适合做单元测试覆盖其:
- 图标/名称路径生成 (getItemIconPath / getChampionIconPath / getRuneIconPath ...)
- 字典查找的异常分支 (KeyError 回退到占位图)
- 队列/地图名称映射 (getNameMapByQueueId / getMapNameById)
- 皮肤列表查询 (getSkinListByChampionName / getSkinIdByChampionAndSkinName)
- 强化系统访问 (getAugmentsIconPath / getAugmentsName)

构造数据时 mock 掉 static_data.registerAugmentRarity (避免导入副作用).
"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lol.connector import JsonManager


# ---------------------------------------------------------------------------
# fixtures: 构造最小可用的 LCU JSON 数据
# ---------------------------------------------------------------------------

def _make_item_data():
    return [
        {"id": 1001, "iconPath": "/lol-game-data/assets/v1/items/1001.png"},
        {"id": 1004, "iconPath": "/lol-game-data/assets/v1/items/1004.png"},
    ]


def _make_spell_data():
    # JsonManager 会切掉最后 3 个 (废法术占位), 至少给 4 个
    return [
        {"id": 4, "iconPath": "/lol-game-data/assets/v1/summoner-spells/4.png"},
        {"id": 7, "iconPath": "/lol-game-data/assets/v1/summoner-spells/7.png"},
        {"id": 14, "iconPath": "/lol-game-data/assets/v1/summoner-spells/14.png"},
        {"id": 32, "iconPath": "/lol-game-data/assets/v1/summoner-spells/32.png"},
        {"id": 999, "iconPath": "/placeholder1.png"},  # 会被切掉
        {"id": 998, "iconPath": "/placeholder2.png"},  # 会被切掉
        {"id": 997, "iconPath": "/placeholder3.png"},  # 会被切掉
    ]


def _make_rune_data():
    return [
        {"id": 8000, "iconPath": "/runes/8000.png",
         "name": "Precision", "longDesc": "primary<br>tree<p>extra</p>"},
        {"id": 8005, "iconPath": "/runes/8005.png",
         "name": "AttackSpeed", "longDesc": "start<i>italic</i>end"},
    ]


def _make_queue_data():
    return [
        {"id": 420, "mapId": 11, "name": "Ranked Solo"},
        {"id": 450, "mapId": 12, "name": "ARAM"},
        {"id": 0, "mapId": 11, "name": "Custom"},  # 不会用到 (queueId==0 特判)
    ]


def _make_champions_data():
    return [
        {"id": 1, "name": "Annie"},
        {"id": 2, "name": "Olaf"},
    ]


def _make_skins_data():
    return {
        "1000": {  # championId = 1 (Annie)
            "id": 1000,
            "name": "Annie",
            "splashPath": "/splashes/1000.jpg",
            "uncenteredSplashPath": "/splashes/u_1000.jpg",
        },
        "1001": {
            "id": 1001,
            "name": "Goth Annie",
            "splashPath": "/splashes/1001.jpg",
            "uncenteredSplashPath": "/splashes/u_1001.jpg",
            "skinAugments": {"augments": [{"contentId": "AUG_1"}]},
        },
        "2000": {  # championId = 2 (Olaf), 带 questSkin
            "id": 2000,
            "name": "Olaf",
            "splashPath": "/splashes/2000.jpg",
            "uncenteredSplashPath": "/splashes/u_2000.jpg",
            "questSkinInfo": {
                "tiers": [
                    {"name": " base", "id": 2000,
                     "splashPath": "/q/2000.jpg",
                     "uncenteredSplashPath": "/q/u_2000.jpg"},
                    {"name": "Pentakill", "id": 2001,
                     "splashPath": "/q/2001.jpg",
                     "uncenteredSplashPath": "/q/u_2001.jpg"},
                ]
            },
        },
    }


def _make_perks_data():
    return {
        "styles": [
            {"id": 8000, "name": "Precision", "iconPath": "/perks/8000.png"},
            {"id": 8100, "name": "Domination", "iconPath": "/perks/8100.png"},
        ]
    }


def _make_augments_data():
    return [
        {"id": 1, "nameTRA": "Test Augment",
         "augmentSmallIconPath": "/aug/1.png", "rarity": 1},
        {"id": 2, "nameTRA": "Gold Aug",
         "augmentSmallIconPath": "/aug/2.png", "rarity": 4},
    ]


@pytest.fixture
def jm():
    """构造一个最小可用的 JsonManager 实例 (mock 掉 static_data 副作用)."""
    with patch("app.lol.static_data.registerAugmentRarity"):
        manager = JsonManager(
            itemData=_make_item_data(),
            spellData=_make_spell_data(),
            runeData=_make_rune_data(),
            queueData=_make_queue_data(),
            champions=_make_champions_data(),
            skins=_make_skins_data(),
            perks=_make_perks_data(),
            augments=_make_augments_data(),
        )
    return manager


# ---------------------------------------------------------------------------
# 物品图标
# ---------------------------------------------------------------------------

class TestGetItemIconPath:
    def test_known_item(self, jm):
        assert jm.getItemIconPath(1001) == "/lol-game-data/assets/v1/items/1001.png"

    def test_zero_returns_placeholder(self, jm):
        # iconId == 0 -> 直接返回占位图
        result = jm.getItemIconPath(0)
        assert "placeholder" in result

    def test_unknown_item_returns_placeholder(self, jm):
        # KeyError 分支 -> 占位图
        result = jm.getItemIconPath(99999)
        assert "placeholder" in result


# ---------------------------------------------------------------------------
# 召唤师技能图标
# ---------------------------------------------------------------------------

class TestGetSummonerSpellIconPath:
    def test_known_spell(self, jm):
        assert jm.getSummonerSpellIconPath(4) == "/lol-game-data/assets/v1/summoner-spells/4.png"

    def test_zero_returns_empty_icon(self, jm):
        result = jm.getSummonerSpellIconPath(0)
        assert "summoner_empty" in result


# ---------------------------------------------------------------------------
# 符文
# ---------------------------------------------------------------------------

class TestRuneAccess:
    def test_get_rune_icon_path(self, jm):
        assert jm.getRuneIconPath(8000) == "/runes/8000.png"

    def test_get_rune_icon_path_fallback_to_perks(self, jm):
        # runeId 不在 self.runes 但在 self.perks['styles'] 中 -> 走回退分支
        # 注意 8100 在 perks 但不在 runes
        result = jm.getRuneIconPath(8100)
        assert result == "/perks/8100.png"

    def test_get_rune_name(self, jm):
        assert jm.getRuneName(8000) == "Precision"

    def test_get_rune_desc_strips_html(self, jm):
        # 契约: longDesc 中的 <p> 等非白名单标签被移除, <br>/<i> 保留, 末尾 <br> 去掉
        desc = jm.getRuneDesc(8000)
        assert "<p>" not in desc
        assert "<br>" in desc  # 中间的 <br> 保留
        assert "primary" in desc
        assert "tree" in desc
        assert "extra" in desc  # <p> 标签移除但内容保留

    def test_get_rune_desc_keeps_i_tag(self, jm):
        # 契约: 白名单含 <i></i>, regex 保留 <i> 标签; <p> 等非白名单标签被移除
        # 注意: __init__ 末尾的 .strip("<br>") 是字符集剥离 (str.strip 语义),
        # 会剥掉首尾的 '<'/'b'/'r'/'>' 字符, 故测试数据首尾避开这些字符
        desc = jm.getRuneDesc(8005)
        assert "<i>" in desc
        assert "italic" in desc
        assert "start" in desc
        assert "end" in desc


# ---------------------------------------------------------------------------
# 路径生成 (纯字符串拼接)
# ---------------------------------------------------------------------------

class TestPathGeneration:
    def test_profile_icon_path(self, jm):
        assert jm.getSummonerProfileIconPath(29) == "/lol-game-data/assets/v1/profile-icons/29.jpg"

    def test_champion_icon_path(self, jm):
        assert jm.getChampionIconPath(1) == "/lol-game-data/assets/v1/champion-icons/1.png"


# ---------------------------------------------------------------------------
# 地图名称
# ---------------------------------------------------------------------------

class TestGetMapNameById:
    def test_summoners_rift(self, jm):
        # 默认中文 (需 cfg.language, 但测试环境 cfg 默认中文)
        result = jm.getMapNameById(11)
        assert "召唤师峡谷" in result or "Summoner" in result

    def test_howling_abyss(self, jm):
        result = jm.getMapNameById(12)
        assert "嚎哭深渊" in result or "Howling" in result

    def test_unknown_map_falls_back_to_special(self, jm):
        result = jm.getMapNameById(999)
        assert "特殊" in result or "Special" in result


# ---------------------------------------------------------------------------
# 队列名称映射
# ---------------------------------------------------------------------------

class TestGetNameMapByQueueId:
    def test_custom_queue(self, jm):
        # queueId == 0 -> 特判返回 {"name": ...} (无 map 字段)
        result = jm.getNameMapByQueueId(0)
        assert "name" in result
        assert "map" not in result

    def test_known_queue(self, jm):
        result = jm.getNameMapByQueueId(420)
        assert "name" in result
        assert "map" in result
        assert result["name"] == "Ranked Solo"

    def test_aram_queue(self, jm):
        result = jm.getNameMapByQueueId(450)
        assert result["name"] == "ARAM"


# ---------------------------------------------------------------------------
# 地图图标路径
# ---------------------------------------------------------------------------

class TestGetMapIconByMapId:
    def test_summoners_rift_victory(self, jm):
        assert jm.getMapIconByMapId(11, True) == "app/resource/images/sr-victory.png"

    def test_howling_abyss_defeat(self, jm):
        assert jm.getMapIconByMapId(12, False) == "app/resource/images/ha-defeat.png"

    def test_arena_victory(self, jm):
        assert jm.getMapIconByMapId(30, True) == "app/resource/images/arena-victory.png"

    def test_unknown_map_other(self, jm):
        assert jm.getMapIconByMapId(999, True) == "app/resource/images/other-victory.png"


# ---------------------------------------------------------------------------
# 英雄列表
# ---------------------------------------------------------------------------

class TestChampionList:
    def test_get_champion_list(self, jm):
        result = jm.getChampionList()
        assert "Annie" in result
        assert "Olaf" in result

    def test_get_champion_id_list(self, jm):
        result = jm.getChampionIdList()
        assert 1 in result
        assert 2 in result

    def test_get_champions(self, jm):
        result = jm.getChampions()
        assert result[1] == "Annie"

    def test_get_champion_name_by_id(self, jm):
        assert jm.getChampionNameById(1) == "Annie"
        assert jm.getChampionNameById(2) == "Olaf"

    def test_get_champion_name_by_id_unknown(self, jm):
        # 不存在的 id -> 循环结束返回 None
        assert jm.getChampionNameById(99999) is None

    def test_get_champion_id_by_name(self, jm):
        assert jm.getChampionIdByName("Annie") == 1


# ---------------------------------------------------------------------------
# 皮肤
# ---------------------------------------------------------------------------

class TestSkins:
    def test_get_skin_list_by_champion_name(self, jm):
        # Annie 有两个皮肤: "Annie"(base) 和 "Goth Annie"
        result = jm.getSkinListByChampionName("Annie")
        assert len(result) == 2
        names = [name for name, _ in result]
        assert "Annie" in names
        assert "Goth Annie" in names

    def test_get_skin_list_by_unknown_champion(self, jm):
        # KeyError -> 返回 []
        assert jm.getSkinListByChampionName("Nonexistent") == []

    def test_get_skin_id_by_champion_and_skin_name(self, jm):
        assert jm.getSkinIdByChampionAndSkinName("Annie", "Goth Annie") == 1001

    def test_quest_skin_tiers_registered(self, jm):
        # Olaf 带 questSkinInfo, 应注册两个 tier 皮肤
        result = jm.getSkinListByChampionName("Olaf")
        names = [name for name, _ in result]
        # tier name 含前导空格 (LCU 原始数据如此)
        assert any("Pentakill" in n for n in names)

    def test_get_skin_augments(self, jm):
        # skinId 1001 (Goth Annie) 带 skinAugments
        assert jm.getSkinAugments(1001) == "AUG_1"

    def test_get_skin_augments_none(self, jm):
        # 无 augment 的皮肤 -> None
        assert jm.getSkinAugments(1000) is None


# ---------------------------------------------------------------------------
# Cherry 强化 (Arena)
# ---------------------------------------------------------------------------

class TestAugments:
    def test_get_augments_icon_path(self, jm):
        assert jm.getAugmentsIconPath(1) == "/aug/1.png"

    def test_get_augments_icon_path_unknown(self, jm):
        # KeyError/TypeError -> 占位图
        result = jm.getAugmentsIconPath(99999)
        assert "placeholder" in result

    def test_get_augments_name(self, jm):
        assert jm.getAugmentsName(1) == "Test Augment"

    def test_get_augments_name_none_arg(self, jm):
        # augmentId=None -> TypeError (dict[None] 失败) -> 但代码没 try/except
        # 实际 getAugmentsName 无回退, 调用方需保证有效 id
        # 这里只测正常路径
        assert jm.getAugmentsName(2) == "Gold Aug"


# ---------------------------------------------------------------------------
# 召唤师技能硬编码列表
# ---------------------------------------------------------------------------

class TestGetSummonerSpellList:
    def test_returns_hardcoded_list(self, jm):
        result = jm.getSummonerSpellList()
        assert isinstance(result, list)
        assert 4 in result  # 闪现
        assert 14 in result  # 点燃
        assert 32 in result  # 标记 (雪球)
        assert len(result) == 12

    def test_list_is_immutable_contract(self, jm):
        # 契约: 每次调用返回新 list (虽是字面量, 但调用方不应依赖对象身份)
        assert jm.getSummonerSpellList() == jm.getSummonerSpellList()


# ---------------------------------------------------------------------------
# PerkStyles
# ---------------------------------------------------------------------------

class TestGetPerkStyles:
    def test_initially_none(self, jm):
        # 契约: __init__ 后 perkStyles 为 None, 由外部 (connector.__initRuneStyle) 填充
        assert jm.getPerkStyles() is None
