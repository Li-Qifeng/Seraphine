"""战犯/躺赢狗诊断结果内存缓存.

进程内 dict, 按 gameId 存诊断结果. 重启清空 (持久化可在后续阶段加 JSON).
career_interface 显示战绩卡片时按 gameId 查缓存, 命中则渲染徽章.

每局缓存包含:
- 当前召唤师所在队的 verdict (向后兼容, 生涯卡片用)
- winner: 胜方队诊断 (对局详情标题栏显示躺赢狗)
- loser: 败方队诊断 (对局详情标题栏显示战犯)
"""
from typing import Optional, TypedDict


class CachedVerdict(TypedDict, total=False):
    gameId: int
    verdict: str
    label: str        # 中文标签 (战犯/躺赢狗/无明显异常/团队低迷)
    isCurrentSuspect: bool  # 当前召唤师是否是嫌疑者
    suspectPuuid: str       # 嫌疑者的 puuid (用于对局详情中标记具体玩家)
    score: float
    evidence: list


class TeamVerdict(TypedDict, total=False):
    """单个队伍的诊断结果 (胜方或败方)."""
    verdict: str
    label: str
    suspectPuuid: str
    score: float
    evidence: list
    teamId: str
    isWin: bool


_cache: dict = {}


def setVerdict(gameId: int, verdict: str = None, label: str = None,
               isCurrentSuspect: bool = False, score: float = 0.0,
               evidence: list = None, suspectPuuid: str = None,
               winner: dict = None, loser: dict = None) -> None:
    """写入一局的诊断结果.

    向后兼容: verdict/label/isCurrentSuspect 等字段表示当前召唤师所在队的诊断,
              供生涯卡片使用.

    新增字段:
        winner: 胜方队诊断 (TeamVerdict), 对局详情显示躺赢狗
        loser:  败方队诊断 (TeamVerdict), 对局详情显示战犯
    """
    if gameId is None:
        return
    _cache[int(gameId)] = {
        'gameId': int(gameId),
        'verdict': verdict,
        'label': label,
        'isCurrentSuspect': isCurrentSuspect,
        'suspectPuuid': suspectPuuid or '',
        'score': score,
        'evidence': evidence or [],
        'winner': winner,
        'loser': loser,
    }


def getVerdict(gameId) -> Optional[CachedVerdict]:
    """查询一局的诊断结果. 未命中返回 None."""
    if gameId is None:
        return None
    return _cache.get(int(gameId))


def clear():
    """清空缓存 (测试用)."""
    _cache.clear()
