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
    v = {"score": 85, "grade": "上等马", "style_labels": {}, "reason": ""}
    set_horse_verdict("puuid-1", v)
    msg = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1")], style="horse"))
    assert msg is not None
    assert msg.startswith("[Seraphine]")
    assert "85分" in msg


def test_cache_miss_rates_from_visible_rank_and_writes_cache():
    msg = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1", tier=8)],
                            style="horse"))
    assert msg is not None
    assert "Alice(" in msg
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
    # 缺可见段位者降级为 Unknown 且无分数
    assert "未知战马: Alice" in msg


def test_message_format_prefix_label_score():
    set_horse_verdict("puuid-1", {"score": 85, "grade": "上等马",
                                  "style_labels": {}, "reason": ""})
    set_horse_verdict("puuid-2", {"score": 52, "grade": "中等马",
                                  "style_labels": {}, "reason": ""})
    msg = asyncio.run(ho.buildHorseReport(
        [_summoner("Alice", "puuid-1"), _summoner("Bob", "puuid-2")],
        style="horse"))
    assert msg == "[Seraphine] 上等马: Alice(85分) | 中等马: Bob(52分)"


def test_formal_style_switches_labels():
    set_horse_verdict("puuid-1", {"score": 85, "grade": "上等马",
                                  "style_labels": {}, "reason": ""})
    msg = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1")], style="formal"))
    assert msg == "[Seraphine] 表现优异: Alice(85分)"


def test_default_style_reads_cfg(monkeypatch):
    monkeypatch.setattr(ho, "_current_style", lambda: "formal")
    set_horse_verdict("puuid-1", {"score": 20, "grade": "驽马",
                                  "style_labels": {}, "reason": ""})
    msg = asyncio.run(ho.buildHorseReport([_summoner("Alice", "puuid-1")]))
    assert "数据不足建议观察: Alice(20分)" in msg


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
