# -*- coding: utf-8 -*-
"""上等马赛前评级 + BP 聊天窗播报编排层.

纯编排 (可测): 输入队友摘要 (LCU 可见段位), 输出一行播报文案;
缓存细节收敛在内部, 单人失败降级 Unknown 不中断整体.
不依赖任何第三方数据源 — 数据全来自 LCU 对局接口的 rankInfo.
不负责发送 — 发送由 main_window 调 connector.sendChampSelectMessage 完成.
"""
import asyncio
import random
from typing import Any, Optional

from app.common.config import cfg
from app.common.logger import logger
from app.lol.horse_rating import HorseVerdict, PlayerHorseProfile, grade_label, rate_horse
from app.lol.horse_rating_cache import get_horse_verdict, set_horse_verdict

TAG = "HorseOrchestrator"

MESSAGE_PREFIX = "[Seraphine]"

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


async def _rateSummoner(s: dict) -> HorseVerdict:
    """单个召唤师摘要 -> HorseVerdict. 缓存命中直接返回; 字段缺失返回 Unknown."""
    puuid = s.get("puuid")
    cached = get_horse_verdict(puuid)
    if cached is not None:
        return cached

    profile: PlayerHorseProfile = {
        "tierIdx": s.get("tierIdx"),
        "divisionIdx": s.get("divisionIdx"),
        "lp": s.get("lp"),
    }
    verdict = rate_horse(profile)
    set_horse_verdict(puuid, verdict)
    return verdict


async def fetchVerdictsForTeam(summoners: list[dict]) -> dict[str, HorseVerdict]:
    """队友摘要列表 -> {puuid: HorseVerdict}，供对局页展示.

    复用 _rateSummoner 的缓存；单人失败降级为 Unknown verdict，
    不中断其余查询。无 puuid 的条目跳过。
    """
    results: dict[str, HorseVerdict] = {}
    for s in summoners:
        puuid = s.get("puuid")
        if not puuid:
            continue
        try:
            results[puuid] = await _rateSummoner(s)
        except Exception as e:  # noqa: BLE001 - 单人失败降级
            logger.warning(
                f"horse rating failed for {puuid}, degrade to Unknown: {e}",
                TAG)
            results[puuid] = {"score": None, "grade": "Unknown",
                              "style_labels": {}, "reason": "查询失败"}
    return results


def formatHorseReport(entries: list, style: str = "horse") -> Optional[str]:
    """[(name, verdict)] -> 一行播报文案; 空输入返回 None."""
    if not entries:
        return None
    parts = []
    for name, verdict in entries:
        score = (verdict or {}).get("score")
        label = grade_label(score, style=style)
        if score is None:
            parts.append(f"{label}: {name}")
        else:
            parts.append(f"{label}: {name}({score}分)")
    return f"{MESSAGE_PREFIX} " + " | ".join(parts)


async def buildHorseReport(summoners: list[dict],
                           style: Optional[str] = None) -> Optional[str]:
    """队友摘要列表 -> BP 聊天播报文案.

    Args:
        summoners: [{puuid, gameName, tagLine, tierIdx, divisionIdx, lp}, ...]
        style: 文案风格覆盖 ('horse'|'formal'); None 时读 cfg.horseRatingStyle

    Returns:
        形如 "[Seraphine] 上等马: A(85分) | 中等马: B(52分)" 的一行文案;
        空队伍返回 None.
    """
    if not summoners:
        return None

    style = style if style is not None else _current_style()
    entries: list[tuple[str, Any]] = []
    for s in summoners:
        name = s.get("gameName") or s.get("puuid") or "?"
        try:
            verdict = await _rateSummoner(s)
        except Exception as e:  # noqa: BLE001 - 单人失败降级
            logger.warning(
                f"horse rating failed for {name}, degrade to Unknown: {e}",
                TAG)
            verdict: HorseVerdict = {"score": None, "grade": "Unknown",
                                     "style_labels": {}, "reason": "查询失败"}
        entries.append((name, verdict))

    return formatHorseReport(entries, style=style)


async def sendWithDelay(message: Optional[str], send_coro_factory,
                        delay_range=(2.0, 5.0)) -> bool:
    """随机延迟后执行发送回调; 返回发送是否成功.

    send_coro_factory: () -> coroutine, 由调用侧绑定 connector 方法.
    """
    if not message:
        return False
    await asyncio.sleep(random.uniform(*delay_range))
    return bool(await send_coro_factory())
