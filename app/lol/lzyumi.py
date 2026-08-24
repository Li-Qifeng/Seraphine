"""lzyumi 第三方数据源异步客户端（LOL 隐藏分 / 近十场查询）。

接口契约见 /root/ctf-lol/REPLICATION.md：
Base: https://a.2025lol.top/lzyumi/lol/info（GET，无 Cookie/UA 校验，无尾斜杠）
每个请求追加 &lzyumiSign={md5}&signStr={...}，时间取当前时刻。
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

import aiohttp

from app.lol.tools_lzyumi import (
    decode_response,
    lzyumi_sign,
    parse_rank_elo,
    parse_recent_games,
    sign_str,
)

TAG = "Lzyumi"

BASE_URL = "https://a.2025lol.top/lzyumi/lol/info"
TIMEOUT_SECONDS = 10
ELO_TTL = 10 * 60
GAMES_TTL = 2 * 60


class LzyumiError(Exception):
    """lzyumi 业务错误（响应无法解析等）。"""


class LzyumiUnavailable(Exception):
    """网络失败 / 超时，上层应降级。"""


def _encode_openid(open_id: str) -> str:
    """openId 加密串：encodeURIComponent 后 '+' 替换 '%2B'。"""
    return quote(open_id, safe="").replace("+", "%2B")


def _encode_nickname(nickname: str) -> str:
    """nickname 中 '#' RiotTag 替换为 '*~*~*' 后 URL 编码。"""
    return quote(nickname.replace("#", "*~*~*"), safe="*")


class Lzyumi:
    def __init__(self, base_url: str = BASE_URL, timeout: int = TIMEOUT_SECONDS):
        self.base_url = base_url
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
        # key -> (expires_at, payload)
        self._cache: Dict[Tuple[Any, ...], Tuple[float, Any]] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    @staticmethod
    def _signed_params(params: Dict[str, str]) -> Dict[str, str]:
        now = datetime.now()
        params["lzyumiSign"] = lzyumi_sign(now)
        params["signStr"] = sign_str(now)
        return params

    async def _fetch(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        session = await self._get_session()
        try:
            async with session.get(
                url, params=self._signed_params(params),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                body = await resp.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise LzyumiUnavailable(f"[{TAG}] request failed: {e}") from e
        try:
            return decode_response(body)
        except ValueError as e:
            raise LzyumiError(str(e)) from e

    async def getRankEloInfo(self, open_id: str, area_id: int = 16) -> Optional[Dict[str, Optional[int]]]:
        """隐藏分：{solo, flex, aram}；无数据返回 None。"""
        key = ("elo", open_id, area_id)
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        raw = await self._fetch(
            "/getRankEloInfo",
            {"openId": _encode_openid(open_id), "areaId": str(area_id), "filter": "1"},
        )
        result = parse_rank_elo(raw)
        if result is None:
            return None
        self._cache_put(key, result, ELO_TTL)
        return result

    async def searchPlayer(self, nickname: str, area_id: int, count: int = 10) -> Dict[str, Any]:
        """近十场主查询：返回原始 dict（battleInfo + data[]）。"""
        key = ("games", nickname, area_id, count)
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        raw = await self._fetch(
            "/",
            {
                "nickname": _encode_nickname(nickname),
                "allCount": str(count),
                "areaId": str(area_id),
                "seleMe": "1",
                "filter": "1",
                "openId": "",
            },
        )
        if not isinstance(raw.get("data"), list) or "battleInfo" not in raw:
            raise LzyumiError(f"[{TAG}] unexpected search response shape")
        games = parse_recent_games(raw)
        payload = {"battleInfo": raw["battleInfo"], "games": games}
        self._cache_put(key, payload, GAMES_TTL)
        return payload

    def _cache_get(self, key: Tuple[Any, ...]) -> Any:
        item = self._cache.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if time.monotonic() >= expires_at:
            del self._cache[key]
            return None
        return payload

    def _cache_put(self, key: Tuple[Any, ...], payload: Any, ttl: int):
        self._cache[key] = (time.monotonic() + ttl, payload)


lzyumi = Lzyumi()
