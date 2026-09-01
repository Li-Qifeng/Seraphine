"""上等马赛前评价结果缓存 (内存, 带 TTL).

进程内 dict 按 puuid 存评级结果, 每条带时间戳;
TTL 600 秒过期, 过期后 get 返回 None (赛前画像变化较快, 不持久化).
模仿 war_criminal_cache.py 的接口风格.
"""
import copy
import time
from typing import Optional

from app.lol.horse_rating import HorseVerdict

TAG = "HorseRatingCache"

# 缓存存活时间 (秒): 一局比赛内有效即可
HORSE_CACHE_TTL_SECONDS = 600.0

_cache: dict = {}  # puuid -> {'verdict': HorseVerdict, 'ts': float}


def set_horse_verdict(puuid: Optional[str],
                      verdict: HorseVerdict) -> None:
    """写入一个玩家的上等马评级结果."""
    if not puuid or verdict is None:
        return
    _cache[str(puuid)] = {
        'verdict': verdict,
        'ts': time.time(),
    }


def get_horse_verdict(puuid: Optional[str]) -> Optional[HorseVerdict]:
    """查询一个玩家的评级结果. 未命中或已过期 (TTL 600s) 返回 None.

    返回深拷贝: 调用方 (orchestrator) 会往 verdict 上打 scheme 等
    批次字段, 引用直出会把这些字段永久写回缓存.
    """
    if not puuid:
        return None
    entry = _cache.get(str(puuid))
    if entry is None:
        return None
    if time.time() - entry['ts'] > HORSE_CACHE_TTL_SECONDS:
        del _cache[str(puuid)]
        return None
    return copy.deepcopy(entry['verdict'])


def clear():
    """清空缓存 (测试用)."""
    _cache.clear()
