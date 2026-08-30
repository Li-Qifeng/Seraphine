"""上等马赛前评价体系 (5 档评级算法).

与 war_criminal.py 的局内评级互补: 这是"赛前"画像评价, 只用 LCU 本地即可
取得的可见排位数据估计一个队友/对手的实力档位, 不依赖任何第三方数据源.

评分模型 (单轴, 基于可见排位):
- 段位基准: tierIdx/8*100 (黑铁0 ~ 王者8)
- division 细分: 同段位内 I 段最高 (3-divisionIdx)*3 分加成
- LP 红利: 段位分 80 以上按 lp 微调封顶 +4
- 小号近似信号: 钻石+ 且 Ⅰ段 且 lp>=75 视为接近晋级, 提示徽章

输出 5 档:
>=80 上等马 / >=65 中上等马 / >=50 中等马 / >=35 下等马 / <35 驽马
数据不足 -> Unknown

全部纯函数, 零 Qt / 网络 / IO 依赖.
"""
from typing import Optional, TypedDict


class PlayerHorseProfile(TypedDict, total=False):
    """上等马评级所需的赛前玩家画像 (全来自 LCU 可见排位)."""
    tierIdx: Optional[int]        # 可见段位序数 0=铁 ... 8=王者, 缺失=None
    divisionIdx: Optional[int]    # 段内序数 0=Ⅰ ... 3=Ⅳ; Unranked 无
    lp: Optional[int]             # 当前胜点 0~99/100, 缺失=None


class HorseVerdict(TypedDict, total=False):
    """上等马评级结果."""
    score: Optional[int]     # 0~100, 数据不足时 None
    grade: str               # 档位名 (含 'Unknown')
    style_labels: dict       # {'horse': ..., 'formal': ...} 双风格标签
    reason: str              # 人话解释


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

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

# 单轴归一参数
TIER_MAX = 8                       # 王者 idx
DIVISION_BONUS_PER = 3             # 段内 Ⅰ~Ⅳ 每前进一级 +3 分
LP_BONUS_SCALE = 4.0               # 高位段 (>=80) 时 lp 可加成分数封顶
LP_BONUS_THRESHOLD = 80            # 段位分达到该值才启用 LP 微调
PROMOTION_LP = 75                  # 钻石+ Ⅰ段 该 LP 视为接近晋级


# ---------------------------------------------------------------------------
# 分轴计算
# ---------------------------------------------------------------------------

def axis_visible_score(tierIdx: Optional[int],
                       divisionIdx: Optional[int],
                       lp: Optional[int]) -> tuple:
    """基于 LCU 可见排位 -> (0~100 分, 人话理由片段).

    段位基准 0~100; 同段位 Ⅰ 段较 Ⅳ 段高; 高段位下按 LP 高位微调.
    """
    if tierIdx is None:
        return None, '缺少可见段位，无法评价'
    idx = max(0, min(TIER_MAX, int(tierIdx)))
    score = idx / TIER_MAX * 100.0

    if divisionIdx is not None:
        score += (3 - max(0, min(3, int(divisionIdx)))) * DIVISION_BONUS_PER

    bits = ['段位%s' % _tier_name(idx)]
    if lp is not None and score >= LP_BONUS_THRESHOLD:
        bonus = min(LP_BONUS_SCALE,
                    max(0, int(lp)) / 100.0 * LP_BONUS_SCALE)
        score = min(100.0, score + bonus)
        bits.append('胜点%d' % int(lp))

    promotion = (idx >= 6 and (divisionIdx if divisionIdx is not None else 9) == 0
                 and lp is not None and lp >= PROMOTION_LP)
    if promotion:
        bits.append('接近晋级')

    return score, '，'.join(bits)


def _tier_name(idx: int) -> str:
    names = ('黑铁', '黄铜', '白银', '黄金', '铂金',
             '翡翠', '钻石', '大师', '王者')
    return names[idx]


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------

def rate_horse(profile: PlayerHorseProfile) -> HorseVerdict:
    """赛前画像 -> 上等马评级. 纯函数 (仅 LCU 可见排位)."""
    tierIdx = profile.get('tierIdx')
    divisionIdx = profile.get('divisionIdx')
    lp = profile.get('lp')

    score, reason = axis_visible_score(tierIdx, divisionIdx, lp)
    if score is None:
        return {
            'score': None,
            'grade': GRADE_UNKNOWN,
            'style_labels': {},
            'reason': reason,
        }

    final = int(round(score))
    grade = grade_from_score(final)
    return {
        'score': final,
        'grade': grade,
        'style_labels': {
            'horse': grade_label(final, style='horse'),
            'formal': grade_label(final, style='formal'),
        },
        'reason': reason,
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


def _custom_horse_labels() -> Optional[list]:
    """读取用户自定义马评分文案 (style='custom'); 无效/未填时返回 None.

    马评分按分数分档 (无胜败概念), 自定义文案使用 'win' 侧 5 个标签.
    """
    try:
        from app.common.config import cfg
        raw = cfg.get(cfg.horseRatingCustomLabels) or {}
        labels = raw.get('win') or []
        if isinstance(labels, list) and len(labels) == 5:
            return [str(x) for x in labels]
    except Exception:
        pass
    return None


def grade_label(score: Optional[float], style: str = 'horse') -> str:
    """分数 -> 用户可见标签文本.

    Args:
        score: 0~100 分; None 表示数据不足.
        style: 'horse' (马系风) | 'formal' (正式风) | 'custom' (用户自定义)
    """
    if score is None:
        return '未知战马' if style == 'horse' else '数据不足建议观察'
    if style == 'custom':
        labels = _custom_horse_labels()
        if labels is None:
            labels = HORSE_LABELS.get('horse', GRADE_HORSE)
        grade = grade_from_score(score)
        idx = GRADE_HORSE.index(grade)
        return labels[idx]
    labels = HORSE_LABELS.get(style, GRADE_HORSE)
    grade = grade_from_score(score)
    idx = GRADE_HORSE.index(grade)
    return labels[idx]
