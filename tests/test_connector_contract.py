"""
Mock 契约测试: 验证 LolClientConnector 方法对 LCU HTTP 响应的处理契约.

通过 mock 私有 HTTP 方法 (_LolClientConnector__get/__post/__put/__delete/__patch)
注入预设的 LCU 响应, 验证公共方法的:
- 返回值结构符合契约 (dict/list/str/bool 等)
- 异常分支按契约抛出 (SummonerNotFound/SummonerGamesNotFound 等)
  ReferenceError 由 @retry 统一拦截 (返回 None + 发射 lcuNotConnected 信号)
- 响应转换逻辑正确 (如 getGameStatus 去引号, getMapSide 取字段)

不依赖真实 LCU 客户端, 不发起真实网络请求.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lol.connector import connector
from app.lol.exceptions import (
    SummonerNotFound,
    SummonerGamesNotFound,
    SummonerRankInfoNotFound,
)


# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------

class _AsyncCM:
    """简易 async context manager, 用于 mock aiohttp 的 `async with` 语义."""

    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *exc):
        return False


class _ErrorAsyncCM:
    """进入 aenter 时抛出指定异常的 async context manager."""

    def __init__(self, exc):
        self.exc = exc

    async def __aenter__(self):
        raise self.exc

    async def __aexit__(self, *exc):
        return False


def _resp(json_data=None, text_data=None, read_data=None, status=200):
    """构造一个 mock 的 aiohttp ClientResponse."""
    resp = MagicMock()
    resp.status = status
    if json_data is not None:
        resp.json = AsyncMock(return_value=json_data)
    if text_data is not None:
        resp.text = AsyncMock(return_value=text_data)
    if read_data is not None:
        resp.read = AsyncMock(return_value=read_data)
    return resp


def _run(coro):
    """在独立事件循环中运行协程 (不依赖 pytest-asyncio)."""
    return asyncio.run(coro)


@pytest.fixture
def mock_lcu():
    """配置 connector 绕过 @needLcu 守卫与 @retry 并发限制, 测试后还原.

    - lcuSess 设为非 None: 通过 @needLcu 的 `is None` 检查
    - semaphore 设为 None: @retry 检测到后跳过并发 semaphore, 直接执行
    """
    connector.lcuSess = MagicMock()
    connector.semaphore = None
    yield connector
    connector.lcuSess = None
    connector.semaphore = None


def _patch_get(ret_val):
    """patch connector._LolClientConnector__get 为返回 ret_val 的 AsyncMock."""
    return patch.object(
        connector, '_LolClientConnector__get',
        new=AsyncMock(return_value=ret_val))


def _patch_post(ret_val):
    return patch.object(
        connector, '_LolClientConnector__post',
        new=AsyncMock(return_value=ret_val))


# ---------------------------------------------------------------------------
# 契约: getSummonerByPuuid -> dict | raise SummonerNotFound
# ---------------------------------------------------------------------------

class TestGetSummonerByPuuid:
    def test_returns_summoner_dict(self, mock_lcu):
        data = {"puuid": "abc", "summonerId": 123, "displayName": "Tester"}
        with _patch_get(_resp(json_data=data)):
            result = _run(mock_lcu.getSummonerByPuuid("abc"))
        assert result == data

    def test_error_with_httpStatus_400_raises_summoner_not_found(self, mock_lcu):
        # 契约: 响应含 errorCode 且 httpStatus==400 -> SummonerNotFound
        # (retry 装饰器对此异常不重试, 直接向上抛)
        data = {"errorCode": "BAD_REQUEST", "httpStatus": 400}
        with _patch_get(_resp(json_data=data)):
            with pytest.raises(SummonerNotFound):
                _run(mock_lcu.getSummonerByPuuid("missing"))

    def test_error_without_400_returns_dict(self, mock_lcu):
        # httpStatus 不是 400 时不抛异常, 原样返回 dict
        data = {"errorCode": "X", "httpStatus": 500}
        with _patch_get(_resp(json_data=data)):
            result = _run(mock_lcu.getSummonerByPuuid("abc"))
        assert result == data


# ---------------------------------------------------------------------------
# 契约: getSummonerGamesByPuuid -> list (games) | raise SummonerGamesNotFound
# ---------------------------------------------------------------------------

class TestGetSummonerGamesByPuuid:
    def test_returns_games_list(self, mock_lcu):
        games = [{"gameId": 1}, {"gameId": 2}]
        with _patch_get(_resp(json_data={"games": games})):
            result = _run(mock_lcu.getSummonerGamesByPuuid("abc"))
        assert result == games
        assert isinstance(result, list)

    def test_missing_games_key_raises(self, mock_lcu):
        # 契约: 响应无 "games" 字段 -> SummonerGamesNotFound
        with _patch_get(_resp(json_data={"errorCode": "not_found"})):
            with pytest.raises(SummonerGamesNotFound):
                _run(mock_lcu.getSummonerGamesByPuuid("abc"))


# ---------------------------------------------------------------------------
# 契约: getRankedStatsByPuuid -> dict | raise SummonerRankInfoNotFound
# ---------------------------------------------------------------------------

class TestGetRankedStatsByPuuid:
    def test_returns_ranked_dict(self, mock_lcu):
        data = {"queueMap": {"RANKED_SOLO_5x5": {"tier": "Gold"}}}
        with _patch_get(_resp(json_data=data)):
            result = _run(mock_lcu.getRankedStatsByPuuid("abc"))
        assert result == data

    def test_errorCode_raises(self, mock_lcu):
        # 契约: 响应含 errorCode -> SummonerRankInfoNotFound
        with _patch_get(_resp(json_data={"errorCode": "NOT_FOUND"})):
            with pytest.raises(SummonerRankInfoNotFound):
                _run(mock_lcu.getRankedStatsByPuuid("abc"))


# ---------------------------------------------------------------------------
# 契约: getCurrentSummoner -> dict (含 summonerId) | None (LCU 未就绪)
# ---------------------------------------------------------------------------

class TestGetCurrentSummoner:
    def test_returns_summoner_with_id(self, mock_lcu):
        data = {"summonerId": 42, "displayName": "Me"}
        with _patch_get(_resp(json_data=data)):
            result = _run(mock_lcu.getCurrentSummoner())
        assert result == data

    def test_missing_summonerId_returns_none(self, mock_lcu):
        # 契约: 响应无 summonerId (LCU 未就绪) -> 方法内 raise ReferenceError
        # @retry 统一拦截 ReferenceError, 发射 lcuNotConnected 信号, 返回 None
        with _patch_get(_resp(json_data={})):
            result = _run(mock_lcu.getCurrentSummoner())
        assert result is None


# ---------------------------------------------------------------------------
# 契约: getGameStatus -> str (去掉首尾引号)
# ---------------------------------------------------------------------------

class TestGetGameStatus:
    def test_strips_surrounding_quotes(self, mock_lcu):
        # LCU gameflow-phase 返回带引号的字符串如 '"Lobby"'
        # 契约: 去掉首尾字符后返回 "Lobby"
        with _patch_get(_resp(text_data='"Lobby"')):
            result = _run(mock_lcu.getGameStatus())
        assert result == "Lobby"

    def test_inprogress(self, mock_lcu):
        with _patch_get(_resp(text_data='"InProgress"')):
            result = _run(mock_lcu.getGameStatus())
        assert result == "InProgress"


# ---------------------------------------------------------------------------
# 契约: getMapSide -> str (取 mapSide, 缺失返回 "")
# ---------------------------------------------------------------------------

class TestGetMapSide:
    def test_returns_mapside_field(self, mock_lcu):
        with _patch_get(_resp(json_data={"mapSide": "blue"})):
            result = _run(mock_lcu.getMapSide())
        assert result == "blue"

    def test_missing_mapside_returns_empty(self, mock_lcu):
        with _patch_get(_resp(json_data={})):
            result = _run(mock_lcu.getMapSide())
        assert result == ""


# ---------------------------------------------------------------------------
# 契约: getLobbyStatus -> Optional[dict] (异常吞掉返回 None)
# ---------------------------------------------------------------------------

class TestGetLobbyStatus:
    def test_returns_lobby_dict(self, mock_lcu):
        data = {"gameConfig": {"queueId": 420}}
        with _patch_get(_resp(json_data=data)):
            result = _run(mock_lcu.getLobbyStatus())
        assert result == data

    def test_client_error_returns_none(self, mock_lcu):
        # 契约: 任何 aiohttp/解析异常 -> 返回 None (不抛出)
        with patch.object(
                connector, '_LolClientConnector__get',
                new=AsyncMock(side_effect=aiohttp.ClientError("boom"))):
            result = _run(mock_lcu.getLobbyStatus())
        assert result is None


# ---------------------------------------------------------------------------
# 契约: getMatchmakingStatus -> Optional[dict]
#   优先 teambuilder 端点 (200) -> 回退 /lol-matchmaking/v1/search (200) -> None
# ---------------------------------------------------------------------------

class TestGetMatchmakingStatus:
    def test_teambuilder_200_returns_dict(self, mock_lcu):
        data = {"searchState": "Searching", "isCurrentlyInQueue": True}
        with _patch_get(_resp(json_data=data, status=200)):
            result = _run(mock_lcu.getMatchmakingStatus())
        assert result == data

    def test_both_endpoints_fail_returns_none(self, mock_lcu):
        # 两个端点都抛异常 -> None
        with patch.object(
                connector, '_LolClientConnector__get',
                new=AsyncMock(side_effect=aiohttp.ClientError("boom"))):
            result = _run(mock_lcu.getMatchmakingStatus())
        assert result is None


# ---------------------------------------------------------------------------
# 契约: isLobbyReadyToSearch -> bool
# ---------------------------------------------------------------------------

class TestIsLobbyReadyToSearch:
    def test_no_lobby_returns_false(self, mock_lcu):
        with patch.object(
                connector, 'getLobbyStatus', new=AsyncMock(return_value=None)):
            result = _run(mock_lcu.isLobbyReadyToSearch())
        assert result is False

    def test_canStartActivity_true(self, mock_lcu):
        with patch.object(
                connector, 'getLobbyStatus',
                new=AsyncMock(return_value={"canStartActivity": True})):
            result = _run(mock_lcu.isLobbyReadyToSearch())
        assert result is True

    def test_canStartActivity_false(self, mock_lcu):
        with patch.object(
                connector, 'getLobbyStatus',
                new=AsyncMock(return_value={"canStartActivity": False})):
            result = _run(mock_lcu.isLobbyReadyToSearch())
        assert result is False

    def test_fallback_to_queue_id(self, mock_lcu):
        # canStartActivity 为 None 时, 有 queueId 即视为可搜索
        with patch.object(
                connector, 'getLobbyStatus',
                new=AsyncMock(return_value={
                    "canStartActivity": None,
                    "gameConfig": {"queueId": 420},
                })):
            result = _run(mock_lcu.isLobbyReadyToSearch())
        assert result is True

    def test_no_queue_id_returns_false(self, mock_lcu):
        with patch.object(
                connector, 'getLobbyStatus',
                new=AsyncMock(return_value={
                    "canStartActivity": None,
                    "gameConfig": {},
                })):
            result = _run(mock_lcu.isLobbyReadyToSearch())
        assert result is False


# ---------------------------------------------------------------------------
# 契约: isInTencent -> bool (镜像 self.inTencent)
# ---------------------------------------------------------------------------

class TestIsInTencent:
    def test_true(self, mock_lcu):
        connector.inTencent = True
        assert connector.isInTencent() is True

    def test_false(self, mock_lcu):
        connector.inTencent = False
        assert connector.isInTencent() is False


# ---------------------------------------------------------------------------
# 契约: getLoginSummonerByPid -> dict | {} (异常吞掉)
#   不经过 @retry, 自建 aiohttp.ClientSession 直连目标 pid 的 LCU
# ---------------------------------------------------------------------------

class TestGetLoginSummonerByPid:
    def test_returns_summoner_dict(self, mock_lcu):
        summoner = {"summonerId": 7, "displayName": "P1"}
        mock_resp = MagicMock()
        mock_resp.json = AsyncMock(return_value=summoner)
        mock_sess = MagicMock()
        mock_sess.get = MagicMock(return_value=_AsyncCM(mock_resp))

        with patch('app.lol.connector.aiohttp.ClientSession',
                   return_value=_AsyncCM(mock_sess)), \
             patch('app.lol.connector.getPortTokenServerByPid',
                   return_value=(12345, "tok", "hn1")):
            result = _run(connector.getLoginSummonerByPid(9999))
        assert result == summoner

    def test_client_error_returns_empty_dict(self, mock_lcu):
        # 契约: aiohttp.ClientError / TimeoutError / ValueError -> 返回 {}
        mock_sess = MagicMock()
        mock_sess.get = MagicMock(
            return_value=_ErrorAsyncCM(aiohttp.ClientError("refused")))

        with patch('app.lol.connector.aiohttp.ClientSession',
                   return_value=_AsyncCM(mock_sess)), \
             patch('app.lol.connector.getPortTokenServerByPid',
                   return_value=(12345, "tok", "hn1")):
            result = _run(connector.getLoginSummonerByPid(9999))
        assert result == {}

    def test_timeout_returns_empty_dict(self, mock_lcu):
        mock_sess = MagicMock()
        mock_sess.get = MagicMock(
            return_value=_ErrorAsyncCM(asyncio.TimeoutError()))

        with patch('app.lol.connector.aiohttp.ClientSession',
                   return_value=_AsyncCM(mock_sess)), \
             patch('app.lol.connector.getPortTokenServerByPid',
                   return_value=(12345, "tok", "hn1")):
            result = _run(connector.getLoginSummonerByPid(9999))
        assert result == {}


# ---------------------------------------------------------------------------
# 契约: startMatchmaking -> bool
#   teambuilder 端点 200/204 -> True; 都失败时查状态确认
# ---------------------------------------------------------------------------

class TestStartMatchmaking:
    def test_teambuilder_200_returns_true(self, mock_lcu):
        with _patch_post(_resp(status=200)):
            result = _run(mock_lcu.startMatchmaking())
        assert result is True

    def test_teambuilder_204_returns_true(self, mock_lcu):
        with _patch_post(_resp(status=204)):
            result = _run(mock_lcu.startMatchmaking())
        assert result is True

    def test_all_fail_and_not_in_queue_returns_false(self, mock_lcu):
        # 两个 POST 端点都返回 500, 且 matchmaking 状态查询返回 None
        with _patch_post(_resp(status=500)), \
             patch.object(connector, 'getMatchmakingStatus',
                          new=AsyncMock(return_value=None)):
            result = _run(mock_lcu.startMatchmaking())
        assert result is False

    def test_post_fails_but_already_in_queue_returns_true(self, mock_lcu):
        # 契约: 即使 POST 返回非 200, 若 matchmaking 状态显示已在队列, 视为成功
        with _patch_post(_resp(status=500)), \
             patch.object(connector, 'getMatchmakingStatus',
                          new=AsyncMock(return_value={
                              "isCurrentlyInQueue": True})):
            result = _run(mock_lcu.startMatchmaking())
        assert result is True
