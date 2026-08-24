"""上等马赛前评价体系单元测试."""
import pytest

from app.lol import horse_rating_cache
from app.lol.horse_rating import (
    GRADE_UNKNOWN,
    HORSE_THRESHOLDS,
    TIER_ELO_MIDPOINTS,
    PlayerHorseProfile,
    grade_from_score,
    grade_label,
    rate_horse,
)


def _profile(**kw) -> PlayerHorseProfile:
    base: PlayerHorseProfile = {
        'elo': None,
        'recent10WinRate': None,
        'recent10KdaAvg': None,
        'mvpSvpCount': 0,
        'visibleTierIdx': None,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# 黄金用例
# ---------------------------------------------------------------------------

def test_golden_case_top_horse():
    """elo1478 + 白金框(idx4) + 十场80%胜率 + 4.5 KDA + 3 MVP => 上等马."""
    verdict = rate_horse(_profile(
        elo=1478,
        visibleTierIdx=4,
        recent10WinRate=0.8,
        recent10KdaAvg=4.5,
        mvpSvpCount=3,
    ))
    assert verdict['score'] is not None
    assert verdict['score'] >= HORSE_THRESHOLDS[0]
    assert verdict['grade'] == '上等马'
    assert verdict['style_labels']['horse'] == '上等马'
    assert verdict['style_labels']['formal'] == '表现优异'


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


# ---------------------------------------------------------------------------
# 缺数据降级路径
# ---------------------------------------------------------------------------

def test_missing_elo_falls_back_to_axis_b():
    """elo=None -> 只用维度 B, 权重归一, 仍给分但理由说明降级."""
    verdict = rate_horse(_profile(
        recent10WinRate=1.0,
        recent10KdaAvg=6.0,
        mvpSvpCount=5,
    ))
    assert verdict['score'] is not None
    assert 60 <= verdict['score'] <= 100
    assert verdict['grade'] == '上等马'
    assert '仅按近期表现' in verdict['reason']


def test_missing_recent_form_falls_back_to_axis_a():
    """近十场全缺 -> 只用维度 A."""
    verdict = rate_horse(_profile(elo=1900, visibleTierIdx=2))
    assert verdict['score'] is not None
    assert verdict['grade'] == '上等马'  # 大师分打银框 => 小号信号
    assert '仅按隐藏分' in verdict['reason']


def test_smurf_signal_reason():
    """隐藏分高出段位一档以上 -> 理由里出现小号提示."""
    verdict = rate_horse(_profile(
        elo=TIER_ELO_MIDPOINTS[2] + 650,   # 高出约两档
        visibleTierIdx=2,
        recent10WinRate=0.5,
    ))
    assert '2档' in verdict['reason'] or '两档' in verdict['reason']


def test_all_missing_returns_unknown():
    verdict = rate_horse(_profile())
    assert verdict['score'] is None
    assert verdict['grade'] == GRADE_UNKNOWN
    assert verdict['style_labels'] == {}
    assert verdict['reason']


def test_mvp_bonus_capped_at_15():
    low = rate_horse(_profile(recent10WinRate=0.5, mvpSvpCount=3))
    high = rate_horse(_profile(recent10WinRate=0.5, mvpSvpCount=99))
    # 3*3=9 与 15 封顶之间应有差; 99 个也只加 15
    mid = rate_horse(_profile(recent10WinRate=0.5, mvpSvpCount=5))
    assert high['score'] == mid['score']
    assert high['score'] > low['score']


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
