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
    rate_horse,
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
    """王者(8) + Ⅰ段 + 80LP => 上等马."""
    verdict = rate_horse(_profile(tierIdx=8, divisionIdx=0, lp=80))
    assert verdict['score'] is not None
    assert verdict['score'] >= HORSE_THRESHOLDS[0]
    assert verdict['grade'] == '上等马'
    assert verdict['style_labels']['horse'] == '上等马'
    assert verdict['style_labels']['formal'] == '表现优异'
    assert '段位' in verdict['reason']


def test_low_tier_is_bottom_horse():
    """黑铁(0) => 驽马."""
    verdict = rate_horse(_profile(tierIdx=0, divisionIdx=3, lp=10))
    assert verdict['score'] == 0
    assert verdict['grade'] == '驽马'


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
    (100, '上等马'),
    (80, '上等马'),      # 边界含
    (79.9, '中上等马'),
    (65, '中上等马'),
    (64.9, '中等马'),
    (50, '中等马'),
    (49.9, '下等马'),
    (35, '下等马'),
    (34.9, '驽马'),
    (0, '驽马'),
])
def test_grade_from_score_boundaries(score, expected):
    assert grade_from_score(score) == expected


def test_grade_label_styles():
    # 双风格: 同一分数不同文案
    for boundary in HORSE_THRESHOLDS:
        assert grade_label(boundary, style='horse') in (
            '上等马', '中上等马', '中等马', '下等马')
        assert grade_label(boundary, style='formal') in (
            '表现优异', '状态良好', '表现平平', '状态低迷')
    assert grade_label(90, style='horse') == '上等马'
    assert grade_label(90, style='formal') == '表现优异'
    assert grade_label(20, style='horse') == '驽马'
    assert grade_label(20, style='formal') == '数据不足建议观察'
    # Unknown 单独处理
    assert grade_label(None, style='horse') == '未知战马'
    assert grade_label(None, style='formal') == '数据不足建议观察'


def test_grade_label_custom():
    """自定义文案: 按分数档位取 'win' 侧五档标签."""
    from unittest.mock import patch

    custom = {'win': ['H1', 'H2', 'H3', 'H4', 'H5'], 'loss': ['X'] * 5}
    with patch('app.common.config.cfg.get', return_value=custom):
        assert grade_label(90, style='custom') == 'H1'
        assert grade_label(80, style='custom') == 'H1'
        assert grade_label(70, style='custom') == 'H2'
        assert grade_label(60, style='custom') == 'H3'
        assert grade_label(40, style='custom') == 'H4'
        assert grade_label(20, style='custom') == 'H5'


def test_grade_label_custom_invalid_falls_back():
    from unittest.mock import patch

    with patch('app.common.config.cfg.get', return_value=None):
        assert grade_label(90, style='custom') == '上等马'
    with patch('app.common.config.cfg.get', return_value={'win': ['a']}):
        assert grade_label(10, style='custom') == '驽马'


# ---------------------------------------------------------------------------
# 缺数据降级路径
# ---------------------------------------------------------------------------

def test_missing_all_returns_unknown():
    verdict = rate_horse(_profile())
    assert verdict['score'] is None
    assert verdict['grade'] == GRADE_UNKNOWN
    assert verdict['style_labels'] == {}
    assert verdict['reason']


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
    v = {'score': 88, 'grade': '上等马', 'style_labels': {},
         'reason': 'test'}
    horse_rating_cache.set_horse_verdict('puuid-1', v)
    assert horse_rating_cache.get_horse_verdict('puuid-1') is v

    # TTL 内仍命中
    now[0] += horse_rating_cache.HORSE_CACHE_TTL_SECONDS - 1
    assert horse_rating_cache.get_horse_verdict('puuid-1') is v

    # 超过 TTL 600s -> 过期返回 None
    now[0] += 2
    assert horse_rating_cache.get_horse_verdict('puuid-1') is None


def test_cache_unknown_puuid():
    assert horse_rating_cache.get_horse_verdict('nobody') is None
    assert horse_rating_cache.get_horse_verdict(None) is None
