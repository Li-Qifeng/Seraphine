"""战犯/躺赢狗诊断算法.

设计原则 (用户明确要求):
1. 只看本局数据, 不讨论局外因素 (挂机/网络/对手代练等)
2. 海克斯大乱斗 (queueId=2400) 视野分不计入评分
3. 海克斯强化纳入计分: 按 OPGG 强化 pick/win 算用户组合强度, 强组合英雄"预期贡献"基线更高
4. 历史对照使用 OPGG 该英雄胜率: 胜率高的英雄在胜局"躺赢狗"概率与负局"战犯"概率都应更大
5. 标准化: 所有指标按队伍内同位置平均算 z-score, 避免全输出阵容里坦克被误判

输出 verdict:
- "war_criminal" (负局, 显著低于队友, 是战犯)
- "carried_dog" (胜局, 显著低于队友, 是躺赢狗)
- "no_clear_suspect" (无明显异常, 不挂标签)
- "team_underperformed" (整队都低, 不单独点名)
"""
import asyncio
from typing import Optional, TypedDict

TAG = "WarCriminal"

# 海克斯大乱斗 queueId (国际/国服)
HEXTECH_QUEUE_IDS = (2400,)

# 海克斯强化影响预期伤害基线的强度: 0=不调, 1=强化分翻倍预期
AUGMENT_BASELINE_WEIGHT = 0.3

# OPGG 胜率对最终评分的权重: 胜率高的英雄在躺赢/战犯判定时偏离放大
CHAMPION_BASELINE_WEIGHT = 0.4

# 灵敏度档位 -> z 阈值
SENSITIVITY_Z = {
    'loose': 0.6,   # 宽松: 更易判定为躺赢狗/战犯
    'normal': 0.8,
    'strict': 1.1,
}

# 各项指标权重 (按角色粗二分: 全输出/坦克辅助). 海克斯模式一律走"输出"分支
# 数值越大表示该指标对"贡献"的正向权重越大
ROLE_WEIGHTS = {
    'dps': {  # 输出位 (法师/ADC/刺客/战士)
        'damage': 0.40,
        'gold': 0.15,
        'cs': 0.10,
        'kda': 0.20,
        'death': 0.15,
        'damage_taken': 0.0,
        'shield_heal': 0.0,
        'cc': 0.0,
        'vision': 0.0,
    },
    'tank_support': {  # 坦克/辅助
        'damage_taken': 0.30,
        'cc': 0.20,
        'shield_heal': 0.20,
        'damage': 0.10,
        'kda': 0.10,
        'death': 0.10,
        'gold': 0.0,
        'cs': 0.0,
        'vision': 0.0,  # 海克斯不计视野, 其他模式默认也不算
    },
}


class ParticipantStats(TypedDict, total=False):
    """战犯评分所需的本局玩家数据 (从 parseGameDetailData 提取)."""
    puuid: Optional[str]
    championId: int
    kills: int
    deaths: int
    assists: int
    damage: int              # totalDamageDealtToChampions
    damageTaken: int         # totalDamageTaken
    totalHeal: int
    shieldOnTeammates: int   # totalDamageShieldedOnTeammates
    ccTime: float            # timeCCingOthers
    gold: int                # goldEarned
    cs: int                  # totalMinionsKilled + neutralMinionsKilled
    visionScore: float
    win: bool
    augmentIds: list         # 海克斯强化 id 列表 (空表示非海克斯)


class VerdictResult(TypedDict, total=False):
    verdict: str
    suspect: Optional[ParticipantStats]
    score: float
    secondScore: float
    threshold: float
    evidence: list   # list of dict {metric, value, teamAvg, zScore, severity}


def _kda(stats: ParticipantStats) -> float:
    k = stats.get('kills', 0) or 0
    d = stats.get('deaths', 0) or 0
    a = stats.get('assists', 0) or 0
    if d == 0:
        return float(k + a)  # 0 死用 KA 代替, 避免除零
    return (k + a) / d


def _mean(values: list) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    var = sum((v - m) ** 2 for v in values) / len(values)
    return var ** 0.5


def _zScore(values: list, value: float) -> float:
    """计算 value 在 values 中的 z-score. 单点或全相同时返回 0."""
    if len(values) < 2:
        return 0.0
    s = _std(values)
    if s < 1e-6:
        return 0.0
    return (value - _mean(values)) / s


def _roleOf(championId: int, queueId: Optional[int]) -> str:
    """英雄角色粗分类. 海克斯模式一律返回 dps (全输出阵容)."""
    # 海克斯大乱斗没有明确位置且阵容偏输出, 统一按 dps 评分
    if queueId in HEXTECH_QUEUE_IDS:
        return 'dps'
    # 其他模式: 简单按英雄 id 模 2 划分 (后续可扩展为查表)
    # 这里仅做兜底, 实际项目可引入 champion_roles.json
    return 'dps' if championId % 2 == 0 else 'tank_support'


def _shieldHeal(stats: ParticipantStats) -> float:
    return float((stats.get('totalHeal') or 0) +
                 (stats.get('shieldOnTeammates') or 0))


async def _expectedBaselineMultiplier(stats: ParticipantStats,
                                      queueId: Optional[int]) -> float:
    """计算该玩家的"预期贡献基线倍率".

    返回 1.0 表示中性 (无 OPGG 数据时).
    > 1.0 表示该英雄/强化组合强, 玩家"应贡献更多", 实际贡献低更易判战犯.
    < 1.0 表示该英雄/强化组合弱, 玩家"应贡献少", 实际贡献低不易判战犯.
    """
    multipliers = []

    # 海克斯强化组合分 (lazy import 避免 opgg/aiohttp 链式依赖)
    augIds = stats.get('augmentIds') or []
    if queueId in HEXTECH_QUEUE_IDS and augIds:
        from .augment_baseline import getHextechAugmentScore
        augScore = await getHextechAugmentScore(augIds, stats.get('championId'))
        if augScore is not None:
            # augScore 在 [0,1], 0.5 视为中性, 映射到 [1-W, 1+W] 倍率
            m = 1.0 + AUGMENT_BASELINE_WEIGHT * (augScore - 0.5) * 2
            multipliers.append(m)

    # 英雄 OPGG 胜率基线 (lazy import)
    from .champion_baseline import getChampionBaselineWinrate
    wr = await getChampionBaselineWinrate(stats.get('championId'), queueId)
    if wr is not None:
        # wr 在 [0,1], 0.5 视为中性, 映射到 [1-W, 1+W] 倍率
        # 胜率高的英雄预期贡献高
        m = 1.0 + CHAMPION_BASELINE_WEIGHT * (wr - 0.5) * 2
        multipliers.append(m)

    if not multipliers:
        return 1.0
    # 多重倍率取几何平均, 避免叠加放大过度
    prod = 1.0
    for m in multipliers:
        prod *= max(0.1, m)
    return prod ** (1.0 / len(multipliers))


def _computeContribution(stats: ParticipantStats,
                         team: list,
                         role: str,
                         baselineMultiplier: float,
                         isHextech: bool) -> tuple:
    """计算单个玩家的"贡献 z-score".

    z-score 基线使用全队而非同 role: 避免 2 人同 role 时 z 被限制在 ±1,
    无法识别"伤害 5000 vs 30000"这类极端异常.
    坦克/辅助角色通过 ROLE_WEIGHTS 的低伤害权重保护, 不会被误判.

    Returns:
        (contribution_z, evidence_list)
    """
    w = ROLE_WEIGHTS.get(role, ROLE_WEIGHTS['dps'])

    # 全队各项指标作为 z-score 基线 (不再按 role 分组, 否则极端异常被均化)
    damages = [p.get('damage') or 0 for p in team]
    golds = [p.get('gold') or 0 for p in team]
    css = [p.get('cs') or 0 for p in team]
    kdas = [_kda(p) for p in team]
    deaths = [p.get('deaths') or 0 for p in team]
    dmgTaken = [p.get('damageTaken') or 0 for p in team]
    shieldHeals = [_shieldHeal(p) for p in team]
    ccs = [p.get('ccTime') or 0 for p in team]
    # 海克斯模式视野分不计入
    visions = [] if isHextech else [p.get('visionScore') or 0 for p in team]

    # 该玩家实际值 (会被 baseline 调整预期)
    myDmg = stats.get('damage') or 0
    myGold = stats.get('gold') or 0
    myCs = stats.get('cs') or 0
    myKda = _kda(stats)
    myDeaths = stats.get('deaths') or 0
    myDmgTaken = stats.get('damageTaken') or 0
    myShieldHeal = _shieldHeal(stats)
    myCc = stats.get('ccTime') or 0
    myVision = stats.get('visionScore') or 0

    # z-score: 实际值 vs 队友
    z_dmg = _zScore(damages, myDmg)
    z_gold = _zScore(golds, myGold)
    z_cs = _zScore(css, myCs)
    z_kda = _zScore(kdas, myKda)
    z_death = _zScore(deaths, myDeaths)
    z_taken = _zScore(dmgTaken, myDmgTaken)
    z_sh = _zScore(shieldHeals, myShieldHeal)
    z_cc = _zScore(ccs, myCc)
    z_vis = _zScore(visions, myVision) if visions else 0.0

    # 海克斯模式视野权重强制归零
    if isHextech:
        w = {**w, 'vision': 0.0}

    # 加权贡献 (正值=贡献高, 负值=贡献低)
    # baseline 放大伤害贡献: 强英雄/强组合玩家 (baselineMultiplier>1) 时,
    # 伤害 z 被乘以倍率 — z<0 (低于平均) 被进一步扣分, z>0 (高于平均) 被进一步加分.
    # 这样 OPGG 胜率高的英雄在胜局更易被判躺赢狗, 在负局更易被判战犯.
    contribution = (
        w.get('damage', 0) * z_dmg * baselineMultiplier +
        w.get('gold', 0) * z_gold +
        w.get('cs', 0) * z_cs +
        w.get('kda', 0) * z_kda +
        w.get('damage_taken', 0) * z_taken +
        w.get('shield_heal', 0) * z_sh +
        w.get('cc', 0) * z_cc +
        w.get('vision', 0) * z_vis
    )
    # 死亡越多越扣分 (z_death 正值表示比队友死更多)
    contribution -= w.get('death', 0) * z_death

    # 证据列表
    evidence = _buildEvidence(
        myDmg, _mean(damages), z_dmg,
        myDeaths, _mean(deaths), z_death,
        myGold, _mean(golds), z_gold,
        myKda, _mean(kdas), z_kda,
        myDmgTaken, _mean(dmgTaken), z_taken,
        myShieldHeal, _mean(shieldHeals), z_sh,
        myCc, _mean(ccs), z_cc,
        myVision, _mean(visions), z_vis,
        isHextech,
    )

    return contribution, evidence


def _buildEvidence(myDmg, avgDmg, zDmg,
                   myDeaths, avgDeaths, zDeaths,
                   myGold, avgGold, zGold,
                   myKda, avgKda, zKda,
                   myTaken, avgTaken, zTaken,
                   mySh, avgSh, zSh,
                   myCc, avgCc, zCc,
                   myVis, avgVis, zVis,
                   isHextech) -> list:
    def sev(z):
        if z >= 1.5:
            return 'high_pos'
        if z >= 0.8:
            return 'pos'
        if z <= -1.5:
            return 'high_neg'
        if z <= -0.8:
            return 'neg'
        return 'normal'

    items = [
        {'metric': 'damage', 'value': myDmg, 'teamAvg': avgDmg,
         'zScore': round(zDmg, 2), 'severity': sev(zDmg)},
        {'metric': 'deaths', 'value': myDeaths, 'teamAvg': avgDeaths,
         'zScore': round(zDeaths, 2), 'severity': sev(zDeaths)},
        {'metric': 'gold', 'value': myGold, 'teamAvg': avgGold,
         'zScore': round(zGold, 2), 'severity': sev(zGold)},
        {'metric': 'kda', 'value': round(myKda, 2), 'teamAvg': round(avgKda, 2),
         'zScore': round(zKda, 2), 'severity': sev(zKda)},
        {'metric': 'damage_taken', 'value': myTaken, 'teamAvg': avgTaken,
         'zScore': round(zTaken, 2), 'severity': sev(zTaken)},
        {'metric': 'shield_heal', 'value': mySh, 'teamAvg': avgSh,
         'zScore': round(zSh, 2), 'severity': sev(zSh)},
        {'metric': 'cc', 'value': myCc, 'teamAvg': avgCc,
         'zScore': round(zCc, 2), 'severity': sev(zCc)},
    ]
    if not isHextech:
        items.append({'metric': 'vision', 'value': myVis, 'teamAvg': avgVis,
                      'zScore': round(zVis, 2), 'severity': sev(zVis)})
    return items


async def diagnoseTeam(team: list,
                       queueId: Optional[int],
                       isWin: bool,
                       sensitivity: str = 'normal') -> Optional[VerdictResult]:
    """诊断一队玩家, 找出最显著的"躺赢狗"或"战犯".

    Args:
        team: list[ParticipantStats], 同队玩家 (5 或 4 人)
        queueId: 队列 id, 用于判断海克斯模式
        isWin: 该队是否获胜 (胜局找躺赢狗, 负局找战犯)
        sensitivity: 'loose' | 'normal' | 'strict'

    Returns:
        VerdictResult 或 None (队伍太小/无数据时).
    """
    if not team or len(team) < 2:
        return None

    isHextech = queueId in HEXTECH_QUEUE_IDS
    threshold = SENSITIVITY_Z.get(sensitivity, SENSITIVITY_Z['normal'])

    # 计算每个玩家的 baseline (异步并发)
    baselines = await asyncio.gather(
        *[_expectedBaselineMultiplier(p, queueId) for p in team]
    )

    scored = []
    for i, p in enumerate(team):
        role = _roleOf(p.get('championId'), queueId)
        contribution, evidence = _computeContribution(
            p, team, role, baselines[i], isHextech)
        scored.append({
            'participant': p,
            'score': contribution,
            'evidence': evidence,
        })

    scored.sort(key=lambda x: x['score'])
    worst = scored[0]
    second = scored[1] if len(scored) > 1 else None
    secondScore = second['score'] if second else 0.0

    # 整队都低 (worst score 不算特别低, 但都接近): 不点名
    # 判定: worst 与 second 的差 < 0.3 且 worst 绝对分 > -0.5
    if abs(worst['score'] - secondScore) < 0.3 and worst['score'] > -0.5:
        return {
            'verdict': 'team_underperformed',
            'suspect': worst['participant'],
            'score': round(worst['score'], 3),
            'secondScore': round(secondScore, 3),
            'threshold': threshold,
            'evidence': worst['evidence'],
        }

    # 显著低于第二名 (z 差 >= threshold) -> 命名
    if (secondScore - worst['score']) >= threshold:
        verdict = 'carried_dog' if isWin else 'war_criminal'
        return {
            'verdict': verdict,
            'suspect': worst['participant'],
            'score': round(worst['score'], 3),
            'secondScore': round(secondScore, 3),
            'threshold': threshold,
            'evidence': worst['evidence'],
        }

    # 没有显著异常
    return {
        'verdict': 'no_clear_suspect',
        'suspect': worst['participant'],
        'score': round(worst['score'], 3),
        'secondScore': round(secondScore, 3),
        'threshold': threshold,
        'evidence': worst['evidence'],
    }


def verdictLabel(verdict: str, isWin: bool) -> str:
    """verdict -> 用户可见标签."""
    if verdict == 'war_criminal':
        return '战犯'
    if verdict == 'carried_dog':
        return '躺赢狗'
    if verdict == 'team_underperformed':
        return '团队低迷'
    if verdict == 'no_clear_suspect':
        return '无明显异常'
    return ''
