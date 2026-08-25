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

from app.common.logger import logger
from app.lol.tools_lzyumi import (
    decode_response,
    lzyumi_sign,
    parse_rank_elo,
    parse_recent_games,
    sign_str,
)

TAG = "Lzyumi"

BASE_URL = "https://a.2025lol.top/lzyumi/lol/info"

# lzyumi areaId -> 大区中文名 (searchPlayer 必传 areaName, 否则后端 500)
AREA_NAMES = {
    1: "艾欧尼亚", 2: "德玛西亚", 3: "班德尔城", 4: "诺克萨斯",
    6: "祖安", 9: "弗雷尔卓德", 11: "皮尔特沃夫", 12: "战争学院",
    13: "巨神峰", 14: "黑色玫瑰", 15: "暗影岛", 16: "恕瑞玛",
    17: "钢铁烈阳", 18: "水晶之痕", 19: "裁决之地", 20: "扭曲丛林",
    21: "教育网", 22: "卡拉曼达", 23: "雷瑟守备", 24: "征服之海",
    25: "峡谷之巅", 26: "男爵领域", 30: "艾欧尼亚", 31: "峡谷之巅",
}

TIMEOUT_SECONDS = 25
FETCH_RETRIES = 1
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
        last_exc: Exception = LzyumiUnavailable(f"[{TAG}] not attempted")
        for attempt in range(1 + FETCH_RETRIES):
            try:
                async with session.get(
                    url, params=self._signed_params(params),
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    proxy=None,
                ) as resp:
                    body = await resp.read()
                return decode_response(body)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exc = e
                logger.warning(
                    f"lzyumi fetch {path} attempt {attempt + 1} failed: "
                    f"{type(e).__name__}: {e}", TAG)
            except ValueError as e:
                raise LzyumiError(str(e)) from e
        raise LzyumiUnavailable(f"[{TAG}] request failed: {last_exc}") from last_exc

    async def getRankEloInfo(self, open_id: str, area_id: int = 16) -> Optional[Dict[str, Optional[int]]]:
        """隐藏分：{solo, flex, aram}；无数据返回 None。"""
        key = ("elo", open_id, area_id)
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        raw = await self._fetch(
            "/getRankEloInfo",
            # openId 传原始串, aiohttp params 会正确编码;
            # 预编码后再传会被二次转义 (%2B -> %252B) 导致后端解密 500
            {"openId": open_id, "areaId": str(area_id), "filter": "2"},
        )
        result = parse_rank_elo(raw.get("data") or raw)
        if result is None:
            return None
        self._cache_put(key, result, ELO_TTL)
        return result

    async def searchPlayer(self, nickname: str, area_id: int, count: int = 10,
                           area_name: str = "") -> Dict[str, Any]:
        """近十场主查询：返回原始 dict（battleInfo + data[]）。

        area_name 必填 (大区中文名): 缺失时后端 500 NullPointerException。
        """
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
                "areaName": area_name or AREA_NAMES.get(area_id, "未知"),
                "seleMe": "1",
                "filter": "1",
                "openId": "",
                "modelId": "1",
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
