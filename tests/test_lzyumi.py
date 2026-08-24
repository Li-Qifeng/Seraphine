"""lzyumi 数据源测试：签名黄金值 / 解码 / 解析 / 客户端 mock。"""

import asyncio
import base64
import hashlib
import json
from datetime import datetime

import pytest

from app.lol.lzyumi import Lzyumi, LzyumiUnavailable, _encode_nickname, _encode_openid
from app.lol.tools_lzyumi import (
    decode_response,
    lzyumi_sign,
    parse_rank_elo,
    parse_recent_games,
    sign_seed,
    sign_str,
)

# ---------------------------------------------------------------- 签名黄金值


def test_sign_seed_golden():
    dt = datetime(2026, 8, 24, 20, 43, 5)
    assert sign_seed(dt) == "dld08o24u20d43o05dld"


def test_sign_golden():
    dt = datetime(2026, 8, 24, 20, 43, 5)
    seed = "dld08o24u20d43o05dld"
    assert lzyumi_sign(dt) == hashlib.md5(seed.encode()).hexdigest()


def test_sign_str_golden():
    # month=1 day=2 hour=3 minute=4 second=5 → 全一位数，len*3 均为 3
    dt = datetime(2026, 1, 2, 3, 4, 5)
    assert sign_str(dt) == "12345" + "33333"
    # 混合位数：month=12(2位), day=3(1位) → len*3 分别 6 和 3
    dt2 = datetime(2026, 12, 3, 4, 5, 6)
    assert sign_str(dt2) == "123456" + "63333"


def test_sign_matches_reference_formula():
    dt = datetime(2025, 11, 9, 7, 58, 30)

    def p(x):
        return f"{x:02d}"

    manual_md5 = hashlib.md5(
        f"dld{p(dt.month)}o{p(dt.day)}u{p(dt.hour)}d{p(dt.minute)}o{p(dt.second)}dld".encode()
    ).hexdigest()
    v = [dt.month, dt.day, dt.hour, dt.minute, dt.second]
    manual_signstr = "".join(map(str, v)) + "".join(str(len(str(x)) * 3) for x in v)
    assert lzyumi_sign(dt) == manual_md5
    assert sign_str(dt) == manual_signstr


# ---------------------------------------------------------------- 解码


def test_decode_plain_json():
    body = json.dumps({"a": 1}).encode()
    assert decode_response(body) == {"a": 1}


def test_decode_base64_json():
    raw = {"dataRankEloNum": "单双：1478"}
    body = base64.b64encode(json.dumps(raw).encode())
    assert decode_response(body) == raw


def test_decode_invalid_raises():
    with pytest.raises(ValueError):
        decode_response(b"not json at all")


# ---------------------------------------------------------------- parse_rank_elo


def test_parse_rank_elo_normal():
    elo = parse_rank_elo(
        {
            "dataRankEloNum": "单双：1478",
            "dataRankEloInfoB": "灵活：1610",
            "dataRankEloInfoA": "大乱斗：2351",
        }
    )
    assert elo == {"solo": 1478, "flex": 1610, "aram": 2351}


def test_parse_rank_elo_missing_fields():
    assert parse_rank_elo({}) is None
    assert parse_rank_elo({"dataRankEloNum": "单双：1478"}) == {
        "solo": 1478,
        "flex": None,
        "aram": None,
    }


def test_parse_rank_elo_empty_or_garbage():
    assert parse_rank_elo({"dataRankEloNum": ""}) is None
    assert parse_rank_elo({"dataRankEloNum": "单双：abc"}) is None
    assert parse_rank_elo(None) is None


# ---------------------------------------------------------------- parse_recent_games


def test_parse_recent_games_normal():
    raw = {
        "battleInfo": {},
        "data": [
            {"gameId": "g1", "championId": 22, "isWin": True, "wasMvp": False, "wasSvp": False},
            {"gameId": "g2", "championId": 412, "isWin": 0},
        ],
    }
    games = parse_recent_games(raw)
    assert len(games) == 2
    assert games[0] == {
        "gameId": "g1",
        "championId": 22,
        "isWin": True,
        "isMvp": False,
        "isSvp": False,
    }
    assert games[1]["isWin"] is False


def test_parse_recent_games_mvp_svp_variants():
    raw = {
        "data": [
            {"gameId": "m", "championId": 1, "isWin": True, "wasMvp": 1, "wasSvp": ""},
            {"gameId": "s", "championId": 1, "isWin": False, "wasMvp": None, "wasSvp": "true"},
        ]
    }
    games = parse_recent_games(raw)
    assert games[0]["isMvp"] is True and games[0]["isSvp"] is False
    assert games[1]["isMvp"] is False and games[1]["isSvp"] is True


def test_parse_recent_games_empty():
    assert parse_recent_games({}) == []
    assert parse_recent_games({"data": None}) == []


# ---------------------------------------------------------------- 编码辅助


def test_encode_nickname_riot_tag():
    assert _encode_nickname("玩家#EUW") == "%E7%8E%A9%E5%AE%B6*~*~*EUW"
    assert _encode_nickname("simple") == "simple"


def test_encode_openid_plus():
    assert _encode_openid("ab+cd==") == "ab%2Bcd%3D%3D"


# ---------------------------------------------------------------- 客户端 mock


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    async def read(self):
        return self._body


class FakeSession:
    """记录请求并返回预设响应；可注入异常模拟超时/网络失败。"""

    def __init__(self, body: bytes = b"", exc: Exception | None = None):
        self.body = body
        self.exc = exc
        self.requests = []

    def get(self, url, params=None, timeout=None):
        self.requests.append((url, dict(params or {})))
        if self.exc:
            raise self.exc

        class _Ctx:
            async def __aenter__(self_inner):
                return FakeResponse(self.body)

            async def __aexit__(self_inner, *args):
                return False

        return _Ctx()

    @property
    def closed(self):
        return False

    async def close(self):
        pass


@pytest.fixture
def elo_body():
    payload = {
        "dataRankEloNum": "单双：1478",
        "dataRankEloInfoB": "灵活：1610",
        "dataRankEloInfoA": "大乱斗：2351",
    }
    return base64.b64encode(json.dumps(payload).encode())


def test_get_rank_elo_success_and_cache(monkeypatch, elo_body):
    fake = FakeSession(elo_body)
    client = Lzyumi()

    async def run():
        async def fake_session():
            return fake
        monkeypatch.setattr(client, "_get_session", fake_session)
        r1 = await client.getRankEloInfo("encOpenId", 16)
        r2 = await client.getRankEloInfo("encOpenId", 16)
        await client.close()
        return r1, r2

    r1, r2 = asyncio.run(run())
    assert r1 == {"solo": 1478, "flex": 1610, "aram": 2351}
    assert r2 == r1
    assert len(fake.requests) == 1  # 缓存命中不重复请求
    params = fake.requests[0][1]
    assert params["openId"] == "encOpenId"
    assert params["areaId"] == "16"
    assert "lzyumiSign" in params and "signStr" in params


def test_search_player_success(monkeypatch):
    payload = {
        "battleInfo": {"nameInfoNew": "玩家", "openId": "x"},
        "data": [{"gameId": "g1", "championId": 22, "isWin": True}],
    }
    fake = FakeSession(json.dumps(payload).encode())
    client = Lzyumi()

    async def run():
        async def fake_session():
            return fake
        monkeypatch.setattr(client, "_get_session", fake_session)
        result = await client.searchPlayer("玩家#EUW", 16)
        await client.close()
        return result, fake.requests[0]

    result, (url, params) = asyncio.run(run())
    assert result["games"][0]["gameId"] == "g1"
    assert params["nickname"] == "%E7%8E%A9%E5%AE%B6*~*~*EUW"
    assert params["allCount"] == "10"


def test_timeout_degrades_to_unavailable(monkeypatch):
    import aiohttp

    fake = FakeSession(exc=aiohttp.ClientError("boom"))
    client = Lzyumi()

    async def run():
        async def fake_session():
            return fake
        monkeypatch.setattr(client, "_get_session", fake_session)
        with pytest.raises(LzyumiUnavailable):
            await client.getRankEloInfo("oid")
        with pytest.raises(LzyumiUnavailable):
            await client.searchPlayer("nick", 16)
        await client.close()

    asyncio.run(run())
