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

from app.lol.connector import connector, _parse_retry_after
from app.common.signals import signalBus
from app.lol.exceptions import (
    RateLimited,
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
    - _gamesFastCache 清空: 避免测试间缓存污染
    """
    connector.lcuSess = MagicMock()
    connector.semaphore = None
    connector._gamesFastCache = None
    yield connector
    connector.lcuSess = None
    connector.semaphore = None
    connector._gamesFastCache = None


def _patch_get(ret_val):
    """patch connector._LolClientConnector__get 为返回 ret_val 的 AsyncMock."""
    return patch.object(
        connector, '_LolClientConnector__get',
        new=AsyncMock(return_value=ret_val))


def _patch_post(ret_val):
    return patch.object(
        connector, '_LolClientConnector__post',
        new=AsyncMock(return_value=ret_val))


def _patch_delete(ret_val):
    return patch.object(
        connector, '_LolClientConnector__delete',
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


# ---------------------------------------------------------------------------
# 契约: 429 RateLimited — __get 检测 429 并抛出 RateLimited, @retry 重试后最终向上抛
# ---------------------------------------------------------------------------

class TestParseRetryAfter:
    """契约: Retry-After 解析 — 整数/浮点/缺失/非法值."""

    def test_integer_string(self):
        assert _parse_retry_after("5") == 5

    def test_float_string(self):
        # LCU 正常返回整数秒, 但浮点值 (如网关返回 "0.5") 需按原值解析
        assert _parse_retry_after("0.1") == 0.1
        assert _parse_retry_after("2.5") == 2.5

    def test_missing_or_empty_falls_back_to_5(self):
        assert _parse_retry_after(None) == 5
        assert _parse_retry_after("") == 5

    def test_invalid_value_falls_back_to_5(self):
        assert _parse_retry_after("soon") == 5

    def test_clamped_to_bounds(self):
        assert _parse_retry_after("120") == 60
        assert _parse_retry_after("0") == 0


class Test429RateLimited:
    def test_get_429_raises_ratelimited_after_retry_exhausted(self, mock_lcu):
        """__get 返回 429 时抛出 RateLimited, @retry 用完重试次数后向上抛."""
        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_resp.headers = {'Retry-After': '0.1'}
        connector.lcuSess.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(RateLimited):
            _run(mock_lcu.getSummonerByPuuid("abc"))

    def test_get_429_ratelimited_contained_in_retry(self, mock_lcu):
        """@retry 捕获 RateLimited 后 sleep 重试, 最终成功时不抛异常."""
        attempt_count = 0
        mock_resp_429 = MagicMock()
        mock_resp_429.status = 429
        mock_resp_429.headers = {'Retry-After': '0.05'}

        mock_resp_200 = MagicMock()
        mock_resp_200.status = 200
        mock_resp_200.json = AsyncMock(return_value={"puuid": "abc", "summonerId": 1})

        async def side_effect(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            return mock_resp_429 if attempt_count < 3 else mock_resp_200

        connector.lcuSess.get = AsyncMock(side_effect=side_effect)

        result = _run(mock_lcu.getSummonerByPuuid("abc"))
        assert result == {"puuid": "abc", "summonerId": 1}

    def test_get_summoner_games_bubbles_429_to_outer_retry(self, mock_lcu):
        """getSummonerGamesByPuuid 内层 except (ClientError, ...) 不捕获
        RateLimited, 429 自然冒泡到 @retry 外层, 避免嵌套爆炸."""
        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_resp.headers = {'Retry-After': '0.1'}
        connector.lcuSess.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(RateLimited):
            _run(mock_lcu.getSummonerGamesByPuuid("abc", 0, 4))


# ---------------------------------------------------------------------------
# 契约: LCU 冷启动 stale match-history -> 返回部分数据 + 后台恢复
# ---------------------------------------------------------------------------

def _games_resp(count, gameCount=None):
    """构造 LCU match-history 容器响应: {"games": {"gameCount": N, "games": [...]}}"""
    if gameCount is None:
        gameCount = count
    return {"games": {
        "gameCount": gameCount,
        "games": [{"gameId": i} for i in range(count)],
    }}


class TestStaleMatchHistoryRecovery:
    def _cleanup(self):
        for task in list(connector._staleRecoveryTasks.values()):
            task.cancel()
        connector._staleRecoveryTasks.clear()
        connector._gamesFastCache = None
        connector.__dict__.pop('_STALE_RECOVERY_INTERVAL', None)

    def _fast_sleep(self):
        """把 connector 模块里的 asyncio.sleep 置空, 加速 stale 重试与恢复探测."""
        return patch('app.lol.connector.asyncio.sleep',
                     new=AsyncMock(return_value=None))

    def test_stale_partial_returns_data_and_schedules_recovery(self, mock_lcu):
        """冷启动场景: 请求 20 条只返回 2 条 (gameCount 也是 2).

        契约: 不阻塞 UI -- 单次请求后立即返回部分数据, 同时调度后台恢复任务.
        (不直接检查 _staleRecoveryTasks: asyncio.run 退出时会取消后台任务
        并将其从注册表移除, 这里用 spy 验证调度动作本身)"""
        schedule_mock = MagicMock(return_value=None)
        with patch.object(
                connector, '_LolClientConnector__scheduleStaleRecovery',
                new=schedule_mock), \
                _patch_get(_resp(json_data=_games_resp(2))):
            result = _run(mock_lcu.getSummonerGamesByPuuid("abc", 0, 19))

        assert result["gameCount"] == 2
        assert len(result["games"]) == 2
        schedule_mock.assert_called_once_with("abc", 0, 19)
        self._cleanup()

    def test_full_result_does_not_schedule_recovery(self, mock_lcu):
        """返回足量数据时不调度后台恢复."""
        with _patch_get(_resp(json_data=_games_resp(20))):
            result = _run(mock_lcu.getSummonerGamesByPuuid("abc", 0, 19))

        assert len(result["games"]) == 20
        assert "abc" not in connector._staleRecoveryTasks
        self._cleanup()

    def test_recovery_emits_signal_and_updates_fast_cache(self, mock_lcu):
        """后台探测拿到足量数据 -> 刷新 fast cache + 广播 matchHistoryRecovered.

        conftest 把 PyQt5 stub 成 MagicMock, 真实信号无法收发,
        这里直接 mock 信号属性验证 emit 调用契约."""
        sig_mock = MagicMock()
        get_mock = AsyncMock(side_effect=[
            _resp(json_data=_games_resp(2)),    # 首次请求 (stale)
            _resp(json_data=_games_resp(20)),  # 恢复探测
        ])
        with patch.object(connector, '_LolClientConnector__get', new=get_mock), \
                patch.object(signalBus, 'matchHistoryRecovered', new=sig_mock), \
                self._fast_sleep():
            async def scenario():
                result = await connector.getSummonerGamesByPuuid(
                    "abc", 0, 19)
                task = connector._staleRecoveryTasks.get("abc")
                assert task is not None
                await task  # 等待恢复循环完成
                return result

            result = _run(scenario())

        assert len(result["games"]) == 2  # 首次仍返回部分数据
        sig_mock.emit.assert_called_once_with("abc")
        # fast cache 已被恢复后的完整数据刷新
        c_puuid, c_beg, c_end, c_data, _ = connector._gamesFastCache
        assert c_puuid == "abc"
        assert (c_beg, c_end) == (0, 19)
        assert len(c_data["games"]) == 20

    def test_recovery_stops_for_genuinely_small_accounts(self, mock_lcu):
        """探测发现 gameCount 与条数一致 (账号真的只有几局) -> 停止且不广播."""
        sig_mock = MagicMock()
        get_mock = AsyncMock(side_effect=[
            _resp(json_data=_games_resp(2)),  # 首次请求 (stale)
            _resp(json_data=_games_resp(3)),  # 探测: 3 局且 gameCount=3
        ])
        with patch.object(connector, '_LolClientConnector__get', new=get_mock), \
                patch.object(signalBus, 'matchHistoryRecovered', new=sig_mock), \
                self._fast_sleep():
            async def scenario():
                await connector.getSummonerGamesByPuuid("abc", 0, 19)
                task = connector._staleRecoveryTasks.get("abc")
                assert task is not None
                await task

            _run(scenario())

        sig_mock.emit.assert_not_called()

    def test_recovery_stops_when_lcu_disconnected(self, mock_lcu):
        """探测期间 LCU 断开 (ReferenceError) -> 静默放弃恢复."""
        sig_mock = MagicMock()
        get_mock = AsyncMock(side_effect=[
            _resp(json_data=_games_resp(2)),    # 首次请求 (stale)
            ReferenceError("lcu gone"),        # 探测: LCU 已断开
            _resp(json_data=_games_resp(20)),  # 不应被请求
        ])
        with patch.object(connector, '_LolClientConnector__get', new=get_mock), \
                patch.object(signalBus, 'matchHistoryRecovered', new=sig_mock), \
                self._fast_sleep():
            async def scenario():
                await connector.getSummonerGamesByPuuid("abc", 0, 19)
                task = connector._staleRecoveryTasks.get("abc")
                assert task is not None
                await task

            _run(scenario())

        sig_mock.emit.assert_not_called()
        assert get_mock.call_count == 2  # 断开后不再探测


# ---------------------------------------------------------------------------
# 契约: sendChampSelectMessage -> bool
#   先 GET /lol-chat/v1/conversations 找 type==championSelect 的真实对话 id,
#   再 POST 到该对话. 找不到对话 / 非 2xx 时返回 False.
# ---------------------------------------------------------------------------

class TestSendChampSelectMessage:
    def test_posts_to_real_championselect_conversation(self, mock_lcu):
        """存在 championSelect 对话时, 用其真实 id 发消息."""
        convs = [
            {"id": "111", "type": "group", "name": "x"},
            {"id": "champ-real", "type": "championSelect", "name": "y"},
        ]
        conv_resp = _resp(json_data=convs, status=200)
        post_resp = _resp(status=201)

        with _patch_get(conv_resp), _patch_post(post_resp) as mock_post:
            result = _run(mock_lcu.sendChampSelectMessage("hello"))

        assert result is True
        mock_post.assert_awaited_once_with(
            "/lol-chat/v1/conversations/champ-real/messages",
            data={"type": "chat", "body": "hello"})

    def test_no_championselect_conversation_returns_false(self, mock_lcu):
        """没有 championSelect 对话 (不在选人阶段) 时不发送并返回 False."""
        convs = [{"id": "111", "type": "group", "name": "x"}]
        conv_resp = _resp(json_data=convs, status=200)

        with _patch_get(conv_resp), _patch_post(_resp(status=200)) as mock_post:
            result = _run(mock_lcu.sendChampSelectMessage("hello"))

        assert result is False
        mock_post.assert_not_awaited()

    def test_post_non_2xx_returns_false(self, mock_lcu):
        """POST 返回非 200/201 时返回 False (不抛异常)."""
        convs = [{"id": "cid", "type": "championSelect", "name": "y"}]
        conv_resp = _resp(json_data=convs, status=200)
        post_resp = _resp(status=404, text_data="not found")

        with _patch_get(conv_resp), _patch_post(post_resp):
            result = _run(mock_lcu.sendChampSelectMessage("hello"))

        assert result is False

    def test_conversations_get_error_returns_false(self, mock_lcu):
        """GET conversations 非 200 时返回 False."""
        conv_resp = _resp(json_data=[], status=503)

        with _patch_get(conv_resp), _patch_post(_resp(status=200)) as mock_post:
            result = _run(mock_lcu.sendChampSelectMessage("hello"))

        assert result is False
        mock_post.assert_not_awaited()


# ---------------------------------------------------------------------------
# 契约: dodge -> bool
#   逐字移植 Sona dodgeChampSelect: 仅 DELETE /lol-lobby/v2/lobby;
#   DELETE 404 视为已不在房间的幂等成功. 其余异常返回 False.
# ---------------------------------------------------------------------------

class TestDodge:
    def test_delete_ok_returns_true(self, mock_lcu):
        """DELETE 房间成功 (200/204) -> True, 不再追加任何端点."""
        delete_resp = _resp(status=204)
        delete_resp.ok = True

        with _patch_delete(delete_resp), \
                _patch_post(_resp(status=204)) as mock_post:
            result = _run(mock_lcu.dodge())

        assert result is True
        mock_post.assert_not_awaited()

    def test_delete_404_is_idempotent_success(self, mock_lcu):
        """DELETE 返回 404 (已不在房间) 视为成功.

        客户端正常返回 response (不抛 ClientResponseError), 404 由
        dodge() 直接判幂等成功.
        """
        delete_resp = _resp(status=404)
        delete_resp.ok = False

        with _patch_delete(delete_resp) as mock_del:
            result = _run(mock_lcu.dodge())

        assert result is True
        mock_del.assert_awaited_once_with("/lol-lobby/v2/lobby")

    def test_delete_fails_returns_false(self, mock_lcu):
        """DELETE 返回 500 等其他错误时返回 False."""
        delete_resp = _resp(status=500)
        delete_resp.ok = False

        with _patch_delete(delete_resp):
            result = _run(mock_lcu.dodge())

        assert result is False
