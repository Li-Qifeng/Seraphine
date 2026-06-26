"""
League of Legends Live Client Data API 客户端。

与 LCU API 不同, Live Client API 运行在游戏客户端内 (端口 2999),
无需鉴权, 仅在游戏进行中可用。用于获取实时装备、KDA、海克斯强化等数据。

官方文档: https://developer.riotgames.com/docs/lol#game-client-data_live-client-data-api
"""

import asyncio
from typing import Optional

import aiohttp

from app.common.logger import logger

TAG = "LiveClient"

BASE_URL = "https://127.0.0.1:2999"


class LiveClient:
    """Live Client Data API 客户端, 仅在游戏进行中可用"""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _getSession(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(BASE_URL)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get(self, path: str):
        """发起 GET 请求, 返回 JSON。游戏未进行时返回 None"""
        s = await self._getSession()
        timeout = aiohttp.ClientTimeout(total=3)
        try:
            async with s.get(path, ssl=False, proxy=None, timeout=timeout) as res:
                if res.status != 200:
                    return None
                return await res.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            # 游戏未运行时连接会失败, 属正常情况, 不打 error 日志
            return None
        except Exception as e:
            logger.warning(f"Live Client API {path} failed: {e}", TAG)
            return None

    async def getGamePhase(self) -> Optional[str]:
        """获取当前游戏阶段: None/ChampSelect/InProgress/Ended"""
        data = await self._get("/liveclientdata/gamephase")
        return data if isinstance(data, str) else None

    async def getAllGameData(self) -> Optional[dict]:
        """
        获取全量游戏数据, 包含所有玩家的装备、KDA、符文等。
        海克斯强化字段也可能在此响应中 (需实测确认)。
        """
        return await self._get("/liveclientdata/allgamedata")

    async def getPlayerItems(self) -> Optional[dict]:
        """获取当前活跃玩家的装备、召唤师技能、符文"""
        return await self._get("/liveclientdata/playeritems")

    async def getPlayerList(self) -> Optional[list]:
        """获取所有玩家的基本信息 (含每个玩家的 items 数组)"""
        data = await self._get("/liveclientdata/playerlist")
        return data if isinstance(data, list) else None

    async def getActivePlayer(self) -> Optional[dict]:
        """获取当前活跃玩家的详细信息"""
        return await self._get("/liveclientdata/activeplayer")

    async def getActivePlayerName(self) -> Optional[str]:
        """获取当前活跃玩家的名称"""
        data = await self._get("/liveclientdata/activeplayername")
        return data if isinstance(data, str) else None

    async def isAvailable(self) -> bool:
        """检查 Live Client API 是否可用 (游戏是否在进行中)"""
        phase = await self.getGamePhase()
        return phase is not None


# 全局单例
liveClient = LiveClient()
