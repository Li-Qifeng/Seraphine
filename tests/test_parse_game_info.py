"""
Mock 契约测试: 验证 parseGameInfoByGameflowSession 的输出契约.

覆盖:
- 不支持队列早返回 None (1700/1090/1100/1110/1130/1160)
- side='ally'/'enemy' 选队正确
- separateTeams 找不到 currentSummonerId 时返回 None
- FIXME 修复契约: 上局名单泄露时去重 (重复 summonerId / summonerId==0 / None 被过滤)
- 去重后空 team 返回 None
- parseSummonerGameInfo 返回 None 时被过滤
- 返回结构 {'summoners', 'champions', 'order'}
- ranked (420/440) 按 selectedPosition 排序
- useSGP 路径: isInTencent 控制是否走 SGP, SGP 异常时 fallback

不依赖真实 LCU 客户端, 不发起真实网络请求.
"""
import asyncio
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lol.tools import parseGameInfoByGameflowSession


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """在独立事件循环中运行协程 (不依赖 pytest-asyncio)."""
    return asyncio.run(coro)


def _make_session(queue_id, team_one, team_two):
    """构造 gameflow session 结构 (只保留 parseGameInfoByGameflowSession 用到的字段)."""
    return {
        'gameData': {
            'queue': {'id': queue_id},
            'teamOne': team_one,
            'teamTwo': team_two,
        }
    }


def _player(summoner_id, champion_id=1, selected_position=None):
    """构造 team participant."""
    p = {'summonerId': summoner_id, 'championId': champion_id}
    if selected_position is not None:
        p['selectedPosition'] = selected_position
    return p


def _patch_parse(returns_by_id=None, default=None):
    """patch parseSummonerGameInfo 为按 summonerId 返回固定 dict 的 async mock.

    returns_by_id: {summonerId: dict | None} 显式覆盖; 未覆盖的走 default
    default: callable(item) -> dict | None, 默认透传真实 parseSummonerGameInfo 的关键字段
    """
    returns_by_id = returns_by_id or {}

    async def mock_parse(item, qid, csid):
        sid = item['summonerId']
        if sid in returns_by_id:
            return returns_by_id[sid]
        if default is not None:
            return default(item)
        # 与真实 parseSummonerGameInfo 返回结构对齐 (至少包含 sortedSummonersByGameRole
        # 在 ranked 模式下读的 selectedPosition 字段; 缺省 None 会让排序跳过)
        return {
            'summonerId': sid,
            'championId': item['championId'],
            'selectedPosition': item.get('selectedPosition'),
        }

    return patch("app.lol.tools.parseSummonerGameInfo", new=mock_parse)


# ---------------------------------------------------------------------------
# 早期返回 None 契约
# ---------------------------------------------------------------------------

class TestEarlyReturns:
    @pytest.mark.parametrize("queue_id", [1700, 1090, 1100, 1110, 1130, 1160])
    def test_unsupported_queue_returns_none(self, queue_id):
        session = _make_session(queue_id, [_player(1)], [_player(2)])
        assert _run(parseGameInfoByGameflowSession(session, 1, 'ally')) is None

    def test_current_summoner_not_in_either_team_returns_none(self):
        session = _make_session(420, [_player(1)], [_player(2)])
        # currentSummonerId=99 不在任一队, separateTeams 返回 (None, None)
        assert _run(parseGameInfoByGameflowSession(session, 99, 'ally')) is None

    def test_empty_team_after_dedupe_returns_none(self):
        # teamOne 全是 summonerId=0, 去重后为空
        session = _make_session(420, [_player(0), _player(0)], [_player(1)])
        # currentSummonerId=1 在 teamTwo, side='enemy' 取 teamOne, 去重后空 → None
        assert _run(parseGameInfoByGameflowSession(session, 1, 'enemy')) is None


# ---------------------------------------------------------------------------
# side 选队契约
# ---------------------------------------------------------------------------

class TestSideSelection:
    def test_side_ally_returns_team_with_current_summoner(self):
        # currentSummonerId=1 在 teamOne, ally 应取 teamOne
        session = _make_session(
            420,
            [_player(1, champion_id=10), _player(2, champion_id=20)],
            [_player(3, champion_id=30)],
        )
        with _patch_parse():
            result = _run(parseGameInfoByGameflowSession(session, 1, 'ally'))
        assert result is not None
        assert [s['summonerId'] for s in result['summoners']] == [1, 2]

    def test_side_enemy_returns_opposing_team(self):
        session = _make_session(
            420,
            [_player(1, champion_id=10)],
            [_player(2, champion_id=20), _player(3, champion_id=30)],
        )
        with _patch_parse():
            result = _run(parseGameInfoByGameflowSession(session, 1, 'enemy'))
        assert result is not None
        assert [s['summonerId'] for s in result['summoners']] == [2, 3]


# ---------------------------------------------------------------------------
# FIXME 修复契约: 去重过滤 (上局名单泄露场景)
# ---------------------------------------------------------------------------

class TestDedupeContract:
    def test_duplicate_summoner_id_keeps_first_occurrence(self):
        # FIXME 场景: teamTwo 泄露了上一局 teamOne 的 summonerId=2
        # 同一 summonerId 出现两次 (championId 不同), 应保留首次
        session = _make_session(
            420,
            [_player(1, champion_id=10)],
            [_player(2, champion_id=20), _player(2, champion_id=99), _player(3, champion_id=30)],
        )
        called_ids = []

        async def mock_parse(item, qid, csid):
            called_ids.append(item['summonerId'])
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item.get('selectedPosition'),
            }

        with patch("app.lol.tools.parseSummonerGameInfo", new=mock_parse):
            result = _run(parseGameInfoByGameflowSession(session, 1, 'enemy'))

        assert result is not None
        # 重复的 summonerId=2 只保留首次 (championId=20), 3 保留
        ids = [s['summonerId'] for s in result['summoners']]
        assert ids == [2, 3]
        assert [s['championId'] for s in result['summoners']] == [20, 30]
        # parseSummonerGameInfo 只被调用 2 次 (重复项被去重前过滤)
        assert called_ids == [2, 3]

    def test_zero_and_none_summoner_id_filtered(self):
        session = _make_session(
            420,
            [_player(0, champion_id=10), {'summonerId': None, 'championId': 11},
             _player(1, champion_id=12)],
            [_player(2, champion_id=20)],
        )
        called_ids = []

        async def mock_parse(item, qid, csid):
            called_ids.append(item['summonerId'])
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item.get('selectedPosition'),
            }

        with patch("app.lol.tools.parseSummonerGameInfo", new=mock_parse):
            result = _run(parseGameInfoByGameflowSession(session, 1, 'ally'))

        assert result is not None
        # summonerId=0 和 None 被过滤, 只剩 summonerId=1
        assert [s['summonerId'] for s in result['summoners']] == [1]
        assert called_ids == [1]


# ---------------------------------------------------------------------------
# 返回结构契约
# ---------------------------------------------------------------------------

class TestReturnStructure:
    def test_structure_and_champions_map(self):
        session = _make_session(
            420,
            [_player(1, champion_id=10), _player(2, champion_id=20)],
            [_player(3, champion_id=30)],
        )
        with _patch_parse():
            result = _run(parseGameInfoByGameflowSession(session, 1, 'ally'))

        assert set(result.keys()) == {'summoners', 'champions', 'order'}
        assert result['champions'] == {1: 10, 2: 20}
        assert result['order'] == [1, 2]

    def test_none_results_filtered_from_summoners(self):
        # parseSummonerGameInfo 对 summonerId=2 返回 None (例如 nameVisibilityType=HIDDEN)
        session = _make_session(
            420,
            [_player(1, champion_id=10), _player(2, champion_id=20), _player(3, champion_id=30)],
            [_player(4, champion_id=40)],
        )
        with _patch_parse(returns_by_id={2: None}):
            result = _run(parseGameInfoByGameflowSession(session, 1, 'ally'))

        assert result is not None
        assert [s['summonerId'] for s in result['summoners']] == [1, 3]
        assert result['order'] == [1, 3]
        assert result['champions'] == {1: 10, 3: 30}


# ---------------------------------------------------------------------------
# ranked (420/440) 排序契约
# ---------------------------------------------------------------------------

class TestRankedSort:
    def test_ranked_sorts_by_role(self):
        session = _make_session(
            420,
            [
                _player(1, champion_id=10, selected_position='MIDDLE'),
                _player(2, champion_id=20, selected_position='TOP'),
                _player(3, champion_id=30, selected_position='JUNGLE'),
                _player(4, champion_id=40, selected_position='BOTTOM'),
                _player(5, champion_id=50, selected_position='UTILITY'),
            ],
            [_player(6, champion_id=60)],
        )

        def with_position(item):
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item['selectedPosition'],
            }

        with _patch_parse(default=with_position):
            result = _run(parseGameInfoByGameflowSession(session, 1, 'ally'))

        # TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY
        assert [s['summonerId'] for s in result['summoners']] == [2, 3, 1, 4, 5]

    def test_ranked_invalid_position_skips_sort(self):
        session = _make_session(
            420,
            [
                _player(1, champion_id=10, selected_position='MIDDLE'),
                _player(2, champion_id=20, selected_position='INVALID'),
            ],
            [_player(6, champion_id=60)],
        )

        def with_position(item):
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item['selectedPosition'],
            }

        with _patch_parse(default=with_position):
            result = _run(parseGameInfoByGameflowSession(session, 1, 'ally'))

        # sortedSummonersByGameRole 返回 None, 保持原顺序
        assert [s['summonerId'] for s in result['summoners']] == [1, 2]

    def test_non_ranked_does_not_sort(self):
        # queueId=400 (普通匹配) 不在 [420, 440]
        session = _make_session(
            400,
            [
                _player(1, champion_id=10, selected_position='MIDDLE'),
                _player(2, champion_id=20, selected_position='TOP'),
            ],
            [_player(6, champion_id=60)],
        )

        def with_position(item):
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item['selectedPosition'],
            }

        with _patch_parse(default=with_position):
            result = _run(parseGameInfoByGameflowSession(session, 1, 'ally'))

        assert [s['summonerId'] for s in result['summoners']] == [1, 2]


# ---------------------------------------------------------------------------
# useSGP 路径契约
# ---------------------------------------------------------------------------

class TestSGPPath:
    def test_sgp_used_when_useSGP_and_in_tencent(self):
        session = _make_session(
            420,
            [_player(1, champion_id=10)],
            [_player(2, champion_id=20)],
        )

        sgp_calls = []
        parse_calls = []

        async def mock_sgp(item, qid, csid):
            sgp_calls.append(item['summonerId'])
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item.get('selectedPosition'),
            }

        async def mock_parse(item, qid, csid):
            parse_calls.append(item['summonerId'])
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item.get('selectedPosition'),
            }

        with patch("app.lol.tools.getSummonerGamesInfoViaSGP", new=mock_sgp), \
                patch("app.lol.tools.parseSummonerGameInfo", new=mock_parse), \
                patch("app.lol.tools.connector.isInTencent", return_value=True):
            result = _run(parseGameInfoByGameflowSession(session, 1, 'enemy', useSGP=True))

        assert sgp_calls == [2]
        assert parse_calls == []
        assert result is not None
        assert [s['summonerId'] for s in result['summoners']] == [2]

    def test_sgp_fallback_to_parse_on_exception(self):
        session = _make_session(
            420,
            [_player(1, champion_id=10)],
            [_player(2, champion_id=20)],
        )

        sgp_calls = []
        parse_calls = []

        async def mock_sgp(item, qid, csid):
            sgp_calls.append(item['summonerId'])
            raise RuntimeError("SGP down")

        async def mock_parse(item, qid, csid):
            parse_calls.append(item['summonerId'])
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item.get('selectedPosition'),
            }

        with patch("app.lol.tools.getSummonerGamesInfoViaSGP", new=mock_sgp), \
                patch("app.lol.tools.parseSummonerGameInfo", new=mock_parse), \
                patch("app.lol.tools.connector.isInTencent", return_value=True):
            result = _run(parseGameInfoByGameflowSession(session, 1, 'enemy', useSGP=True))

        assert sgp_calls == [2]  # SGP 被调用但抛异常
        assert parse_calls == [2]  # fallback 到 parseSummonerGameInfo
        assert result is not None

    def test_sgp_not_used_when_not_in_tencent(self):
        session = _make_session(
            420,
            [_player(1, champion_id=10)],
            [_player(2, champion_id=20)],
        )

        sgp_calls = []
        parse_calls = []

        async def mock_sgp(item, qid, csid):
            sgp_calls.append(item['summonerId'])
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item.get('selectedPosition'),
            }

        async def mock_parse(item, qid, csid):
            parse_calls.append(item['summonerId'])
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item.get('selectedPosition'),
            }

        with patch("app.lol.tools.getSummonerGamesInfoViaSGP", new=mock_sgp), \
                patch("app.lol.tools.parseSummonerGameInfo", new=mock_parse), \
                patch("app.lol.tools.connector.isInTencent", return_value=False):
            result = _run(parseGameInfoByGameflowSession(session, 1, 'enemy', useSGP=True))

        assert sgp_calls == []
        assert parse_calls == [2]
        assert result is not None

    def test_sgp_not_used_when_useSGP_false(self):
        session = _make_session(
            420,
            [_player(1, champion_id=10)],
            [_player(2, champion_id=20)],
        )

        sgp_calls = []
        parse_calls = []

        async def mock_sgp(item, qid, csid):
            sgp_calls.append(item['summonerId'])
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item.get('selectedPosition'),
            }

        async def mock_parse(item, qid, csid):
            parse_calls.append(item['summonerId'])
            return {
                'summonerId': item['summonerId'],
                'championId': item['championId'],
                'selectedPosition': item.get('selectedPosition'),
            }

        with patch("app.lol.tools.getSummonerGamesInfoViaSGP", new=mock_sgp), \
                patch("app.lol.tools.parseSummonerGameInfo", new=mock_parse), \
                patch("app.lol.tools.connector.isInTencent", return_value=True):
            result = _run(parseGameInfoByGameflowSession(session, 1, 'enemy', useSGP=False))

        assert sgp_calls == []
        assert parse_calls == [2]
        assert result is not None
