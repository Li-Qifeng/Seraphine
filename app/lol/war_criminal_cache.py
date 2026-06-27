"""战犯/躺赢狗诊断结果内存缓存.

进程内 dict, 按 gameId 存诊断结果. 重启清空 (持久化可在后续阶段加 JSON).
career_interface 显示战绩卡片时按 gameId 查缓存, 命中则渲染徽章.
"""
from typing import Optional, TypedDict


class CachedVerdict(TypedDict, total=False):
    gameId: int
    verdict: str
    label: str        # 中文标签 (战犯/躺赢狗/无明显异常/团队低迷)
    isCurrentSuspect: bool  # 当前召唤师是否是嫌疑者
    score: float
    evidence: list


_cache: dict = {}


def setVerdict(gameId: int, verdict: str, label: str,
               isCurrentSuspect: bool, score: float,
               evidence: list) -> None:
    """写入一局的诊断结果."""
    if gameId is None:
        return
    _cache[int(gameId)] = {
        'gameId': int(gameId),
        'verdict': verdict,
        'label': label,
        'isCurrentSuspect': isCurrentSuspect,
        'score': score,
        'evidence': evidence or [],
    }


def getVerdict(gameId) -> Optional[CachedVerdict]:
    """查询一局的诊断结果. 未命中返回 None."""
    if gameId is None:
        return None
    return _cache.get(int(gameId))


def clear():
    """清空缓存 (测试用)."""
    _cache.clear()
