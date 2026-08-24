"""上等马赛前评价体系 (5 档评级算法).

与 war_criminal.py 的局内评级互补: 这是"赛前"画像评价, 只用公开可得的
排位数据估计一个队友/对手的实力档位.

评分模型 (用户已批准, 两轴加权):
- 维度 A 隐藏分相对段位差 (40%): elo 高于可见段位中位 elo 视为小号信号,
  deviation = (elo - tierMidpoint) / 300, sigmoid 映射到 0~100
- 维度 B 近十场表现 (60%): 胜率以 0.5 基线线性归一 (占 B 内 50%)
  + KDA log(1+kda)/log(1+6) 归一 (占 B 内 30%) + mvpSvpCount*3 封顶 15 加成
- 总分 = A*0.4 + B*0.6; 仅一轴可用时该轴权重归一为 1.0; 全缺返回 Unknown

输出 5 档:
>=80 上等马 / >=65 中上等马 / >=50 中等马 / >=35 下等马 / <35 驽马
数据不足 -> Unknown

全部纯函数, 零 Qt / 网络 / IO 依赖.
"""
import math
from typing import Optional, TypedDict


class PlayerHorseProfile(TypedDict, total=False):
    """上等马评级所需的赛前玩家画像."""
    elo: Optional[int]              # 单双排隐藏分, 缺失=None
    recent10WinRate: Optional[float]  # 0~1, 缺失=None
    recent10KdaAvg: Optional[float]
    mvpSvpCount: int
    visibleTierIdx: Optional[int]   # 可见段位序数 0=铁 ... 8=王者, 缺失=None


class HorseVerdict(TypedDict, total=False):
    """上等马评级结果."""
    score: Optional[int]     # 0~100, 数据不足时 None
    grade: str               # 档位名 (含 'Unknown')
    style_labels: dict       # {'horse': ..., 'formal': ...} 双风格标签
    reason: str              # 人话解释


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 段位-隐藏分近似对照表 (铁0 铜1 银2 金3 铂4 翡翠5 钻6 大师7 王者8).
# 注意: 这是经验近似中位数, 非官方数据, 可按实际分布调整.
TIER_ELO_MIDPOINTS = (
    600,    # 0 铁
    750,    # 1 铜
    900,    # 2 银
    1050,   # 3 黄金
    1200,   # 4 铂金
    1400,   # 5 翡翠
    1600,   # 6 钻石
    1850,   # 7 大师
    2100,   # 8 王者
)

# 5 档阈值 (与 war_criminal 的 GRADE_THRESHOLDS 风格对齐)
HORSE_THRESHOLDS = (80, 65, 50, 35)  # 上等马 / 中上等马 / 中等马 / 下等马

GRADE_HORSE = ('上等马', '中上等马', '中等马', '下等马', '驽马')
GRADE_FORMAL = ('表现优异', '状态良好', '表现平平', '状态低迷',
                '数据不足建议观察')
GRADE_UNKNOWN = 'Unknown'

# 双风格标签 (对齐 war_criminal 的用户可选风格机制)
HORSE_LABELS = {
    'horse': GRADE_HORSE,
    'formal': GRADE_FORMAL,
}

# 维度归一参数
ELO_DEVIATION_SCALE = 300.0      # deviation = (elo - midpoint) / 300
SIGMOID_STEEPNESS = 2.0          # sigmoid 斜率
KDA_NORM_CEILING = 6.0           # log(1+6) 归一分母
MVP_BONUS_PER = 3                # 每个 MVP/SVP 加 3 分
MVP_BONUS_CAP = 15               # 加成封顶 15
SMURF_TIER_ELO = ELO_DEVIATION_SCALE  # 高出一整档 ≈ +300 elo

AXIS_WEIGHT_A = 0.4
AXIS_WEIGHT_B = 0.6


# ---------------------------------------------------------------------------
# 分轴计算
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def axis_a_score(elo: int, visibleTierIdx: int) -> tuple:
    """维度 A: 隐藏分相对可见段位的偏离 -> (0~100 分, 人话理由片段)."""
    idx = max(0, min(len(TIER_ELO_MIDPOINTS) - 1, int(visibleTierIdx)))
    mid = TIER_ELO_MIDPOINTS[idx]
    dev = (elo - mid) / ELO_DEVIATION_SCALE
    score = _sigmoid(SIGMOID_STEEPNESS * dev) * 100.0
    reason = ''
    if elo - mid >= SMURF_TIER_ELO:
        # 小号信号: 隐藏分高出当前段位约一档以上, 显著加分
        tiers_above = round((elo - mid) / ELO_DEVIATION_SCALE)
        reason = f'隐藏分高出段位约{tiers_above}档'
        score = min(100.0, score + min(10.0, 2.0 * tiers_above))
    elif mid - elo >= SMURF_TIER_ELO:
        reason = '隐藏分低于段位水平'
    else:
        reason = '隐藏分与段位相符'
    return score, reason


def axis_b_score(recent10WinRate: Optional[float],
                 recent10KdaAvg: Optional[float],
                 mvpSvpCount: int) -> tuple:
    """维度 B: 近十场表现 -> (0~100 分, 人话理由片段).

    B 内部权重: 胜率 50% + KDA 30% + MVP/SVP 加成 (封顶 15).
    胜率/KDA 任一缺失时其权重按比例摊给仍在的项; 加成始终叠加.
    """
    wr = recent10WinRate if recent10WinRate is not None else None
    kda = recent10KdaAvg if recent10KdaAvg is not None else None

    wr_score = None
    if wr is not None:
        # 0.5 基线线性归一: 0.5->50, 1.0->100, 0.0->0
        wr_score = max(0.0, min(100.0, 50.0 + (wr - 0.5) * 100.0))

    kda_score = None
    if kda is not None and kda >= 0:
        kda_score = math.log1p(min(kda, KDA_NORM_CEILING)) \
            / math.log1p(KDA_NORM_CEILING) * 100.0

    weighted_parts = []   # (score, weight)
    if wr_score is not None:
        weighted_parts.append((wr_score, 50.0))
    if kda_score is not None:
        weighted_parts.append((kda_score, 30.0))

    parts = []
    if weighted_parts:
        total_w = sum(w for _, w in weighted_parts)
        for s, w in weighted_parts:
            # 权重按可用比例放大到 85 (留 15 给 MVP 加成空间)
            parts.append(s * (w / total_w) * 85.0 / 100.0)

    mvp_bonus = min(float(MVP_BONUS_CAP),
                    max(0, int(mvpSvpCount or 0)) * MVP_BONUS_PER)
    score = min(100.0, sum(parts) + mvp_bonus)

    bits = []
    if wr is not None:
        bits.append('近十场胜率%.0f%%' % (wr * 100))
    if kda_score is not None:
        bits.append('场均KDA %.1f' % kda)
    return score, '，'.join(bits), mvp_bonus


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------

def rate_horse(profile: PlayerHorseProfile) -> HorseVerdict:
    """赛前画像 -> 上等马评级. 纯函数."""
    elo = profile.get('elo')
    tierIdx = profile.get('visibleTierIdx')
    wr = profile.get('recent10WinRate')
    kda = profile.get('recent10KdaAvg')
    mvp = profile.get('mvpSvpCount') or 0

    a_ok = elo is not None and tierIdx is not None
    b_ok = wr is not None or kda is not None or bool(mvp)

    reasons = []
    if not a_ok and not b_ok:
        return {
            'score': None,
            'grade': GRADE_UNKNOWN,
            'style_labels': {},
            'reason': '缺少隐藏分与近十场数据，无法评价',
        }

    if a_ok and b_ok:
        assert elo is not None and tierIdx is not None
        a_score, a_reason = axis_a_score(int(elo), int(tierIdx))
        b_score, b_reason, bonus = axis_b_score(wr, kda, mvp)
        score = a_score * AXIS_WEIGHT_A + b_score * AXIS_WEIGHT_B
        if bonus > 0:
            b_reason += f'（MVP加成+{bonus:g}）'
        reasons = [a_reason, b_reason]
    elif a_ok:
        assert elo is not None and tierIdx is not None
        a_score, a_reason = axis_a_score(int(elo), int(tierIdx))
        score = a_score
        reasons = [a_reason, '缺少近十场数据，仅按隐藏分评估']
    else:
        b_score, b_reason, bonus = axis_b_score(wr, kda, mvp)
        score = b_score
        if bonus > 0:
            b_reason += f'（MVP加成+{bonus:g}）'
        reasons = [b_reason, '缺少隐藏分数据，仅按近期表现评估']

    final = int(round(score))
    grade = grade_from_score(final)
    return {
        'score': final,
        'grade': grade,
        'style_labels': {
            'horse': grade_label(final, style='horse'),
            'formal': grade_label(final, style='formal'),
        },
        'reason': '；'.join(reasons),
    }


def grade_from_score(score: float) -> str:
    """0~100 分 -> 5 档档位名 (Unknown 只由 rate_horse 处理)."""
    if score >= HORSE_THRESHOLDS[0]:
        return GRADE_HORSE[0]
    if score >= HORSE_THRESHOLDS[1]:
        return GRADE_HORSE[1]
    if score >= HORSE_THRESHOLDS[2]:
        return GRADE_HORSE[2]
    if score >= HORSE_THRESHOLDS[3]:
        return GRADE_HORSE[3]
    return GRADE_HORSE[4]


def grade_label(score: Optional[float], style: str = 'horse') -> str:
    """分数 -> 用户可见标签文本.

    Args:
        score: 0~100 分; None 表示数据不足.
        style: 'horse' (马系风) | 'formal' (正式风)
    """
    if score is None:
        return '未知战马' if style == 'horse' else '数据不足建议观察'
    labels = HORSE_LABELS.get(style, GRADE_HORSE)
    grade = grade_from_score(score)
    idx = GRADE_HORSE.index(grade)
    return labels[idx]
