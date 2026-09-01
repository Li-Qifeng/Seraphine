"""上等马赛前评价体系 (6 档评级算法).

与 war_criminal.py 的局内评级互补: 这是"赛前"画像评价, 只用 LCU 本地即可
取得的可见排位数据估计一个队友/对手的实力档位, 不依赖任何第三方数据源.

评分模型 (三维, 基于可见排位 + 近期战绩):
- 段位轴: tierIdx/8*100 (黑铁0 ~ 王者8) + division 细分 + LP 红利 (见 axis_visible_score)
- 胜率轴: winrate*100 (50%=50 分, 封顶 100)
- KDA 轴: kda*16 (KDA 3.0=48, 5.0=80, 6.25=100, 封顶 100)
- 加权: 段位*0.5 + 胜率*0.3 + KDA*0.2; 缺失的轴自动降权, 缺全部战绩时退化为纯段位分 (与旧版一致)

输出 6 档 (0-100 重标, 对齐 hh-lol-prophet):
>=85 通天代 / >=75 小代 / >=60 上等马 / >=45 中等马 / >=30 下等马 / <30 牛马
数据不足 -> Unknown

全部纯函数, 零 Qt / 网络 / IO 依赖.
"""
from typing import Optional, TypedDict


class PlayerHorseProfile(TypedDict, total=False):
    """上等马评级所需的赛前玩家画像 (全来自 LCU 可见排位 + 近期战绩)."""
    tierIdx: Optional[int]        # 可见段位序数 0=铁 ... 8=王者, 缺失=None
    divisionIdx: Optional[int]    # 段内序数 0=Ⅰ ... 3=Ⅳ; Unranked 无
    lp: Optional[int]             # 当前胜点 0~99/100, 缺失=None
    winrate: Optional[float]      # 近期胜率 0~1, 缺失=None
    kda: Optional[float]          # 近期 KDA 比值 (k+a)/d, 缺失=None


class HorseVerdict(TypedDict, total=False):
    """上等马评级结果."""
    score: Optional[int]     # 0~100, 数据不足时 None
    grade: str               # 档位名 (含 'Unknown')
    scheme: Optional[str]    # 本局实际使用的方案 key (随机风格时为抽中的方案)
    reason: str              # 人话解释


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 6 档阈值 (0-100 重标, 对齐 hh-lol-prophet 的档位语序)
HORSE_THRESHOLDS = (85, 75, 60, 45, 30)  # 通天代/小代/上等马/中等马/下等马/牛马

GRADE_HORSE = ('通天代', '小代', '上等马', '中等马', '下等马', '牛马')
GRADE_UNKNOWN = 'Unknown'

# ===========================================================================
# 马评分风格方案 (模板): 内置(只读, 代码常量) + 用户命名方案(存 config)
# 马评分按分数分档 (无胜败概念), 方案 = 6 个标签的列表; 无括号评语(走 BP 聊天).
# 方案以 "key" 存储; 内置 key='horse'(展示名 '纯牛马'), 用户方案以方案名为 key.
# ===========================================================================

HORSE_RANDOM_KEY = '随机'
HORSE_BUILTIN_KEY = 'horse'
# 内置方案 key -> 中文展示名 (风格下拉显示用)
HORSE_BUILTIN_DISPLAY = {'horse': '纯牛马'}
HORSE_DEFAULT_KEY = 'horse'


def _user_horse_schemes() -> dict:
    """读取用户命名马评分方案: {方案名: {win: [6 标签]}}."""
    try:
        from app.common.config import cfg
        raw = cfg.get(cfg.horseRatingSchemes) or {}
        if not isinstance(raw, dict):
            raw = {}
        out = {}
        for name, s in raw.items():
            if not isinstance(s, dict):
                continue
            labels = [str(x) for x in s.get('win') or []] if isinstance(
                s.get('win'), list) else []
            if len(labels) != 6:
                continue
            out[str(name)] = list(labels)
        # 旧版单桶自定义马评分 (style=custom) 迁移为命名方案 '自定义'
        legacy = cfg.get(cfg.horseRatingCustomLabels)
        if '自定义' not in out and isinstance(legacy, dict):
            labels = [str(x) for x in legacy.get('win') or []]
            if len(labels) == 6:
                out['自定义'] = list(labels)
        return out
    except Exception:
        return {}


def _horse_scheme(key: str) -> list:
    """按方案 key (内置 'horse' 或用户方案名) 返回 6 标签列表."""
    if key == HORSE_BUILTIN_KEY:
        return list(GRADE_HORSE)
    scheme = _user_horse_schemes().get(key)
    if scheme:
        return list(scheme)
    return list(GRADE_HORSE)


def horse_scheme_names() -> list:
    """全部可选方案名 (内置 + 用户), 不含 '随机'."""
    return [HORSE_BUILTIN_KEY] + sorted(_user_horse_schemes().keys())


def resolve_horse_style(style: str) -> str:
    """把用户配置的风格值解析为具体方案 key.

    '随机' -> 从全部内置+用户方案中随机抽一套; 未命中回退默认.
    旧版 'custom' 值 -> '自定义' 迁移方案 (见 _user_horse_schemes).
    """
    if style == 'custom':
        style = '自定义'
    if style == HORSE_RANDOM_KEY:
        pools = horse_scheme_names()
        if not pools:
            pools = [HORSE_BUILTIN_KEY]
        import random
        return random.choice(pools)
    if style in horse_scheme_names():
        return style
    return HORSE_DEFAULT_KEY


def horse_display_name(style: str) -> str:
    """风格值 (内置 key / 用户方案名 / 随机) -> UI 展示名."""
    if style == HORSE_RANDOM_KEY:
        return HORSE_RANDOM_KEY
    if style in HORSE_BUILTIN_DISPLAY:
        return HORSE_BUILTIN_DISPLAY[style]
    return style

# 单轴归一参数
TIER_MAX = 8                       # 王者 idx
DIVISION_BONUS_PER = 3             # 段内 Ⅰ~Ⅳ 每前进一级 +3 分
LP_BONUS_SCALE = 4.0               # 高位段 (>=80) 时 lp 可加成分数封顶
LP_BONUS_THRESHOLD = 80            # 段位分达到该值才启用 LP 微调
PROMOTION_LP = 75                  # 钻石+ Ⅰ段 该 LP 视为接近晋级

# 三维权重 (段位 : 胜率 : KDA); 缺失的轴在 rate_horse 内自动降权
WEIGHT_TIER = 0.5
WEIGHT_WINRATE = 0.3
WEIGHT_KDA = 0.2
# KDA -> 0~100 的斜率 (KDA 5.0 = 80 分)
KDA_SCORE_SLOPE = 16.0


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

def _winrate_score(winrate: Optional[float]) -> float:
    """胜率 0~1 -> 0~100 (50%=50 分, 封顶)."""
    if winrate is None:
        return 0.0
    return max(0.0, min(100.0, winrate * 100.0))


def _kda_score(kda: Optional[float]) -> float:
    """KDA 比值 -> 0~100 (5.0=80 分, 封顶)."""
    if kda is None:
        return 0.0
    return max(0.0, min(100.0, kda * KDA_SCORE_SLOPE))


def rate_horse(profile: PlayerHorseProfile, use_tier: bool = True) -> HorseVerdict:
    """赛前画像 -> 上等马评级. 纯函数 (仅 LCU 可见排位 + 近期战绩).

    Args:
        profile: 玩家画像 (段位 + 可选近期战绩).
        use_tier: 是否参考段位轴. 大乱斗/海克斯大乱斗 (450/2400) 传 False,
            只看近期 KDA (不参考段位); 排位/匹配传 True (默认, 段位+战绩三维).
    """
    tierIdx = profile.get('tierIdx')
    divisionIdx = profile.get('divisionIdx')
    lp = profile.get('lp')
    winrate = profile.get('winrate')
    kda = profile.get('kda')

    if not use_tier:
        # 大乱斗/海克斯: 只看近期 KDA, 不参考段位
        if kda is None:
            return {
                'score': None,
                'grade': GRADE_UNKNOWN,
                'reason': '缺少近期战绩，无法评价',
            }
        score = round(_kda_score(kda))
        return {
            'score': score,
            'grade': grade_from_score(score),
            'reason': '近局KDA%.1f' % kda,
        }

    tier_score, tier_reason = axis_visible_score(tierIdx, divisionIdx, lp)
    if tier_score is None:
        return {
            'score': None,
            'grade': GRADE_UNKNOWN,
            'reason': tier_reason,
        }

    # 加权平均可用轴: 缺战绩时退化为纯段位分, 保证单调且与旧版兼容
    weighted = tier_score * WEIGHT_TIER
    total_w = WEIGHT_TIER
    bits = [tier_reason]
    if winrate is not None:
        weighted += _winrate_score(winrate) * WEIGHT_WINRATE
        total_w += WEIGHT_WINRATE
        bits.append('胜率%.0f%%' % (winrate * 100.0))
    if kda is not None:
        weighted += _kda_score(kda) * WEIGHT_KDA
        total_w += WEIGHT_KDA
        bits.append('KDA%.1f' % kda)

    score = weighted / total_w
    final = int(round(score))
    grade = grade_from_score(final)
    return {
        'score': final,
        'grade': grade,
        'reason': '，'.join(bits),
    }


def grade_from_score(score: float) -> str:
    """0~100 分 -> 6 档档位名 (Unknown 只由 rate_horse 处理)."""
    if score >= HORSE_THRESHOLDS[0]:
        return GRADE_HORSE[0]
    if score >= HORSE_THRESHOLDS[1]:
        return GRADE_HORSE[1]
    if score >= HORSE_THRESHOLDS[2]:
        return GRADE_HORSE[2]
    if score >= HORSE_THRESHOLDS[3]:
        return GRADE_HORSE[3]
    if score >= HORSE_THRESHOLDS[4]:
        return GRADE_HORSE[4]
    return GRADE_HORSE[5]


def grade_label(score: Optional[float], style: str = 'horse') -> str:
    """分数 -> 用户可见标签文本.

    Args:
        score: 0~100 分; None 表示数据不足.
        style: 方案 key ('horse'='纯牛马' | 用户方案名). '随机' 在此处仅
               作回退 (应由调用方在每局开头 resolve 为具体方案后再传入,
               避免逐玩家重抽导致同局不一致).

    Returns:
        对应 6 档标签文本; score 为 None 时返回 '未知战绩'.
    """
    if score is None:
        return '未知战绩'
    if style == HORSE_RANDOM_KEY:
        style = HORSE_DEFAULT_KEY
    labels = _horse_scheme(style)
    grade = grade_from_score(score)
    idx = GRADE_HORSE.index(grade)
    return labels[idx]
