# -*- coding: utf-8 -*-
"""horse_orchestrator 单元测试: BP 聊天窗播报编排层 (可见段位, 零网络)."""
import asyncio

import pytest

from app.lol import horse_orchestrator as ho
from app.lol.horse_rating_cache import clear as clear_cache, set_horse_verdict


@pytest.fixture(autouse=True)
def _clean():
    clear_cache()
    yield
    clear_cache()


def _summoner(name, puuid, tier=3, div=0, lp=50):
    return {"puuid": puuid, "gameName": name, "tagLine": "cn1",
            "tierIdx": tier, "divisionIdx": div, "lp": lp}


def test_empty_summoners_returns_none():
    assert asyncio.run(ho.buildHorseReport([])) is None


def test_cache_hit_skips_rate():
    v = {"score": 85, "grade": "通天代", "reason": ""}
    set_horse_verdict("puuid-1", v)
    msg = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1")], style="horse"))
    assert msg is not None
    assert "Alice" in msg
    assert "85" in msg


def test_cache_miss_rates_from_visible_rank_and_writes_cache():
    msg = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1", tier=8)],
                            style="horse"))
    assert msg is not None
    assert "Alice" in msg
    # 第二次调用应命中缓存
    from app.lol.horse_rating_cache import get_horse_verdict
    assert get_horse_verdict("puuid-1") is not None
    msg2 = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1", tier=8)],
                            style="horse"))
    assert msg2 == msg


def test_missing_rank_degrades_to_unknown_without_abort():
    msg = asyncio.run(ho.buildHorseReport(
        [{"puuid": "puuid-1", "gameName": "Alice", "tagLine": "cn1"},
         _summoner("Bob", "puuid-2", tier=7)], style="horse"))
    assert msg is not None
    assert "Alice" in msg and "Bob" in msg
    # 缺可见段位者降级为 Unknown 且无分数, 未知行附带原因
    assert "未知战绩(缺少可见段位，无法评价): Alice" in msg


def test_message_format_prefix_label_score():
    set_horse_verdict("puuid-1", {"score": 85, "grade": "通天代", "reason": ""})
    set_horse_verdict("puuid-2", {"score": 52, "grade": "中等马", "reason": ""})
    # 按分数阈值定档 (与 UI 徽章同口径): 85=通天代, 52=中等马
    msg = asyncio.run(ho.buildHorseReport(
        [_summoner("Alice", "puuid-1"), _summoner("Bob", "puuid-2")],
        style="horse"))
    assert msg == "通天代(85): Alice 未知战绩\n中等马(52): Bob 未知战绩"


def test_user_scheme_style_switches_labels():
    from unittest.mock import patch

    custom = {'我的马': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']}
    set_horse_verdict("puuid-1", {"score": 85, "grade": "通天代", "reason": ""})
    with patch('app.lol.horse_rating._user_horse_schemes',
               return_value=custom):
        msg = asyncio.run(ho.buildHorseReport(
            [_summoner("Alice", "puuid-1")], style="我的马"))
        assert msg == "S1(85): Alice 未知战绩"


def test_random_style_resolves_once_for_team():
    import app.lol.horse_rating as hr
    from app.lol.horse_rating_cache import get_horse_verdict

    set_horse_verdict("puuid-1", {"score": 85, "grade": "通天代", "reason": ""})
    set_horse_verdict("puuid-2", {"score": 52, "grade": "中等马", "reason": ""})

    async def run():
        return await ho.fetchVerdictsForTeam(
            [_summoner("Alice", "puuid-1"), _summoner("Bob", "puuid-2")],
            style=hr.HORSE_RANDOM_KEY)

    results = asyncio.run(run())
    # 同批 (一局) 只抽一次: 全队 verdict 烘焙同一个方案
    schemes = {v.get("scheme") for v in results.values()}
    assert len(schemes) == 1
    assert schemes.pop() in hr.horse_scheme_names()
    # 缓存条目不被批次 scheme 字段污染 (深拷贝隔离)
    for p in ("puuid-1", "puuid-2"):
        assert "scheme" not in get_horse_verdict(p)


def test_unknown_style_falls_back_to_default():
    set_horse_verdict("puuid-1", {"score": 85, "grade": "通天代", "reason": ""})
    msg = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1")], style="不存在的方案"))
    assert msg == "通天代(85): Alice 未知战绩"


def test_default_style_reads_cfg(monkeypatch):
    monkeypatch.setattr(ho, "_current_style", lambda: "horse")
    set_horse_verdict("puuid-1", {"score": 20, "grade": "牛马", "reason": ""})
    set_horse_verdict("puuid-2", {"score": 90, "grade": "通天代", "reason": ""})
    # 默认风格读 cfg + 按评分排序 (高分段在前), 按分数阈值定档
    msg = asyncio.run(ho.buildHorseReport(
        [_summoner("Bob", "puuid-2"), _summoner("Alice", "puuid-1")]))
    lines = msg.splitlines()
    assert lines[0].startswith("通天代(90): Bob")
    assert lines[1].startswith("牛马(20): Alice")


def test_uses_games_for_winrate_and_ranks_team():
    """从原始 summoner(gamesInfo+kda)提取战绩参与三维评分, 并按分阈值定档."""
    a = {"puuid": "p1", "gameName": "A", "tagLine": "cn1",
         "tierIdx": 5, "divisionIdx": 0, "lp": 50,
         "gamesInfo": [{"win": True, "remake": False, "kills": 10, "deaths": 2, "assists": 6},
                       {"win": True, "remake": False, "kills": 7, "deaths": 4, "assists": 5},
                       {"win": False, "remake": False, "kills": 0, "deaths": 2, "assists": 1}]}
    b = {"puuid": "p2", "gameName": "B", "tagLine": "cn1",
         "tierIdx": 5, "divisionIdx": 0, "lp": 50,
         "gamesInfo": [{"win": False, "remake": False, "kills": 2, "deaths": 8, "assists": 2},
                       {"win": False, "remake": False, "kills": 1, "deaths": 5, "assists": 0}]}
    msg = asyncio.run(ho.buildHorseReport([a, b], style="horse"))
    # 双方 KDA 明细均拼接进播报 (hh 逐名一行格式)
    assert "10-2-6  7-4-5  0-2-1" in msg
    assert "2-8-2  1-5-0" in msg


def test_queue_group_mapping():
    assert ho._queue_group(420) == (420, 440)
    assert ho._queue_group(440) == (420, 440)
    assert ho._queue_group(450) == (450, 2400)
    assert ho._queue_group(2400) == (450, 2400)
    assert ho._queue_group(430) == (430,)
    assert ho._queue_group(None) is None


def test_build_horse_report_filters_by_ranked_group():
    """排位大厅 (queue_id=440) 只统计 420/440 的对局, KDA 串与平均KDA 同步过滤."""
    s = {"puuid": "p1", "gameName": "A", "tagLine": "cn1",
         "tierIdx": 5, "divisionIdx": 0, "lp": 50,
         "gamesInfo": [
             {"queueId": 420, "win": True, "remake": False,
              "kills": 10, "deaths": 2, "assists": 6},
             {"queueId": 440, "win": True, "remake": False,
              "kills": 7, "deaths": 4, "assists": 5},
             {"queueId": 450, "win": False, "remake": False,
              "kills": 0, "deaths": 10, "assists": 0}]}
    msg = asyncio.run(ho.buildHorseReport([s], style="horse", queue_id=440))
    # 大乱斗局被滤掉: 串只剩排位局, 平均KDA = (10+7+6+5)/(2+4) = 4.67
    assert "10-2-6  7-4-5" in msg
    assert "0-10-0" not in msg
    assert msg.endswith(" 平均KDA 4.67")


def test_build_horse_report_merges_aram_groups():
    """海克斯大乱斗 (queue_id=2400) 合并经典 450 一起统计."""
    s = {"puuid": "p1", "gameName": "A", "tagLine": "cn1",
         "tierIdx": 5, "divisionIdx": 0, "lp": 50,
         "gamesInfo": [
             {"queueId": 450, "win": True, "remake": False,
              "kills": 10, "deaths": 5, "assists": 5},
             {"queueId": 2400, "win": True, "remake": False,
              "kills": 5, "deaths": 5, "assists": 5}]}
    msg = asyncio.run(ho.buildHorseReport([s], style="horse", queue_id=2400))
    assert "10-5-5  5-5-5" in msg
    assert msg.endswith(" 平均KDA 2.50")  # (10+5+5+5)/(5+5)


def test_rate_with_stats_bypasses_statless_cache():
    """概览任务预置的无战绩缓存不应覆盖 BP 带 gamesInfo 的实时评分."""
    set_horse_verdict("puuid-1", {"score": 20, "grade": "牛马", "reason": ""})
    s = {"puuid": "puuid-1", "gameName": "Alice", "tagLine": "cn1",
         "tierIdx": 5, "divisionIdx": 0, "lp": 50,
         "gamesInfo": [{"win": True, "remake": False,
                        "kills": 10, "deaths": 1, "assists": 8}]}
    msg = asyncio.run(ho.buildHorseReport([s], style="horse"))
    assert "牛马(20)" not in msg


def test_no_avg_kda_when_no_games():
    set_horse_verdict("puuid-1", {"score": 85, "grade": "通天代", "reason": ""})
    msg = asyncio.run(ho.buildHorseReport(
        [_summoner("Alice", "puuid-1")], style="horse"))
    assert "平均KDA" not in msg


class TestSendGuard:
    def test_acquire_once_per_game(self):
        g = ho.SendGuard()
        assert g.try_acquire() is True
        assert g.try_acquire() is False

    def test_reset_reallows(self):
        g = ho.SendGuard()
        g.try_acquire()
        g.reset()
        assert g.try_acquire() is True


def test_tier_name_to_idx():
    assert ho.tierNameToIdx("黄金") == 3
    assert ho.tierNameToIdx("王者") == 8
    assert ho.tierNameToIdx("宗师") == 8
    assert ho.tierNameToIdx(None) is None
    assert ho.tierNameToIdx("未定级") is None


def test_division_name_to_idx():
    assert ho.divisionNameToIdx("I") == 0
    assert ho.divisionNameToIdx("II") == 1
    assert ho.divisionNameToIdx("Ⅲ") == 2
    assert ho.divisionNameToIdx("IV") == 3
    assert ho.divisionNameToIdx(None) is None
    assert ho.divisionNameToIdx("--") is None


def test_fetch_verdicts_for_team_maps_by_puuid():
    async def run():
        return await ho.fetchVerdictsForTeam(
            [_summoner("A", "puuid-a", tier=6, div=0, lp=80),
             _summoner("B", "puuid-b", tier=2)])

    results = asyncio.run(run())
    assert set(results) == {"puuid-a", "puuid-b"}
    assert all(v["score"] is not None for v in results.values())


def test_fetch_verdicts_single_failure_degrades():
    async def run():
        return await ho.fetchVerdictsForTeam(
            [_summoner("A", "puuid-a", tier=6),
             {"puuid": "puuid-b", "gameName": "void"}])

    results = asyncio.run(run())
    assert results["puuid-a"]["score"] is not None
    assert results["puuid-b"]["grade"] == "Unknown"


def test_fetch_verdicts_skips_missing_puuid():
    async def run():
        return await ho.fetchVerdictsForTeam([{"gameName": "X"}])

    assert asyncio.run(run()) == {}


def test_report_grades_by_score_threshold():
    """播报按分数阈值定档 (与 UI 徽章同口径); 同档并列标注队内名次."""
    set_horse_verdict("puuid-1", {"score": 80, "grade": "小代", "reason": ""})
    set_horse_verdict("puuid-2", {"score": 75, "grade": "小代", "reason": ""})
    set_horse_verdict("puuid-3", {"score": 60, "grade": "上等马", "reason": ""})
    msg = asyncio.run(ho.buildHorseReport(
        [_summoner("A", "puuid-1"), _summoner("B", "puuid-2"),
         _summoner("C", "puuid-3")], style="horse"))
    lines = msg.splitlines()
    # 80/75 同属小代档 -> 并列标队内名次; 60 上等马单独一档不标
    assert lines[0].startswith("小代(80·队内#1): A")
    assert lines[1].startswith("小代(75·队内#2): B")
    assert lines[2].startswith("上等马(60): C")


def test_verdicts_carry_baked_scheme_for_overview():
    """对局页概览: fetchVerdictsForTeam 烘焙同批统一 scheme (随机风格同局一致)."""
    async def run():
        return await ho.fetchVerdictsForTeam(
            [_summoner("A", "p1", tier=6), _summoner("B", "p2", tier=6),
             _summoner("C", "p3", tier=6)], queue_id=420)

    results = asyncio.run(run())
    filled = [v for v in results.values() if v.get('score') is not None]
    assert filled  # 三人都有可见段位 -> 都有分
    schemes = {v.get("scheme") for v in filled}
    assert len(schemes) == 1
    assert schemes.pop() is not None


def test_uses_tier_by_mode():
    """大乱斗/海克斯只看 KDA; 排位/匹配参考段位; 未知名默认参考段位."""
    assert ho._uses_tier(450) is False
    assert ho._uses_tier(2400) is False
    assert ho._uses_tier(420) is True
    assert ho._uses_tier(440) is True
    assert ho._uses_tier(430) is True
    assert ho._uses_tier(None) is True


def test_rate_by_mode_ignores_tier_in_aram():
    """同一高段位玩家: 排位大厅因段位高分, 大乱斗因低 KDA 低分 (只按战绩)."""
    s = {"puuid": "p1", "gameName": "A", "tagLine": "cn1",
         "tierIdx": 8, "divisionIdx": 0, "lp": 90,
         "gamesInfo": [
             {"queueId": 450, "win": True, "remake": False,
              "kills": 1, "deaths": 5, "assists": 1},
             {"queueId": 2400, "win": False, "remake": False,
              "kills": 1, "deaths": 5, "assists": 0}]}
    ranked = asyncio.run(ho.buildHorseReport([s], style="horse", queue_id=440))
    aram = asyncio.run(ho.buildHorseReport([s], style="horse", queue_id=450))
    # 排位: 段位轴参与 (王者), 分数应高于纯 KDA 的大乱斗
    ranked_score = _extract_score(ranked)
    aram_score = _extract_score(aram)
    assert aram_score is not None and ranked_score is not None
    assert ranked_score > aram_score
    # 大乱斗只统计 450/2400, 平均KDA = (1+1+1+0)/(5+5) = 0.30
    assert "平均KDA 0.30" in aram


def test_rate_by_mode_ignores_missing_tier_in_aram():
    """大乱斗无段位也能按 KDA 出分 (此前只看段位会 Unknown 无徽章)."""
    s = {"puuid": "p1", "gameName": "A", "tagLine": "cn1",
         "tierIdx": None, "divisionIdx": None, "lp": None,
         "gamesInfo": [
             {"queueId": 450, "win": True, "remake": False,
              "kills": 8, "deaths": 3, "assists": 4},
             {"queueId": 450, "win": True, "remake": False,
              "kills": 6, "deaths": 2, "assists": 6}]}
    msg = asyncio.run(ho.buildHorseReport([s], style="horse", queue_id=450))
    assert msg is not None
    assert "Unknown" not in msg
    assert "(" in msg  # 有分


def _extract_score(msg):
    """从 '标签(score): ...' 播报行提取分数 (无分返回 None)."""
    for line in (msg or "").splitlines():
        head = line.split(":")[0]
        if "(" in head and ")" in head:
            try:
                return int(head.split("(")[1].split(")")[0])
            except ValueError:
                return None
    return None
