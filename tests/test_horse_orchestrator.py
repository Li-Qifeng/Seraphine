# -*- coding: utf-8 -*-
"""horse_orchestrator 单元测试: BP 聊天窗播报编排层."""
import asyncio

import pytest

from app.lol import horse_orchestrator as ho
from app.lol.horse_rating_cache import clear as clear_cache, set_horse_verdict


class FakeLzyumi:
    """可注入的 lzyumi 替身."""

    def __init__(self, players=None, fail_names=()):
        # nickname -> {'battleInfo': {...}, 'games': [...]}
        self.players = players or {}
        self.fail_names = set(fail_names)
        self.search_calls = []
        self.elo_calls = []

    async def searchPlayer(self, nickname, area_id, count=10):
        self.search_calls.append(nickname)
        if nickname in self.fail_names:
            raise ho.LzyumiUnavailable("network down")
        return self.players[nickname]

    async def getRankEloInfo(self, open_id, area_id=16):
        self.elo_calls.append(open_id)
        return {"solo": 1500, "flex": None, "aram": None}


@pytest.fixture(autouse=True)
def _clean():
    clear_cache()
    yield
    clear_cache()


def _summoner(name, puuid):
    return {"puuid": puuid, "gameName": name, "tagLine": "cn1", "tierIdx": 3}


def test_empty_summoners_returns_none():
    fake = FakeLzyumi()
    ho.lzyumi = fake
    assert asyncio.run(ho.buildHorseReport([], 16)) is None


def test_all_cache_hits_skip_network():
    fake = FakeLzyumi()
    ho.lzyumi = fake
    v = {"score": 85, "grade": "上等马", "style_labels": {}, "reason": ""}
    set_horse_verdict("puuid-1", v)
    msg = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1")], 16, style="horse"))
    assert msg is not None
    assert msg.startswith("[Seraphine]")
    assert "85分" in msg
    assert fake.search_calls == [] and fake.elo_calls == []


def test_cache_miss_goes_through_lzyumi_and_writes_cache():
    fake = FakeLzyumi(players={
        "Alice#cn1": {
            "battleInfo": {"openId": "openid-A"},
            "games": [{"isWin": True, "isMvp": True, "isSvp": False}] * 10,
        },
    })
    ho.lzyumi = fake
    msg = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1")], 16, style="horse"))
    assert fake.search_calls == ["Alice#cn1"]
    assert fake.elo_calls == ["openid-A"]
    assert "Alice(" in msg
    # 第二次调用应命中缓存, 不再发网络
    calls = len(fake.search_calls)
    asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1")], 16, style="horse"))
    assert len(fake.search_calls) == calls


def test_single_failure_degrades_to_unknown_without_abort():
    fake = FakeLzyumi(
        players={
            "Bob#cn1": {
                "battleInfo": {"openId": "openid-B"},
                "games": [{"isWin": True, "isMvp": False, "isSvp": False},
                          {"isWin": False, "isMvp": False, "isSvp": False}],
            },
        },
        fail_names=("Alice#cn1",),
    )
    ho.lzyumi = fake
    msg = asyncio.run(ho.buildHorseReport(
        [_summoner("Alice", "puuid-1"), _summoner("Bob", "puuid-2")], 16,
        style="horse"))
    assert msg is not None
    assert "Alice" in msg and "Bob" in msg
    # 失败者降级为 Unknown 标签且无分数
    assert "未知战马: Alice" in msg


def test_message_format_prefix_label_score():
    fake = FakeLzyumi()
    ho.lzyumi = fake
    set_horse_verdict("puuid-1", {"score": 85, "grade": "上等马",
                                  "style_labels": {}, "reason": ""})
    set_horse_verdict("puuid-2", {"score": 52, "grade": "中等马",
                                  "style_labels": {}, "reason": ""})
    msg = asyncio.run(ho.buildHorseReport(
        [_summoner("Alice", "puuid-1"), _summoner("Bob", "puuid-2")], 16,
        style="horse"))
    assert msg == "[Seraphine] 上等马: Alice(85分) | 中等马: Bob(52分)"


def test_formal_style_switches_labels():
    fake = FakeLzyumi()
    ho.lzyumi = fake
    set_horse_verdict("puuid-1", {"score": 85, "grade": "上等马",
                                  "style_labels": {}, "reason": ""})
    msg = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1")], 16, style="formal"))
    assert msg == "[Seraphine] 表现优异: Alice(85分)"


def test_default_style_reads_cfg(monkeypatch):
    monkeypatch.setattr(ho, "_current_style", lambda: "formal")
    fake = FakeLzyumi()
    ho.lzyumi = fake
    set_horse_verdict("puuid-1", {"score": 20, "grade": "驽马",
                                  "style_labels": {}, "reason": ""})
    msg = asyncio.run(
        ho.buildHorseReport([_summoner("Alice", "puuid-1")], 16))
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


def test_fetch_verdicts_for_team_maps_by_puuid():
    players = {"A#cn1": {"battleInfo": {"openId": "oa"}, "games": []},
               "B#cn1": {"battleInfo": {"openId": "ob"}, "games": []}}
    fake = FakeLzyumi(players=players)
    ho.lzyumi = fake

    async def run():
        return await ho.fetchVerdictsForTeam(
            [_summoner("A", "puuid-a"), _summoner("B", "puuid-b")], 1)

    import asyncio as _a
    results = _a.run(run())
    assert set(results) == {"puuid-a", "puuid-b"}
    assert all(v["score"] is not None for v in results.values())


def test_fetch_verdicts_single_failure_degrades():
    players = {"A#cn1": {"battleInfo": {"openId": "oa"}, "games": []}}
    fake = FakeLzyumi(players=players, fail_names={"B#cn1"})
    ho.lzyumi = fake

    async def run():
        return await ho.fetchVerdictsForTeam(
            [_summoner("A", "puuid-a"), _summoner("B", "puuid-b")], 1)

    import asyncio as _a
    results = _a.run(run())
    assert results["puuid-a"]["score"] is not None
    assert results["puuid-b"]["grade"] == "Unknown"


def test_fetch_verdicts_skips_missing_puuid():
    async def run():
        return await ho.fetchVerdictsForTeam([{"gameName": "X"}], 1)

    import asyncio as _a
    assert _a.run(run()) == {}
