"""
海克斯强化实时数据采集层。

通过 Live Client API (端口 2999) 的 allgamedata 探测玩家已选强化和当前可选 offer。
字段结构尚未完全确认, 采用防御式解析 + 首次探测日志, 便于后续精化。
"""

import json
from typing import Optional

from app.common.logger import logger
from app.lol.live_client import liveClient

TAG = "AugmentLive"

# 探测日志只打印一次, 避免轮询时刷屏
_probe_logged = False


async def fetchCurrentAugments() -> Optional[dict]:
    """采集当前玩家的海克斯强化状态。

    返回:
        {'selected': [augId...], 'offer': [augId...], 'round': int} 或 None
        - selected: 已选强化 ID 列表
        - offer: 当前可选强化 ID 列表 (可能为空, 表示 Live Client 不暴露此信息)
        - round: 当前选择轮次 (基于已选数量推断, 0 表示首轮)

    返回 None 表示游戏未进行或 API 不可用。
    """
    global _probe_logged

    try:
        data = await liveClient.getAllGameData()
    except Exception as e:
        logger.warning(f"fetchCurrentAugments: getAllGameData failed: {e}", TAG)
        return None

    if not isinstance(data, dict):
        return None

    # 首次探测: 打印完整结构到 ERROR 日志, 便于精化解析逻辑
    if not _probe_logged:
        _probe_logged = True
        try:
            # 只打印顶层 keys 和 allPlayers/activePlayer 的结构, 避免日志过长
            top_keys = list(data.keys())
            logger.error(
                f"[AugmentLiveProbe] allgamedata top keys: {top_keys}", TAG)
            all_players = data.get('allPlayers')
            if isinstance(all_players, list) and all_players:
                p0 = all_players[0]
                if isinstance(p0, dict):
                    logger.error(
                        f"[AugmentLiveProbe] allPlayers[0] keys: "
                        f"{list(p0.keys())}", TAG)
                    # 检查 augment 相关字段
                    for k, v in p0.items():
                        if 'augment' in k.lower() or 'hex' in k.lower():
                            logger.error(
                                f"[AugmentLiveProbe] allPlayers[0]['{k}'] = "
                                f"{json.dumps(v, ensure_ascii=False)[:300]}",
                                TAG)
            active = data.get('activePlayer')
            if isinstance(active, dict):
                logger.error(
                    f"[AugmentLiveProbe] activePlayer keys: "
                    f"{list(active.keys())}", TAG)
                for k, v in active.items():
                    if 'augment' in k.lower() or 'hex' in k.lower():
                        logger.error(
                            f"[AugmentLiveProbe] activePlayer['{k}'] = "
                            f"{json.dumps(v, ensure_ascii=False)[:300]}",
                            TAG)
            # 顶层 augment/hex 相关字段
            for k, v in data.items():
                if 'augment' in k.lower() or 'hex' in k.lower():
                    logger.error(
                        f"[AugmentLiveProbe] top['{k}'] = "
                        f"{json.dumps(v, ensure_ascii=False)[:300]}",
                        TAG)
        except Exception as e:
            logger.warning(f"[AugmentLiveProbe] log structure failed: {e}", TAG)

    # 解析活跃玩家
    active_name = data.get('activePlayerName')
    if not isinstance(active_name, str):
        return None

    all_players = data.get('allPlayers')
    if not isinstance(all_players, list):
        return None

    active_player = None
    for p in all_players:
        if not isinstance(p, dict):
            continue
        # 匹配活跃玩家 (summonerName 或 riotIdName)
        summoner = p.get('summonerName', '')
        riot = p.get('riotIdName', '')
        if active_name == summoner or active_name == riot:
            active_player = p
            break

    if not active_player:
        return None

    # 探测已选强化: 尝试多种可能的字段名
    selected = _extractAugmentIds(active_player)

    # 探测当前 offer: 几乎不可能从 Live Client 获取, 但仍尝试探测
    offer = _extractOfferIds(data, active_player)

    return {
        'selected': selected,
        'offer': offer,
        'round': len(selected),
    }


def _extractAugmentIds(player: dict) -> list:
    """从玩家数据中提取已选强化 ID 列表。

    尝试多种可能的字段名 (Arena 用 augments, Mayhem 待确认)。
    """
    for field in ('augments', 'playerAugments', 'hextechAugments'):
        raw = player.get(field)
        if raw is None:
            continue
        ids = _parseAugmentList(raw)
        if ids:
            return ids
    return []


def _extractOfferIds(gamedata: dict, player: dict) -> list:
    """探测当前可选强化 offer。

    Live Client API 通常不暴露"正在选择"的 UI 状态, 此函数尽力探测,
    失败返回空列表 (调用方据此降级为全量推荐)。
    """
    # 探测 activePlayer 下的选择状态字段
    active = gamedata.get('activePlayer')
    if isinstance(active, dict):
        for field in ('augmentSelection', 'availableAugments', 'augmentChoices',
                      'hextechChoices'):
            raw = active.get(field)
            if raw is not None:
                ids = _parseAugmentList(raw)
                if ids:
                    return ids
    # 探测顶层
    for field in ('augmentSelection', 'availableAugments'):
        raw = gamedata.get(field)
        if raw is not None:
            ids = _parseAugmentList(raw)
            if ids:
                return ids
    return []


def _parseAugmentList(raw) -> list:
    """将原始强化数据解析为 ID 列表。

    支持多种格式:
    - [int, int, ...]
    - [{'augmentId': int}, ...] / [{'id': int}, ...]
    - [{'augmentId': int, ...其他字段}, ...]
    """
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        aid = _coerceAugmentId(item)
        if aid is not None:
            result.append(aid)
    return result


def _coerceAugmentId(item):
    """从单个元素提取强化 ID."""
    if isinstance(item, int):
        return item
    if isinstance(item, dict):
        for k in ('augmentId', 'id', 'augmentID'):
            v = item.get(k)
            if isinstance(v, int) and v > 0:
                return v
    return None
