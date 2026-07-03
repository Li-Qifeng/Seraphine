"""Shared UI constants and utilities for team rating (war criminal) feature."""

GRADE_ACCENT = {
    1: '#FFD700',
    2: '#00E676',
    3: '#90A4AE',
    4: '#FF9100',
    5: '#FF1744',
}

# (light_fg_current, light_bg_current, light_border_current,
#  light_fg_other,   light_bg_other,   light_border_other,
#  dark_fg_current,  dark_bg_current,  dark_border_current,
#  dark_fg_other,    dark_bg_other,    dark_border_other)
GRADE_BADGE_COLORS = {
    1: ('#ffffff', '#FFB300', '#FF8F00',
        '#FF8F00', 'rgba(255,179,0,0.12)', '#FFB300',
        '#ffffff', '#FFB300', '#FFD54F',
        '#FFD54F', 'rgba(255,213,79,0.16)', '#FFD54F'),
    2: ('#ffffff', '#00C853', '#009624',
        '#009624', 'rgba(0,200,83,0.12)', '#00E676',
        '#ffffff', '#00C853', '#69F0AE',
        '#69F0AE', 'rgba(105,240,174,0.16)', '#69F0AE'),
    3: ('#ffffff', '#607D8B', '#455A64',
        '#455A64', 'rgba(96,125,139,0.10)', '#90A4AE',
        '#ffffff', '#607D8B', '#B0BEC5',
        '#B0BEC5', 'rgba(176,190,197,0.14)', '#B0BEC5'),
    4: ('#ffffff', '#FF6D00', '#E65100',
        '#E65100', 'rgba(255,109,0,0.12)', '#FF9100',
        '#ffffff', '#FF6D00', '#FFB74D',
        '#FFB74D', 'rgba(255,183,116,0.16)', '#FFB74D'),
    5: ('#ffffff', '#D50000', '#B71C1C',
        '#B71C1C', 'rgba(213,0,0,0.10)', '#FF1744',
        '#ffffff', '#D50000', '#EF9A9A',
        '#EF9A9A', 'rgba(239,154,154,0.14)', '#EF9A9A'),
}

METRIC_NAMES = {
    'damage': '伤害', 'deaths': '死亡', 'gold': '经济', 'kda': 'KDA',
    'damage_taken': '承伤', 'shield_heal': '护盾/治疗', 'cc': '控制',
    'kill_participation': '参团率', 'damage_efficiency': '伤害转化率', 'vision': '视野',
}


def severity_comment(z: float) -> str:
    if z >= 1.5:
        return '遥遥领先'
    if z >= 0.8:
        return '突出'
    if z <= -1.5:
        return '垫底'
    if z <= -0.8:
        return '偏低'
    return '正常'


def severity_level(z: float) -> str:
    if z >= 1.5:
        return 'high_pos'
    if z >= 0.8:
        return 'pos'
    if z <= -1.5:
        return 'high_neg'
    if z <= -0.8:
        return 'neg'
    return 'normal'


def format_metric_value(metric: str, val: float) -> str:
    if metric in ('kill_participation',):
        return f"{val:.0%}"
    if metric in ('kda', 'damage_efficiency', 'vision'):
        return f"{val:.2f}"
    return f"{int(val):,}"
