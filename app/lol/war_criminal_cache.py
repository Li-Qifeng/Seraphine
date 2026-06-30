"""全队 5 档评级结果内存缓存.

进程内 dict, 按 gameId 存评级结果. 重启清空 (持久化可在后续阶段加 JSON).
career_interface 显示战绩卡片时按 gameId 查缓存, 命中则渲染徽章.

每局缓存包含:
- winnerRating: 胜方全队评级 (list[PlayerRating])
- loserRating:  败方全队评级 (list[PlayerRating])
"""
from typing import Optional, TypedDict


class PlayerRating(TypedDict, total=False):
    """单个玩家的 5 档评级 (全队评级列表中的一项)."""
    puuid: Optional[str]
    championId: int
    score: float       # z-score 综合贡献分
    grade: int         # 1-5 档位 (1=最高, 5=最低)
    label: str         # 标签文本 (已按风格/胜败方转换)
    isWin: bool
    isCurrent: bool    # 是否当前召唤师
    evidence: list


_cache: dict = {}


def setVerdict(gameId: int,
               winnerRating: list = None,
               loserRating: list = None) -> None:
    """写入一局的全队评级结果.

    Args:
        gameId: 对局 ID
        winnerRating: 胜方全队评级 (list[PlayerRating])
        loserRating:  败方全队评级 (list[PlayerRating])
    """
    if gameId is None:
        return
    _cache[int(gameId)] = {
        'gameId': int(gameId),
        'winnerRating': winnerRating,
        'loserRating': loserRating,
    }


def getVerdict(gameId) -> Optional[dict]:
    """查询一局的评级结果. 未命中返回 None.

    返回 dict 包含 winnerRating / loserRating 字段.
    """
    if gameId is None:
        return None
    return _cache.get(int(gameId))


def getTeamRating(gameId, isWinner: bool) -> Optional[list]:
    """查询一局某队伍的全队评级.

    Args:
        gameId: 对局 ID
        isWinner: True 查胜方评级, False 查败方评级

    Returns:
        list[PlayerRating] 或 None (未命中时).
    """
    if gameId is None:
        return None
    cached = _cache.get(int(gameId))
    if not cached:
        return None
    return cached.get('winnerRating' if isWinner else 'loserRating')


def clear():
    """清空缓存 (测试用)."""
    _cache.clear()
