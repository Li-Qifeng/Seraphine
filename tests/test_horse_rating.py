"""上等马赛前评价体系单元测试."""
import pytest

from app.lol import horse_rating_cache
from app.lol.horse_rating import (
    GRADE_UNKNOWN,
    HORSE_THRESHOLDS,
    PlayerHorseProfile,
    axis_visible_score,
    grade_from_score,
    grade_label,
    horse_scheme_names,
    rate_horse,
    resolve_horse_style,
    _kda_score,
)


def _profile(**kw) -> PlayerHorseProfile:
    base: PlayerHorseProfile = {
        'tierIdx': None,
        'divisionIdx': None,
        'lp': None,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# 黄金用例
# ---------------------------------------------------------------------------

def test_golden_case_top_horse():
    """王者(8) + Ⅰ段 + 80LP => 通天代."""
    verdict = rate_horse(_profile(tierIdx=8, divisionIdx=0, lp=80))
    assert verdict['score'] is not None
    assert verdict['score'] >= HORSE_THRESHOLDS[0]
    assert verdict['grade'] == '通天代'
    assert '段位' in verdict['reason']


def test_low_tier_is_bottom_horse():
    """黑铁(0) => 牛马."""
    verdict = rate_horse(_profile(tierIdx=0, divisionIdx=3, lp=10))
    assert verdict['score'] == 0
    assert verdict['grade'] == '牛马'


def test_axis_visible_score_monotonic():
    """段位越高分越高; 同段位Ⅰ>Ⅳ; LP 高分微调."""
    low = axis_visible_score(1, None, None)[0]
    high = axis_visible_score(8, None, None)[0]
    assert high > low
    div0 = axis_visible_score(5, 0, None)[0]
    div3 = axis_visible_score(5, 3, None)[0]
    assert div0 > div3
    lp_high = axis_visible_score(7, 0, 90)[0]
    lp_low = axis_visible_score(7, 0, 10)[0]
    assert lp_high > lp_low


def test_axis_visible_score_missing_tier_unknown():
    score, reason = axis_visible_score(None, None, None)
    assert score is None
    assert reason


def test_axis_visible_score_promotion_hint_diamond_promotion():
    """钻石 Ⅰ段 80LP -> 接近晋级提示."""
    score, reason = axis_visible_score(6, 0, 80)
    assert score is not None
    assert '接近晋级' in reason
    # 非 Ⅰ段不提示
    _, reason2 = axis_visible_score(6, 1, 80)
    assert '接近晋级' not in reason2


# ---------------------------------------------------------------------------
# 档位边界 (参数化, 直接测分级函数)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('score,expected', [
    (100, '通天代'),
    (85, '通天代'),      # 边界含
    (84.9, '小代'),
    (75, '小代'),
    (74.9, '上等马'),
    (60, '上等马'),
    (59.9, '中等马'),
    (45, '中等马'),
    (44.9, '下等马'),
    (30, '下等马'),
    (29.9, '牛马'),
    (0, '牛马'),
])
def test_grade_from_score_boundaries(score, expected):
    assert grade_from_score(score) == expected


def test_grade_label_styles():
    # 内置纯牛马: 同一分数边界 -> 内置 6 档标签之一
    for boundary in HORSE_THRESHOLDS:
        assert grade_label(boundary, style='horse') in (
            '通天代', '小代', '上等马', '中等马', '下等马', '牛马')
    assert grade_label(90, style='horse') == '通天代'
    assert grade_label(20, style='horse') == '牛马'
    # Unknown 单独处理
    assert grade_label(None, style='horse') == '未知战绩'


def test_grade_label_user_scheme():
    """用户命名方案: 按分数档位取六档标签."""
    from unittest.mock import patch

    custom = {'我的马': ['H1', 'H2', 'H3', 'H4', 'H5', 'H6']}
    with patch('app.lol.horse_rating._user_horse_schemes', return_value=custom):
        assert grade_label(90, style='我的马') == 'H1'
        assert grade_label(80, style='我的马') == 'H2'
        assert grade_label(70, style='我的马') == 'H3'
        assert grade_label(50, style='我的马') == 'H4'
        assert grade_label(40, style='我的马') == 'H5'
        assert grade_label(20, style='我的马') == 'H6'


def test_grade_label_unknown_style_falls_back():
    """未知方案名/随机 -> 回退内置默认 (调用方应先 resolve 随机)."""
    assert grade_label(90, style='不存在的方案') == '通天代'
    assert grade_label(90, style='随机') == '通天代'
    assert grade_label(10, style='随机') == '牛马'


def test_resolve_horse_style_random_picks_from_pool():
    for _ in range(50):
        assert resolve_horse_style('随机') in horse_scheme_names()
    assert 'horse' in horse_scheme_names()


def test_resolve_horse_style_unknown_falls_back():
    assert resolve_horse_style('不存在的方案') == 'horse'
    assert resolve_horse_style('horse') == 'horse'


def test_legacy_custom_migrates_to_named_scheme():
    """旧版单桶自定义马评分自动迁移为命名方案 '自定义'."""
    from unittest.mock import patch
    from app.common.config import cfg
    from app.lol.horse_rating import _user_horse_schemes
    legacy = {'win': ['H1', 'H2', 'H3', 'H4', 'H5', 'H6']}

    def fake_get(item):
        if item is cfg.horseRatingCustomLabels:
            return legacy
        return {}

    with patch('app.common.config.cfg.get', side_effect=fake_get):
        schemes = _user_horse_schemes()
        assert '自定义' in schemes
        assert schemes['自定义'] == legacy['win']
        assert grade_label(90, style='自定义') == 'H1'
        assert grade_label(20, style='自定义') == 'H6'


# ---------------------------------------------------------------------------
# 缺数据降级路径
# ---------------------------------------------------------------------------

def test_missing_all_returns_unknown():
    verdict = rate_horse(_profile())
    assert verdict['score'] is None
    assert verdict['grade'] == GRADE_UNKNOWN
    assert verdict['reason']


# ---------------------------------------------------------------------------
# 三维评分: 段位 + 胜率 + KDA
# ---------------------------------------------------------------------------

def test_winrate_and_kda_present_blend():
    """同段位下, 近期战绩更好者综合分更高 (胜率/KDA 权重参与)."""
    base = _profile(tierIdx=4, divisionIdx=0, lp=50)
    low = rate_horse(dict(base, winrate=0.40, kda=2.0))
    high = rate_horse(dict(base, winrate=0.70, kda=5.0))
    assert low['score'] is not None and high['score'] is not None
    assert high['score'] > low['score']
    assert '胜率' in high['reason'] and 'KDA' in high['reason']


def test_missing_winrate_kda_falls_back_to_pure_tier():
    """缺失战绩时退化为纯段位分, 与旧版一致."""
    no = rate_horse(_profile(tierIdx=6, divisionIdx=0, lp=50))
    explicit_none = rate_horse(
        dict(_profile(tierIdx=6, divisionIdx=0, lp=50),
             winrate=None, kda=None))
    assert no['score'] == explicit_none['score']


# ---------------------------------------------------------------------------
# 大乱斗/海克斯模式: 只看 KDA, 不参考段位
# ---------------------------------------------------------------------------

def test_kda_only_mode_ignores_tier():
    """use_tier=False 时王者段位不参与评分, 只由 KDA 决定."""
    high_tier_low_kda = rate_horse(
        _profile(tierIdx=8, divisionIdx=0, lp=90, kda=1.0), use_tier=False)
    assert high_tier_low_kda['score'] is not None
    assert high_tier_low_kda['score'] == int(_kda_score(1.0))
    assert high_tier_low_kda['score'] < HORSE_THRESHOLDS[4]  # 只能到牛马
    assert 'KDA' in high_tier_low_kda['reason']
    assert '段位' not in high_tier_low_kda['reason']

    low_tier_high_kda = rate_horse(
        _profile(tierIdx=0, divisionIdx=3, lp=0, kda=5.5), use_tier=False)
    assert low_tier_high_kda['score'] == int(_kda_score(5.5))
    assert low_tier_high_kda['score'] >= HORSE_THRESHOLDS[1]  # 黑铁也能小代


def test_kda_only_mode_missing_kda_unknown():
    """无近期战绩时 Unknown, 即使有可见段位."""
    verdict = rate_horse(
        _profile(tierIdx=8, divisionIdx=0, lp=90), use_tier=False)
    assert verdict['score'] is None
    assert verdict['grade'] == GRADE_UNKNOWN


def test_tier_mode_unchanged_without_kda():
    """默认 use_tier=True 保持旧行为: 无战绩纯段位分."""
    v = rate_horse(_profile(tierIdx=6, divisionIdx=0, lp=50))
    assert v['score'] is not None
    assert '段位' in v['reason']


# ---------------------------------------------------------------------------
# 缓存 TTL
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_cache():
    horse_rating_cache.clear()
    yield
    horse_rating_cache.clear()


def test_cache_set_get(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(horse_rating_cache.time, 'time',
                        lambda: now[0])
    v = {'score': 88, 'grade': '上等马', 'reason': 'test'}
    horse_rating_cache.set_horse_verdict('puuid-1', v)
    # 深拷贝返回: 值相等但非同一对象 (调用方打批次字段不污染缓存)
    got = horse_rating_cache.get_horse_verdict('puuid-1')
    assert got == v and got is not v
    got['scheme'] = 'polluted'
    assert horse_rating_cache.get_horse_verdict('puuid-1') == v

    # TTL 内仍命中
    now[0] += horse_rating_cache.HORSE_CACHE_TTL_SECONDS - 1
    assert horse_rating_cache.get_horse_verdict('puuid-1') == v

    # 超过 TTL 600s -> 过期返回 None
    now[0] += 2
    assert horse_rating_cache.get_horse_verdict('puuid-1') is None


def test_cache_unknown_puuid():
    assert horse_rating_cache.get_horse_verdict('nobody') is None
    assert horse_rating_cache.get_horse_verdict(None) is None
