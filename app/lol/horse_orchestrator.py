# -*- coding: utf-8 -*-
"""上等马赛前评级 + BP 聊天窗播报编排层.

纯编排 (可测): 输入队友摘要列表, 输出一行播报文案;
网络/缓存细节收敛在内部, 单人失败降级 Unknown 不中断整体.
不负责发送 — 发送由 main_window 调 connector.sendChampSelectMessage 完成.
"""
import asyncio
import random
from typing import Any, Optional

from app.common.config import cfg
from app.common.logger import logger
from app.lol.horse_rating import HorseVerdict, PlayerHorseProfile, grade_label, rate_horse
from app.lol.horse_rating_cache import get_horse_verdict, set_horse_verdict
from app.lol.lzyumi import LzyumiUnavailable, lzyumi

TAG = "HorseOrchestrator"

MESSAGE_PREFIX = "[Seraphine]"
RECENT_GAMES_COUNT = 10

# 可见段位中文名 -> 段位序数 (宗师并入王者档, 与 TIER_ELO_MIDPOINTS 对齐)
TIER_NAME_TO_IDX = {
    "黑铁": 0, "黄铜": 1, "白银": 2, "黄金": 3, "铂金": 4,
    "翡翠": 5, "钻石": 6, "大师": 7, "宗师": 8, "王者": 8,
}

# LCU rso_platform_id -> lzyumi areaId (对照参考站前端下拉表)
SERVER_TO_AREA_ID = {
    "HN1": 1,     # 艾欧尼亚
    "HN10": 14,   # 黑色玫瑰
    "BGP2": 31,   # 峡谷之巅
    "NJ100": 3,   # 联盟一区 (祖安等)
    "GZ100": 4,   # 联盟二区 (诺克萨斯等)
    "CQ100": 2,   # 联盟三区 (班德尔城等)
    "TJ100": 6,   # 联盟四区 (德玛西亚等)
    "TJ101": 9,   # 联盟五区 (弗雷尔卓德等)
}


def serverToAreaId(server: Optional[str]) -> int:
    """LCU 大区标识 -> lzyumi areaId; 未知返回默认恕瑞玛(16)."""
    return SERVER_TO_AREA_ID.get((server or "").upper(), 16)


def tierNameToIdx(name: Optional[str]) -> Optional[int]:
    """段位显示名 -> 序数; 无法识别返回 None."""
    if not name:
        return None
    return TIER_NAME_TO_IDX.get(str(name).strip())


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


def _recentStats(games: list) -> tuple:
    """近十场 games 列表 -> (winRate|None, kda=None, mvpSvpCount).

    lzyumi 的 games 无 KDA 字段, KDA 固定传 None (只用胜率+MVP).
    """
    if not games:
        return None, None, 0
    wins = sum(1 for g in games if g.get("isWin"))
    mvp = sum(1 for g in games if g.get("isMvp") or g.get("isSvp"))
    return wins / len(games), None, mvp


async def _rateSummoner(s: dict, area_id: int) -> HorseVerdict:
    """单个召唤师 -> HorseVerdict. 缓存命中不发网络; 失败向上抛异常."""
    puuid = s.get("puuid")
    cached = get_horse_verdict(puuid)
    if cached is not None:
        return cached

    game_name = s.get("gameName") or ""
    tag_line = s.get("tagLine")
    nickname = f"{game_name}#{tag_line}" if tag_line else game_name

    payload = await lzyumi.searchPlayer(nickname, area_id, RECENT_GAMES_COUNT)
    win_rate, _, mvp_count = _recentStats(payload.get("games") or [])

    elo = None
    battle_info = payload.get("battleInfo") or {}
    open_id = battle_info.get("openId")
    if open_id:
        elo_info = await lzyumi.getRankEloInfo(open_id, area_id)
        if elo_info:
            elo = elo_info.get("solo")

    profile: PlayerHorseProfile = {
        "elo": elo,
        "visibleTierIdx": s.get("tierIdx"),
        "recent10WinRate": win_rate,
        "recent10KdaAvg": None,
        "mvpSvpCount": mvp_count,
    }
    verdict = rate_horse(profile)
    set_horse_verdict(puuid, verdict)
    return verdict


async def fetchVerdictsForTeam(summoners: list[dict],
                               cfg_areaId: int) -> dict[str, HorseVerdict]:
    """队友摘要列表 -> {puuid: HorseVerdict}，供对局页/生涯页展示.

    复用 _rateSummoner 的缓存；单人失败降级为 Unknown verdict，
    不中断其余查询。无 puuid 的条目跳过。
    """
    results: dict[str, HorseVerdict] = {}
    for s in summoners:
        puuid = s.get("puuid")
        if not puuid:
            continue
        try:
            results[puuid] = await _rateSummoner(s, cfg_areaId)
        except (LzyumiUnavailable, Exception) as e:  # noqa: BLE001 - 单人失败降级
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


async def buildHorseReport(summoners: list[dict], cfg_areaId: int,
                           style: Optional[str] = None) -> Optional[str]:
    """队友摘要列表 -> BP 聊天播报文案.

    Args:
        summoners: [{puuid, gameName, tagLine, tierIdx}, ...]
        cfg_areaId: lzyumi 查询区服 id
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
            verdict = await _rateSummoner(s, cfg_areaId)
        except (LzyumiUnavailable, Exception) as e:  # noqa: BLE001 - 单人失败降级
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
