# -*- coding: utf-8 -*-
"""上等马赛前评级 + BP 聊天窗播报编排层.

纯编排 (可测): 输入队友摘要 (LCU 可见段位), 输出逐行播报文案 (对齐 hh);
缓存细节收敛在内部, 单人失败降级 Unknown 不中断整体.
不依赖任何第三方数据源 — 数据全来自 LCU 对局接口的 rankInfo.
不负责发送 — 发送由 main_window 调 connector.sendChampSelectMessage 完成.
"""
import asyncio
import random
from typing import Optional

from app.common.config import cfg
from app.common.logger import logger
from app.lol.horse_rating import (
    GRADE_HORSE,
    HorseVerdict,
    PlayerHorseProfile,
    _horse_scheme,
    grade_from_score,
    rate_horse,
    resolve_horse_style,
)
from app.lol.horse_rating_cache import get_horse_verdict, set_horse_verdict

TAG = "HorseOrchestrator"

# 全队排名分档: 按分数从高到低排名, 第 0 名上等马 ... 第 4 名没有马 (同 sona 全队排名)

# 可见段位中文名 -> 段位序数 (宗师并入王者档)
TIER_NAME_TO_IDX = {
    "黑铁": 0, "黄铜": 1, "白银": 2, "黄金": 3, "铂金": 4,
    "翡翠": 5, "钻石": 6, "大师": 7, "宗师": 8, "王者": 8,
}

# 段内序数 (LCU 返回 "I"~"IV" 罗马数字)
DIVISION_NAME_TO_IDX = {
    "I": 0, "II": 1, "III": 2, "IV": 3,
    "Ⅰ": 0, "Ⅱ": 1, "Ⅲ": 2, "Ⅳ": 3,
}


def tierNameToIdx(name: Optional[str]) -> Optional[int]:
    """段位显示名 -> 序数; 无法识别返回 None."""
    if not name:
        return None
    return TIER_NAME_TO_IDX.get(str(name).strip())


def _queue_group(queue_id: Optional[int]) -> Optional[tuple]:
    """当前大厅模式 -> 历史对局过滤组; None 表示不过滤.

    排位合并单双排, 大乱斗合并经典+海克斯, 其余模式只取同 queueId.
    """
    if queue_id in (420, 440):
        return (420, 440)
    if queue_id in (450, 2400):
        return (450, 2400)
    return (queue_id,) if queue_id else None


def _uses_tier(queue_id: Optional[int]) -> bool:
    """大乱斗/海克斯大乱斗只看近期 KDA, 不参考段位; 其余模式 (排位/匹配) 参考段位."""
    return queue_id not in (450, 2400)


def _filter_games(s: dict, queue_ids: Optional[tuple]) -> list:
    """按模式组过滤 gamesInfo; 无过滤组时原样返回."""
    games = s.get("gamesInfo") or []
    if not queue_ids:
        return games
    return [g for g in games if g.get("queueId") in queue_ids]


def divisionNameToIdx(name: Optional[str]) -> Optional[int]:
    """段位 division 罗马数字 -> 序数 (I=0 ... IV=3); 无法识别返回 None."""
    if not name:
        return None
    return DIVISION_NAME_TO_IDX.get(str(name).strip().upper())


class SendGuard:
    """每局每通道最多发一次的守卫 (实例标志位语义, 可独立测试)."""

    def __init__(self):
        self._sent = False

    def try_acquire(self) -> bool:
        """首次获取返回 True 并置位; 之后返回 False."""
        if self._sent:
            return False
        self._sent = True
        return True

    def reset(self) -> None:
        """一局结束 (GameEnd/Lobby) 时重置."""
        self._sent = False


def _current_style() -> str:
    """读取用户配置的文案风格 ('horse' | 'formal')."""
    try:
        return str(cfg.get(cfg.horseRatingStyle))
    except Exception:
        return "horse"


def _extract_stats(s: dict, queue_ids: Optional[tuple] = None) -> tuple:
    """从召唤师摘要中提取 (winrate, kda); 缺数据返回 (None, None).

    兼容两种入参: ①已算好的 winrate/kda 字段; ②原始 summoner 大字典,
    含 gamesInfo (每局 win/remake/kills/deaths/assists) + kda 数组.
    queue_ids 非空时, 胜率/KDA 只按该模式组统计.
    """
    games = _filter_games(s, queue_ids)
    wr = s.get("winrate")
    kda = s.get("kda")
    if not games and wr is None and isinstance(kda, (list, tuple)) and len(kda) >= 3:
        k, d, a = kda[0], kda[1], kda[2]
        kda = (k + a) / d if d else (k + a)

    if games:
        completed = [g for g in games if not g.get("remake")]
        if completed:
            if wr is None:
                wins = sum(1 for g in completed if g.get("win"))
                wr = wins / len(completed)
            kda = _totals_kda(completed)

    return wr, kda


def _totals_kda(games: list) -> Optional[float]:
    """合计口径 (ΣK+ΣA)/ΣD; 无已完成对局返回 None."""
    k = d = a = 0
    for g in games:
        if g.get("remake"):
            continue
        k += g.get("kills") or 0
        d += g.get("deaths") or 0
        a += g.get("assists") or 0
    if k == 0 and d == 0 and a == 0:
        return None
    return (k + a) / d if d else (k + a)


def _cache_key(puuid: Optional[str], use_tier: bool) -> str:
    """大乱斗 KDA 模式与段位模式分开缓存, 避免跨模式误用旧值.

    use_tier=True 时用裸 puuid (兼容旧缓存/旧测试); KDA 模式用后缀区分.
    """
    return str(puuid) if use_tier else f"{puuid}:kda"


async def _rateSummoner(s: dict, queue_ids: Optional[tuple] = None,
                        use_tier: bool = True) -> HorseVerdict:
    """单个召唤师摘要 -> HorseVerdict. 缓存命中直接返回; 字段缺失返回 Unknown."""
    puuid = s.get("puuid")
    # 携带战绩数据时绕开缓存重算 (概览任务可能预置了无战绩的旧值),
    # 保证 BP 播报始终按最新 stats 评分
    has_stats = bool(_filter_games(s, None) or s.get("winrate") is not None
                     or s.get("kda") is not None)
    cached = None if has_stats else get_horse_verdict(_cache_key(puuid, use_tier))
    if cached is not None:
        return cached

    wr, kda = _extract_stats(s, queue_ids)
    profile: PlayerHorseProfile = {
        "tierIdx": s.get("tierIdx"),
        "divisionIdx": s.get("divisionIdx"),
        "lp": s.get("lp"),
        "winrate": wr,
        "kda": kda,
    }
    verdict = rate_horse(profile, use_tier=use_tier)
    set_horse_verdict(_cache_key(puuid, use_tier), verdict)
    return verdict


async def fetchVerdictsForTeam(summoners: list[dict],
                               queue_id: Optional[int] = None,
                               style: Optional[str] = None) -> dict[str, HorseVerdict]:
    """队友摘要列表 -> {puuid: HorseVerdict}，供对局页展示.

    复用 _rateSummoner 的缓存；单人失败降级为 Unknown verdict，
    不中断其余查询。无 puuid 的条目跳过。
    queue_id: 当前大厅模式; 大乱斗/海克斯 (450/2400) 只看 KDA, 不参考段位.
    style: 方案 key 覆盖 (通常为调用方进局时已 resolve 的值, 保证 UI 徽章
        与 BP 播报同局同方案); None 时读 cfg 并当场 resolve.
    """
    queue_ids = _queue_group(queue_id)
    use_tier = _uses_tier(queue_id)
    results: dict[str, HorseVerdict] = {}
    # '随机' 风格: 每批 (一局) 只抽一次, 同局所有召唤师统一同一套方案
    resolved = resolve_horse_style(
        style if style is not None else str(cfg.get(cfg.horseRatingStyle)))
    for s in summoners:
        puuid = s.get("puuid")
        if not puuid:
            continue
        try:
            verdict = await _rateSummoner(s, queue_ids, use_tier)
        except Exception as e:  # noqa: BLE001 - 单人失败降级
            logger.warning(
                f"horse rating failed for {puuid}, degrade to Unknown: {e}",
                TAG)
            verdict = {"score": None, "grade": "Unknown", "reason": "查询失败"}
        if verdict is not None and "scheme" not in verdict:
            verdict["scheme"] = resolved
        results[puuid] = verdict
    return results


def _kda_str(s: dict, queue_ids: Optional[tuple] = None) -> str:
    """从 summoner(含 gamesInfo) 提取近局 KDA 串, 对齐 hh: 'K-D-A  K-D-A ...',
    (最多 5 局, 空格分隔); 无可用数据返回 ''. queue_ids 非空时只取该模式组."""
    parts = []
    for g in _filter_games(s, queue_ids):
        if g.get("remake"):
            continue
        k = g.get("kills")
        d = g.get("deaths")
        a = g.get("assists")
        if k is None or d is None or a is None:
            continue
        parts.append(f"{k}-{d}-{a}")
        if len(parts) >= 5:
            break
    return "  ".join(parts)


def _avg_kda_str(s: dict, queue_ids: Optional[tuple] = None) -> str:
    """合计口径平均 KDA 'x.xx'; 无已完成对局返回 ''."""
    avg = _totals_kda(_filter_games(s, queue_ids))
    if avg is None:
        return ""
    return f"{avg:.2f}"


def formatHorseReport(entries: list, style: str = "horse") -> Optional[str]:
    """[(name, verdict, kda_str, avg_kda_str)] -> 播报文案 (逐名一行, \\n 合并).

    按分数阈值定档 (与 UI 徽章同口径, 标签/颜色/分数永远一致):
    同档出现多人时标注队内名次以便区分, 如 '上等马(62·队内#1)'.
    每行形如 '上等马(62): Alice 5-3-2  7-4-5 平均KDA 2.37'; 无战绩者 kda_str 为 '',
    行尾补 ' 未知战绩'; 未知行附带原因 (缺段位/查询失败). 空输入返回 None.
    """
    if not entries:
        return None
    scheme = _horse_scheme(style)
    scored = [e for e in entries if (e[1] or {}).get("score") is not None]
    unknown = [e for e in entries if (e[1] or {}).get("score") is None]
    scored.sort(key=lambda e: e[1]["score"], reverse=True)

    # 统计每档人数: 同档并列时行首标队内名次
    grade_count: dict[str, int] = {}
    for _, verdict, _, _ in scored:
        g = grade_from_score(verdict["score"])
        grade_count[g] = grade_count.get(g, 0) + 1

    lines = []
    for rank, (name, verdict, kda_str, avg_str) in enumerate(scored, start=1):
        score = verdict["score"]
        idx = GRADE_HORSE.index(grade_from_score(score))
        label = scheme[idx]
        head = (f"{label}({score}·队内#{rank})"
                if grade_count[GRADE_HORSE[idx]] > 1 else f"{label}({score})")
        if kda_str:
            tail = f" 平均KDA {avg_str}" if avg_str else ""
            lines.append(f"{head}: {name} {kda_str}{tail}")
        else:
            lines.append(f"{head}: {name} 未知战绩")
    for name, verdict, _, _ in unknown:
        reason = (verdict or {}).get("reason")
        why = f"({reason})" if reason else ""
        lines.append(f"未知战绩{why}: {name}")
    return "\n".join(lines)


async def buildHorseReport(summoners: list[dict],
                           style: Optional[str] = None,
                           queue_id: Optional[int] = None) -> Optional[str]:
    """队友摘要列表 -> BP 聊天播报文案 (对齐 hh-lol-prophet).

    Args:
        summoners: [{puuid, gameName, tagLine, tierIdx, divisionIdx, lp,
                     winrate?, gamesInfo?, kda?}, ...]
        style: 方案 key 覆盖 (内置 'horse' / 用户方案名; '随机' 会被 resolve
            为具体方案); None 时读 cfg.horseRatingStyle. 调用方通常传入
            进局时已 resolve 的值, 与 UI 徽章同局共享同一套方案.
        queue_id: 当前大厅模式; 大乱斗/海克斯大乱斗 (450/2400) 只看近 KDA
            评级 (不参考段位), 且战绩只按 450+2400 统计; 其余模式 (排位/匹配)
            参考段位, 战绩按对应模式组统计 (排位=420+440, 其余同 queueId)

    Returns:
        按综合分从高到低排序、按分数阈值定档的逐行文案 (见 formatHorseReport);
        空队伍返回 None.
    """
    if not summoners:
        return None

    style = style if style is not None else _current_style()
    queue_ids = _queue_group(queue_id)
    use_tier = _uses_tier(queue_id)
    # '随机' 风格: 每批 (一局) 只抽一次, 同局/同批统一用同一套方案
    resolved = resolve_horse_style(style)
    rated: list[tuple[str, HorseVerdict, str, str]] = []
    for s in summoners:
        name = s.get("gameName") or s.get("puuid") or "?"
        try:
            verdict = await _rateSummoner(s, queue_ids, use_tier)
        except Exception as e:  # noqa: BLE001 - 单人失败降级
            logger.warning(
                f"horse rating failed for {name}, degrade to Unknown: {e}",
                TAG)
            verdict = {"score": None, "grade": "Unknown", "reason": "查询失败"}
        if verdict is not None and "scheme" not in verdict:
            verdict["scheme"] = resolved
        rated.append((name, verdict, _kda_str(s, queue_ids), _avg_kda_str(s, queue_ids)))

    scored = [(n, v, k, a) for n, v, k, a in rated if (v or {}).get("score") is not None]
    unknown = [(n, v, k, a) for n, v, k, a in rated if (v or {}).get("score") is None]
    scored.sort(key=lambda e: e[1]["score"], reverse=True)

    return formatHorseReport(scored + unknown, style=resolved)


async def sendWithDelay(message: Optional[str], send_coro_factory,
                        delay_range=(2.0, 5.0)) -> bool:
    """随机延迟后执行发送回调; 返回发送是否成功.

    send_coro_factory: () -> coroutine, 由调用侧绑定 connector 方法.
    """
    if not message:
        return False
    await asyncio.sleep(random.uniform(*delay_range))
    return bool(await send_coro_factory())
