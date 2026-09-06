"""全队 5 档评级算法.

设计原则 (用户明确要求):
1. 只看本局数据, 不讨论局外因素 (挂机/网络/对手代练等)
2. 海克斯大乱斗 (queueId=2400) 视野分不计入评分
3. 海克斯强化纳入计分: 按 OPGG 强化 pick/win 算用户组合强度, 强组合英雄"预期贡献"基线更高
4. 历史对照使用 OPGG 该英雄胜率: 胜率高的英雄在胜局"躺赢"概率与负局"战犯"概率都应更大
5. 标准化: 所有指标按队伍内同位置平均算 z-score, 避免全输出阵容里坦克被误判

输出 5 档评级 (胜方/败方各一套贴吧风标签, 或马系风通用标签):
- 胜方: 神 / 爹 / 小有亮点 / 躺赢狗 / 消失
- 败方: 人类 / 类人 / 战犯嫌疑人 / 甲级战犯 / 初升东曦
- 马系: 上等马 / 中等马 / 下等马 / 纯牛马 / 没有马
"""
import asyncio
import json
import logging
import pathlib
import random
from typing import Optional, TypedDict

TAG = "WarCriminal"
logger = logging.getLogger(__name__)

# 海克斯大乱斗 queueId (国际/国服)
HEXTECH_QUEUE_IDS = (2400,)
# 嚎哭深渊 (ARAM)
ARAM_QUEUE_IDS = (450,)
# 有推塔/史诗野怪的模式 (召唤师峡谷)
OBJECTIVE_MODES = (420, 440)

# 海克斯强化影响预期伤害基线的强度: 0=不调, 1=强化分翻倍预期
AUGMENT_BASELINE_WEIGHT = 0.3

# OPGG 胜率对最终评分的权重: 胜率高的英雄在躺赢/战犯判定时偏离放大
CHAMPION_BASELINE_WEIGHT = 0.4

# 各项指标权重 (按角色粗二分: 全输出/坦克辅助). 海克斯/大乱斗一律走"输出"分支
# 数值越大表示该指标对"贡献"的正向权重越大
ROLE_WEIGHTS = {
    'dps': {  # 输出位 (法师/ADC/刺客)
        'damage': 0.30,
        'gold': 0.10,
        'cs': 0.05,
        'kda': 0.15,
        'death': 0.12,
        'damage_taken': 0.0,
        'shield_heal': 0.0,
        'cc': 0.0,
        'vision': 0.0,
        'damage_efficiency': 0.10,   # 伤害/金币 (经济效率)
        'kill_participation': 0.15,  # 参团率 (团队参与度)
        'siege_damage': 0.08,        # 推塔+史诗野怪 (仅召唤师峡谷)
    },
    'tank_support': {  # 坦克/辅助/战士
        'damage_taken': 0.25,
        'cc': 0.18,
        'shield_heal': 0.17,
        'damage': 0.08,
        'kda': 0.08,
        'death': 0.08,
        'gold': 0.0,
        'cs': 0.0,
        'vision': 0.05,  # 仅召唤师峡谷计入
        'damage_efficiency': 0.0,
        'kill_participation': 0.11,
        'siege_damage': 0.0,
    },
}


class ParticipantStats(TypedDict, total=False):
    """评级所需的本局玩家数据 (从 parseGameDetailData 提取)."""
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
    siegeDamage: int         # damageToTurrets + damageToObjectives (仅召唤师峡谷)


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


# 英雄角色映射缓存 (避免每次调用读 JSON)
_CHAMPION_ROLES = None


def _roleOf(championId: int) -> str:
    """英雄角色分类 (按 champion_roles.json 查表, 所有模式统一).

    大乱斗/海克斯不再强制 dps: 坦克/辅助按 tank_support 权重计
    承伤/CC/护盾, 消除"玩坦克天然低分"的系统性偏差;
    其视野/推塔指标仍由 _computeContribution 按模式归零.
    """
    global _CHAMPION_ROLES
    if _CHAMPION_ROLES is None:
        _roles_path = pathlib.Path(__file__).parent / 'champion_roles.json'
        if _roles_path.exists():
            _CHAMPION_ROLES = json.loads(_roles_path.read_text(encoding='utf-8'))
        else:
            _CHAMPION_ROLES = {}
    return _CHAMPION_ROLES.get(str(championId), 'dps')


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
                         isHextech: bool,
                         isAram: bool,
                         hasObjectives: bool) -> tuple:
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
    # 海克斯/大乱斗不计视野
    visions = [] if (isHextech or isAram) else [p.get('visionScore') or 0 for p in team]
    # 推塔+史诗野怪 (仅召唤师峡谷)
    sieges = [] if not hasObjectives else [p.get('siegeDamage') or 0 for p in team]

    # 参团率: (kills+assists) / team_total_kills
    teamTotalKills = sum(p.get('kills', 0) or 0 for p in team)
    killParticipations = [
        ((p.get('kills', 0) or 0) + (p.get('assists', 0) or 0)) /
        max(teamTotalKills, 1)
        for p in team
    ]
    # 伤害转化率: damage / max(gold, 1)
    damageEfficiencies = [
        (p.get('damage') or 0) / max(p.get('gold') or 0, 1)
        for p in team
    ]

    # 该玩家实际值
    myDmg = stats.get('damage') or 0
    myGold = stats.get('gold') or 0
    myCs = stats.get('cs') or 0
    myKda = _kda(stats)
    myDeaths = stats.get('deaths') or 0
    myDmgTaken = stats.get('damageTaken') or 0
    myShieldHeal = _shieldHeal(stats)
    myCc = stats.get('ccTime') or 0
    myVision = stats.get('visionScore') or 0
    mySiege = stats.get('siegeDamage') or 0
    myKills = stats.get('kills', 0) or 0
    myAssists = stats.get('assists', 0) or 0
    myKp = (myKills + myAssists) / max(teamTotalKills, 1)
    myEff = myDmg / max(myGold, 1)

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
    z_siege = _zScore(sieges, mySiege) if sieges else 0.0
    z_kp = _zScore(killParticipations, myKp)
    z_eff = _zScore(damageEfficiencies, myEff)

    # 模式特定: 海克斯/大乱斗视野/推塔权重归零
    if isHextech or isAram:
        w = {**w, 'vision': 0.0, 'siege_damage': 0.0}
    if not hasObjectives:
        w = {**w, 'siege_damage': 0.0}

    # baseline 倍率作用到全部分数: 强英雄/强组合玩家 (baselineMultiplier>1) 时,
    # 贡献分被放大 — 表现差 (负分) 被进一步扣分, 表现好 (正分) 被进一步加分.
    # 这样 OPGG 胜率高的英雄在胜局更易被判躺赢狗, 在负局更易被判战犯.
    contribution = (
        w.get('damage', 0) * z_dmg +
        w.get('gold', 0) * z_gold +
        w.get('cs', 0) * z_cs +
        w.get('kda', 0) * z_kda +
        w.get('damage_taken', 0) * z_taken +
        w.get('shield_heal', 0) * z_sh +
        w.get('cc', 0) * z_cc +
        w.get('vision', 0) * z_vis +
        w.get('damage_efficiency', 0) * z_eff +
        w.get('kill_participation', 0) * z_kp +
        w.get('siege_damage', 0) * z_siege
    )
    contribution -= w.get('death', 0) * z_death
    contribution *= baselineMultiplier

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
        isHextech, isAram,
        mySiege, _mean(sieges), z_siege,
        myKp, _mean(killParticipations), z_kp,
        myEff, _mean(damageEfficiencies), z_eff,
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
                   isHextech, isAram,
                   mySiege, avgSiege, zSiege,
                   myKp, avgKp, zKp,
                   myEff, avgEff, zEff) -> list:
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
        {'metric': 'kill_participation', 'value': round(myKp, 3),
         'teamAvg': round(avgKp, 3), 'zScore': round(zKp, 2),
         'severity': sev(zKp)},
        {'metric': 'damage_efficiency', 'value': round(myEff, 2),
         'teamAvg': round(avgEff, 2), 'zScore': round(zEff, 2),
         'severity': sev(zEff)},
    ]
    if not isHextech and not isAram:
        items.append({'metric': 'vision', 'value': myVis, 'teamAvg': avgVis,
                      'zScore': round(zVis, 2), 'severity': sev(zVis)})
        items.append({'metric': 'siege_damage', 'value': mySiege,
                      'teamAvg': round(avgSiege, 2), 'zScore': round(zSiege, 2),
                      'severity': sev(zSiege)})
    return items


async def _computeTeamScores(team: list,
                              queueId: Optional[int]) -> list:
    """计算全队每个玩家的 z-score 贡献分 (一次计算, 供分级使用).

    Args:
        team: list[ParticipantStats], 同队玩家
        queueId: 队列 id (用于判断海克斯/大乱斗/召唤师峡谷)

    Returns:
        list[dict], 每项 {puuid, championId, score, evidence}, 按 score 降序.
        队伍太小 (<2人) 时返回空列表.
    """
    if not team or len(team) < 2:
        return []

    isHextech = queueId in HEXTECH_QUEUE_IDS
    isAram = queueId in ARAM_QUEUE_IDS
    hasObjectives = queueId in OBJECTIVE_MODES

    # 计算每个玩家的 baseline (异步并发)
    baselines = await asyncio.gather(
        *[_expectedBaselineMultiplier(p, queueId) for p in team]
    )

    scored = []
    for i, p in enumerate(team):
        role = _roleOf(p.get('championId'))
        contribution, evidence = _computeContribution(
            p, team, role, baselines[i], isHextech, isAram, hasObjectives)
        scored.append({
            'puuid': p.get('puuid'),
            'championId': p.get('championId', 0) or 0,
            'score': round(contribution, 3),
            'evidence': evidence,
        })

    # 按 score 降序 (贡献最大的在前)
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored


# ===========================================================================
# 全队 5 档评级 (扩展: 给每个队友打标签, 不只是 worst)
# ===========================================================================

# 5 档评级阈值 (基于 z-score 综合贡献分)
# score 越高 = 对团队贡献越大
GRADE_THRESHOLDS = (1.0, 0.3, -0.3, -1.0)  # 5 档的分界点

# 排位模式档内排名微调参数:
# 匹配机制锚定局内实力接近, 表现方差小, 5 人 z 常全落中间档 (宽 0.6) 同一档,
# 绝对阈值区分度不足 (大乱斗方差大自然跨档, 无此问题).
# 同档 >= RANK_ADJUST_MIN_GROUP 人时, 与相邻队友 z 差 >= RANK_ADJUST_EPS 的
# 档内 top1 升一档 / bottom1 降一档; 差距在噪声内 (z 差 < EPS) 不动, 不冤枉人.
RANK_ADJUST_EPS = 0.15
RANK_ADJUST_MIN_GROUP = 3

# 贴吧风标签 (胜方/败方各一套)
GRADE_LABELS_TIEBA = {
    True: ['神', '爹', '小有亮点', '躺赢狗', '消失'],      # 胜方
    False: ['人类', '类人', '战犯嫌疑人', '甲级战犯', '初升东曦'],  # 败方
}

# 马系风标签 (胜败方通用, 与赛前评级 horse_rating.GRADE_HORSE 一致)
GRADE_LABELS_HORSE = {
    True: ['上等马', '中等马', '下等马', '纯牛马', '没有马'],
    False: ['上等马', '中等马', '下等马', '纯牛马', '没有马'],
}

# ===========================================================================
# 结算评级方案 (模板): 内置(只读, 代码常量) + 用户命名方案(存 config)
# 每个方案 = {win:[标签×5], loss:[标签×5],
#             winComment:[评语×5], lossComment:[评语×5], builtin:bool}
# 评语为空串 = 悬停只显示技术证据 (不显示该档评语).
# 方案以 "key" 存储; 内置 key 固定, 用户方案以用户输入的方案名为 key.
# ===========================================================================

# 随机选项 key (风格下拉新增; 每局在全部内置+用户方案中抽一套)
RANDOM_TEAM_KEY = '随机'

# 内置方案 key -> 中文展示名 (风格下拉显示用)
BUILTIN_TEAM_KEYS = ('tieba', 'horse', 'dianjingxuexie',
                     'yinyangneihan', 'wulichaodu', 'jinzhushuqi')
DEFAULT_TEAM_KEY = 'tieba'
BUILTIN_TEAM_DISPLAY = {
    'tieba': '初升东曦',
    'horse': '没有马',
    'dianjingxuexie': '电竞纯血',
    'yinyangneihan': '阴阳内涵',
    'wulichaodu': '物理超度',
    'jinzhushuqi': '尽搞畜蛆寄',
}
# 内置方案的默认展示名 (用于 UI 文案)
DEFAULT_TEAM_DISPLAY = '初升东曦'


def _builtin_team_scheme(key: str) -> dict:
    """按内置 key 返回方案 dict (只读, 每次现构造, 无共享可变引用)."""
    if key == 'tieba':
        return {
            'name': 'tieba',
            'win': list(GRADE_LABELS_TIEBA[True]),
            'loss': list(GRADE_LABELS_TIEBA[False]),
            'winComment': [''] * 5,
            'lossComment': [''] * 5,
            'builtin': True,
        }
    if key == 'horse':
        return {
            'name': 'horse',
            'win': list(GRADE_LABELS_HORSE[True]),
            'loss': list(GRADE_LABELS_HORSE[False]),
            'winComment': [''] * 5,
            'lossComment': [''] * 5,
            'builtin': True,
        }
    # 电竞纯血 (方案一)
    if key == 'dianjingxuexie':
        return {
            'name': 'dianjingxuexie',
            'win': ['通天代', '真大爹', '局内人', '纯挂件', '幽灵人'],
            'loss': ['院长', '纯畜生', '胎盘成精', '拔网线吧', '九族消融'],
            'winComment': [
                '1v9顶级尽力局局长，带四头猪都能赢',
                '关键团一锤定音，这把给你磕一个',
                '按部就班按出技能，没犯病也没封神',
                '主打一个陪伴，赢了但存在感为零',
                '战后结算看ID才发现这把有你',
            ],
            'lossComment': [
                '尽力了，建议直接报警抓队友',
                '操作下饭到可以直接开席',
                '但凡脑子发育健全点都打不出这波',
                '对面给了多少？这把收了多少米',
                '建议直接剥夺碳基生物呼吸权',
            ],
            'builtin': True,
        }
    # 阴阳内涵 (方案二)
    if key == 'yinyangneihan':
        return {
            'name': 'yinyangneihan',
            'win': ['佛祖降世', '顶梁柱', 'NPC', '吸血鬼', '游离态'],
            'loss': ['人质', '假肢选手', '对面卧底', '降智光环', '人类奇迹'],
            'winComment': [
                '普度众生，直接渡化四个低能儿',
                '硬核扛大梁，没你早点投了',
                '按部就班走剧情，毫无波澜',
                '吃三路兵线打出1000输出，纯混',
                '人在召唤师峡谷，魂在平行宇宙',
            ],
            'lossComment': [
                '被绑架了你就眨眨眼',
                '怀疑是用脚后跟敲的键盘',
                '最佳第六人，功勋卓著',
                '一己之力把全队智商拉低三个档次',
                '医学上至今无法解释你怎么活到现在的',
            ],
            'builtin': True,
        }
    # 物理超度 (方案三)
    if key == 'wulichaodu':
        return {
            'name': 'wulichaodu',
            'win': ['天神下凡', '主心骨', '填空题', '包赢哥', '摄像头'],
            'loss': ['牢底坐穿', '小脑萎缩', '电竞慈禧', '移动ATM', '祖坟冒烟'],
            'winComment': [
                '砍瓜切菜，对面集体道心破碎',
                '团战发动机，指令清晰操作在线',
                '补齐了五人车队的空位而已',
                '这把赢全靠你会投胎排到好队伍',
                '全程OB录制，纯在现场看戏',
            ],
            'lossComment': [
                '坐牢一整把，受尽折磨',
                '建议赛后直接挂神经内科',
                '割地赔款，疯狂给对面送经济',
                '走到哪送到哪，随取随用',
                '操作歹毒到让祖宗蒙羞',
            ],
            'builtin': True,
        }
    # 尽搞畜蛆寄 (方案四, 单字, 无评语)
    if key == 'jinzhushuqi':
        return {
            'name': 'jinzhushuqi',
            'win': ['圣', '爹', '人', '混', '鬼'],
            'loss': ['尽', '搞', '畜', '蛆', '寄'],
            'winComment': [''] * 5,
            'lossComment': [''] * 5,
            'builtin': True,
        }
    return _builtin_team_scheme('tieba')


def _user_team_schemes() -> dict:
    """读取用户命名方案: {方案名: {win:[5], loss:[5], winComment:[5]...}}."""
    try:
        from app.common.config import cfg
        raw = cfg.get(cfg.teamRatingSchemes) or {}
        if not isinstance(raw, dict):
            raw = {}
        out = {}
        for name, s in raw.items():
            if not isinstance(s, dict):
                continue
            win = [str(x) for x in s.get('win') or []] if isinstance(
                s.get('win'), list) else []
            loss = [str(x) for x in s.get('loss') or []] if isinstance(
                s.get('loss'), list) else []
            if len(win) != 5 or len(loss) != 5:
                continue
            wc = [str(x) for x in s.get('winComment') or [''] * 5]
            lc = [str(x) for x in s.get('lossComment') or [''] * 5]
            out[str(name)] = {
                'name': str(name),
                'win': win,
                'loss': loss,
                'winComment': (wc + [''] * 5)[:5],
                'lossComment': (lc + [''] * 5)[:5],
                'builtin': False,
            }
        # 旧版单桶自定义 (style=custom) 迁移为命名方案 '自定义'
        legacy = cfg.get(cfg.teamRatingCustomLabels)
        if '自定义' not in out and isinstance(legacy, dict):
            win = [str(x) for x in legacy.get('win') or []]
            loss = [str(x) for x in legacy.get('loss') or []]
            if len(win) == 5 and len(loss) == 5:
                out['自定义'] = {
                    'name': '自定义',
                    'win': win,
                    'loss': loss,
                    'winComment': [''] * 5,
                    'lossComment': [''] * 5,
                    'builtin': False,
                }
        return out
    except Exception:
        return {}


def _team_scheme_by_key(key: str) -> Optional[dict]:
    """按方案名 (内置 key 或用户方案名) 取方案; 未命中返回 None."""
    if key in BUILTIN_TEAM_KEYS:
        return _builtin_team_scheme(key)
    if key == RANDOM_TEAM_KEY:
        return None
    return _user_team_schemes().get(key)


def team_scheme_names() -> list:
    """全部可选方案名 (内置 + 用户), 不含 '随机'."""
    return list(BUILTIN_TEAM_KEYS) + sorted(_user_team_schemes().keys())


def resolve_team_style(style: str) -> dict:
    """把用户配置的风格值解析为具体方案 dict.

    '随机' -> 从全部内置+用户方案中随机抽一套; 未命中回退默认方案.
    旧版 'custom' 值 -> '自定义' 迁移方案 (见 _user_team_schemes).
    """
    if style == 'custom':
        style = '自定义'
    if style == RANDOM_TEAM_KEY:
        pools = team_scheme_names()
        if not pools:
            pools = list(BUILTIN_TEAM_KEYS)
        style = random.choice(pools)
    scheme = _team_scheme_by_key(style)
    if scheme is None:
        scheme = _builtin_team_scheme(DEFAULT_TEAM_KEY)
    return scheme


def display_name_of(style: str) -> str:
    """风格值（内置 key / 用户方案名 / 随机）-> UI 展示名."""
    if style == RANDOM_TEAM_KEY:
        return RANDOM_TEAM_KEY
    scheme = _team_scheme_by_key(style)
    if scheme is None:
        return style
    return BUILTIN_TEAM_DISPLAY.get(style, style)


def gradeFromScore(score: float) -> int:
    """z-score 综合贡献分 -> 5 档评级 (1=最高, 5=最低).

    阈值参考 GRADE_THRESHOLDS:
      z >= 1.0   -> 1
      0.3 <= z < 1.0 -> 2
      -0.3 < z < 0.3 -> 3
      -1.0 <= z <= -0.3 -> 4
      z < -1.0  -> 5
    """
    if score >= GRADE_THRESHOLDS[0]:
        return 1
    if score >= GRADE_THRESHOLDS[1]:
        return 2
    if score > GRADE_THRESHOLDS[2]:
        return 3
    if score >= GRADE_THRESHOLDS[3]:
        return 4
    return 5


def _applyRankAdjustment(scored: list, queueId: Optional[int]) -> None:
    """排位/峡谷模式: 同档人多的档内排名细化 (原地修改 grade).

    大乱斗/海克斯保持绝对阈值 (局内方差大自然跨档, 无需细化);
    其余模式 (排位/匹配) 匹配机制压平表现方差, 5 人 z 常全落同一档,
    此时档内显著高的 top1 升一档、显著低的 bottom1 降一档,
    恢复"队内相对最好/最差"的区分度.
    """
    if queueId in ARAM_QUEUE_IDS or queueId in HEXTECH_QUEUE_IDS:
        return
    from collections import defaultdict
    groups = defaultdict(list)
    for item in scored:
        groups[item['grade']].append(item)
    for grade, members in groups.items():
        if len(members) < RANK_ADJUST_MIN_GROUP:
            continue
        members.sort(key=lambda x: x['score'], reverse=True)
        # top1 显著高于档内第二名 -> 升一档
        if members[0]['score'] - members[1]['score'] >= RANK_ADJUST_EPS:
            members[0]['grade'] = max(1, grade - 1)
        # bottom1 显著低于倒数第二名 -> 降一档
        if members[-2]['score'] - members[-1]['score'] >= RANK_ADJUST_EPS:
            members[-1]['grade'] = min(5, grade + 1)


def _team_side(scheme: dict, isWin: bool) -> tuple:
    """从方案取 (labels, comments) 并按档位索引取该档."""
    labels = scheme['win' if isWin else 'loss']
    comments = scheme['winComment' if isWin else 'lossComment']
    return labels, comments


def gradeLabel(grade: int, isWin: bool, style: str = 'tieba') -> str:
    """档位 (1-5) -> 用户可见标签文本 (按方案/胜败方).

    style 可为: 内置 key ('tieba'/'horse'/...)、用户方案名、或 '随机'.
    '随机' 在此处仅作回退 (应由调用方在每局开头 resolve 为具体方案后再传入,
    避免逐玩家重抽导致同局标签不一致).
    """
    scheme = resolve_team_style(style)
    labels, _ = _team_side(scheme, isWin)
    idx = max(1, min(5, grade)) - 1
    return labels[idx]


def gradeComment(grade: int, isWin: bool, style: str = 'tieba') -> str:
    """档位 (1-5) -> 该档评语 (悬停显示); 无评语返回 ''."""
    scheme = resolve_team_style(style)
    _, comments = _team_side(scheme, isWin)
    idx = max(1, min(5, grade)) - 1
    if not comments:
        return ''
    return str(comments[idx] or '')


class TeamRatingResult(TypedDict, total=False):
    """全队评级结果 (每个玩家一项)."""
    puuid: Optional[str]
    championId: int
    score: float           # z-score 综合贡献分
    grade: int             # 1-5 档位
    label: str             # 标签文本 (已按风格/胜败方转换)
    isWin: bool
    isCurrent: bool        # 是否当前召唤师
    evidence: list         # 各指标 z-score 证据


async def rateEntireTeam(team: list,
                         queueId: Optional[int],
                         isWin: bool,
                         style: str = 'tieba',
                         currentPuuid: Optional[str] = None) -> list:
    """给全队每个人计算 5 档评级.

    调用 `_computeTeamScores` 一次计算 z-score, 然后分级并加标签.

    Args:
        team: list[ParticipantStats], 同队玩家
        queueId: 队列 id (用于判断海克斯模式)
        isWin: 该队是否获胜
        style: 标签风格 'tieba' | 'horse'
        currentPuuid: 当前召唤师 puuid (用于标记 isCurrent)

    Returns:
        list[TeamRatingResult], 按 score 降序 (贡献最大的在前).
        队伍太小 (<2人) 时返回空列表.
    """
    scored = await _computeTeamScores(team, queueId)
    if not scored:
        return []

    # 先全量按绝对阈值定档, 再做排位模式档内排名微调 (label 需在微调后生成)
    for item in scored:
        item['grade'] = gradeFromScore(item['score'])
    _applyRankAdjustment(scored, queueId)

    rated = []
    for item in scored:
        label = gradeLabel(item['grade'], isWin, style)
        rated.append({
            'puuid': item['puuid'],
            'championId': item['championId'],
            'score': item['score'],
            'grade': item['grade'],
            'label': label,
            'isWin': isWin,
            'isCurrent': (currentPuuid is not None
                          and item['puuid'] == currentPuuid),
            'evidence': item['evidence'],
            'scheme': style,
        })

    return rated


async def diagnoseGameFromParsed(parsed: dict, currentPuuid: str,
                                  gameId: int = None,
                                  ratingStyle: str = 'tieba') -> bool:
    """从已解析的对局数据计算全队 5 档评级, 写入缓存.

    可用于:
    - 游戏结束时诊断最近一局 (main_window.__diagnoseLastGame)
    - 查看历史对局详情时实时诊断 (search_interface)

    诊断策略:
    - 胜方队: 计算 winnerRating (5档评级, 含"躺赢狗"档)
    - 败方队: 计算 loserRating (5档评级, 含"甲级战犯"/"初升东曦"档)
    - 每个玩家根据 z-score 贡献分分到 1-5 档, 贴吧风/马系风标签

    Args:
        parsed: parseGameDetailData 的返回值
        currentPuuid: 当前召唤师 puuid (用于标记 isCurrent)
        gameId: 对局 ID (优先用 parsed 中的)
        ratingStyle: 评级标签风格 'tieba' | 'horse'

    Returns:
        True 如果诊断成功并写入缓存
    """
    try:
        from app.lol.war_criminal_cache import setVerdict

        gid = gameId or parsed.get('gameId')
        if not gid:
            return False

        queueId = parsed.get('queueId')
        teams = parsed.get('teams') or {}

        # '随机' 风格: 每局只抽一次, 胜/败双方统一用同一套方案 (保证同局一致)
        if ratingStyle == RANDOM_TEAM_KEY:
            resolved = resolve_team_style(RANDOM_TEAM_KEY)
            ratingStyle = resolved['name']

        winnerRating = None  # 胜方全队评级
        loserRating = None   # 败方全队评级

        for tidStr, teamInfo in teams.items():
            summoners = (teamInfo or {}).get('summoners') or []
            if len(summoners) < 2:
                continue

            # teamInfo['win'] 可能是 'Win'/'Loss' 字符串或布尔值
            # bool('Loss') == True (非空字符串), 不能直接 bool()
            winField = teamInfo.get('win')
            if isinstance(winField, str):
                teamWin = winField.lower() in ('win', 'true')
            elif winField is None:
                teamWin = bool(summoners[0].get('win', False)) if summoners else False
            else:
                teamWin = bool(winField)

            teamStats = []
            for s in summoners:
                teamStats.append(ParticipantStats(
                    puuid=s.get('puuid'),
                    championId=s.get('championId', 0) or 0,
                    kills=s.get('kills', 0) or 0,
                    deaths=s.get('deaths', 0) or 0,
                    assists=s.get('assists', 0) or 0,
                    damage=s.get('damage', 0) or 0,
                    damageTaken=s.get('damageTaken', 0) or 0,
                    totalHeal=s.get('totalHeal', 0) or 0,
                    shieldOnTeammates=s.get('shieldOnTeammates', 0) or 0,
                    ccTime=s.get('ccTime', 0) or 0,
                    gold=s.get('gold', 0) or 0,
                    cs=s.get('cs', 0) or 0,
                    visionScore=s.get('visionScore', 0) or 0,
                    win=teamWin,
                    augmentIds=s.get('augmentIds') or [],
                    siegeDamage=(s.get('damageToTurrets', 0) or 0) +
                               (s.get('damageToObjectives', 0) or 0),
                ))

            # 全队 5 档评级 (一次计算 baseline + z-score, 然后分级)
            teamRating = await rateEntireTeam(
                teamStats, queueId, teamWin,
                style=ratingStyle,
                currentPuuid=currentPuuid,
            )

            if not teamRating:
                continue

            # 胜方: 只记录第一个 (通常只有 1 个胜方)
            if teamWin and winnerRating is None:
                winnerRating = teamRating

            # 败方: 优先当前召唤师所在的败方队; 否则取第一个败方
            if not teamWin:
                teamPuuids = {s.get('puuid') for s in summoners
                              if isinstance(s, dict)}
                isCurrentTeam = currentPuuid in teamPuuids
                if isCurrentTeam:
                    loserRating = teamRating
                elif loserRating is None:
                    loserRating = teamRating

            logger.info(
                f"TeamRating: game={gid} team={tidStr} win={teamWin} "
                f"players={len(teamRating)}",
                extra={'tag': TAG})

        setVerdict(
            gameId=gid,
            winnerRating=winnerRating,
            loserRating=loserRating,
        )
        return True

    except Exception as e:
        logger.error(f"diagnoseGameFromParsed failed: {e}",
                     extra={'tag': TAG})
        return False
