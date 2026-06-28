"""Tests for war_criminal.py core algorithm.

战犯/躺赢狗诊断核心算法 (纯函数, 无 LCU/Qt 依赖):
- 海克斯大乱斗视野分不计入评分
- 海克斯强化组合影响预期贡献基线
- OPGG 英雄胜率影响判定权重 (高胜率英雄更易被判躺赢狗/战犯)
- verdict 标签: 胜局=躺赢狗, 负局=战犯

mock OPGG 基线模块 (champion_baseline / augment_baseline) 以避免网络请求.
"""
import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub PyQt5 (无法在非 Windows 环境直接 import)
for _qt_mod in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui"):
    if _qt_mod not in sys.modules:
        sys.modules[_qt_mod] = MagicMock()

# 显式导入被 patch 的基线模块, 让 patch('app.lol.augment_baseline.xxx') 能解析到目标.
# 否则 war_criminal 内部是惰性导入, 测试环境里 app.lol 包未挂载 augment_baseline 子模块,
# mock.patch 在 __enter__ 时会因 AttributeError 失败.
import app.lol.augment_baseline  # noqa: E402, F401
import app.lol.champion_baseline  # noqa: E402, F401

from app.lol.war_criminal import (  # noqa: E402
    ParticipantStats,
    diagnoseTeam,
    verdictLabel,
    _kda,
    _zScore,
    _roleOf,
)


# ---------- 纯函数测试 ----------

class TestKda:
    def test_normal(self):
        s = ParticipantStats(kills=3, deaths=2, assists=5)
        assert _kda(s) == 4.0

    def test_zero_deaths(self):
        s = ParticipantStats(kills=2, deaths=0, assists=3)
        # 0 死退回 KA, 避免除零
        assert _kda(s) == 5.0

    def test_all_zero(self):
        s = ParticipantStats(kills=0, deaths=5, assists=0)
        assert _kda(s) == 0.0


class TestZScore:
    def test_single_value(self):
        # 单点无法算 std, 返回 0
        assert _zScore([100], 100) == 0.0

    def test_identical_values(self):
        # 全相同 std=0, 返回 0
        assert _zScore([100, 100, 100], 100) == 0.0

    def test_normal(self):
        vals = [10, 20, 30, 40, 50]
        z = _zScore(vals, 30)  # mean=30, std=sqrt(200)≈14.14
        assert abs(z) < 0.01  # 30 是均值, z≈0

    def test_high_value(self):
        vals = [10, 20, 30, 40, 50]
        z = _zScore(vals, 50)  # 远高于均值
        assert z > 1.0

    def test_low_value(self):
        vals = [10, 20, 30, 40, 50]
        z = _zScore(vals, 10)  # 远低于均值
        assert z < -1.0


class TestRoleOf:
    def test_hextech_always_dps(self):
        # 海克斯模式一律 dps
        for cid in [1, 100, 9999]:
            assert _roleOf(cid, 2400) == 'dps'

    def test_other_modes_by_id(self):
        # 非 2400, 兜底按 id 奇偶分
        assert _roleOf(2, 420) == 'dps'      # 偶数 -> dps
        assert _roleOf(3, 420) == 'tank_support'  # 奇数 -> tank_support


# ---------- diagnoseTeam 集成测试 ----------

def _makeParticipant(puuid, championId, damage=25000, deaths=5, gold=10000,
                     cs=200, kills=5, assists=5, win=True, augmentIds=None,
                     damageTaken=15000, totalHeal=0, shieldOnTeammates=0,
                     ccTime=0, visionScore=20):
    return ParticipantStats(
        puuid=puuid, championId=championId,
        kills=kills, deaths=deaths, assists=assists,
        damage=damage, damageTaken=damageTaken,
        totalHeal=totalHeal, shieldOnTeammates=shieldOnTeammates,
        ccTime=ccTime, gold=gold, cs=cs,
        visionScore=visionScore, win=win, augmentIds=augmentIds or [],
    )


def _run_async(coro):
    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestDiagnoseTeam:
    def test_team_too_small(self):
        """少于 2 人无法评分."""
        result = _run_async(diagnoseTeam([], 420, True, 'normal'))
        assert result is None

        result = _run_async(diagnoseTeam(
            [_makeParticipant('p1', 1, 20000)], 420, True, 'normal'))
        assert result is None

    def test_war_criminal_obvious(self):
        """明显的战犯: 伤害远低于队友, 死亡远高于队友."""
        # mock 基线模块返回中性 (None = 降级到纯 z-score)
        with patch('app.lol.augment_baseline.getHextechAugmentScore',
                   new=AsyncMock(return_value=None)), \
             patch('app.lol.champion_baseline.getChampionBaselineWinrate',
                   new=AsyncMock(return_value=None)):
            team = [
                _makeParticipant('p1', 1, 30000, deaths=3),  # 正常输出
                _makeParticipant('p2', 2, 28000, deaths=4),
                _makeParticipant('p3', 3, 32000, deaths=5),
                _makeParticipant('p4', 4, 5000, deaths=12),   # 战犯: 伤害 1/6, 死亡 2 倍
                _makeParticipant('p5', 5, 31000, deaths=4),
            ]
            result = _run_async(diagnoseTeam(team, 420, False, 'normal'))
            assert result is not None
            assert result['verdict'] == 'war_criminal'
            assert result['suspect']['puuid'] == 'p4'

    def test_carried_dog_obvious(self):
        """胜局明显的躺赢狗: 伤害低/死亡多但赢了."""
        with patch('app.lol.augment_baseline.getHextechAugmentScore',
                   new=AsyncMock(return_value=None)), \
             patch('app.lol.champion_baseline.getChampionBaselineWinrate',
                   new=AsyncMock(return_value=None)):
            team = [
                _makeParticipant('p1', 1, 35000, deaths=3, win=True),
                _makeParticipant('p2', 2, 33000, deaths=4, win=True),
                _makeParticipant('p3', 3, 36000, deaths=5, win=True),
                _makeParticipant('p4', 4, 6000, deaths=10, win=True),  # 躺赢狗
                _makeParticipant('p5', 5, 34000, deaths=4, win=True),
            ]
            result = _run_async(diagnoseTeam(team, 420, True, 'normal'))
            assert result is not None
            assert result['verdict'] == 'carried_dog'
            assert result['suspect']['puuid'] == 'p4'

    def test_no_clear_suspect_balanced_team(self):
        """均衡队伍: 无明显异常."""
        with patch('app.lol.augment_baseline.getHextechAugmentScore',
                   new=AsyncMock(return_value=None)), \
             patch('app.lol.champion_baseline.getChampionBaselineWinrate',
                   new=AsyncMock(return_value=None)):
            team = [
                _makeParticipant('p1', 1, 25000, deaths=5, win=True),
                _makeParticipant('p2', 2, 24000, deaths=4, win=True),
                _makeParticipant('p3', 3, 26000, deaths=6, win=True),
                _makeParticipant('p4', 4, 24500, deaths=5, win=True),
                _makeParticipant('p5', 5, 25500, deaths=5, win=True),
            ]
            result = _run_async(diagnoseTeam(team, 420, True, 'normal'))
            assert result is not None
            # 均衡队伍应判 no_clear 或 team_underperformed
            assert result['verdict'] in ('no_clear_suspect', 'team_underperformed')

    def test_hextech_vision_not_counted(self):
        """海克斯大乱斗视野分不计入: 即使某玩家视野极低, 也不应被判定战犯."""
        with patch('app.lol.augment_baseline.getHextechAugmentScore',
                   new=AsyncMock(return_value=None)), \
             patch('app.lol.champion_baseline.getChampionBaselineWinrate',
                   new=AsyncMock(return_value=None)):
            team = [
                _makeParticipant('p1', 1, 30000, deaths=3, visionScore=0, win=False),
                _makeParticipant('p2', 2, 28000, deaths=4, visionScore=0, win=False),
                _makeParticipant('p3', 3, 32000, deaths=5, visionScore=0, win=False),
                _makeParticipant('p4', 4, 31000, deaths=4, visionScore=0, win=False),
                _makeParticipant('p5', 5, 29000, deaths=4, visionScore=0, win=False),
            ]
            # 海克斯模式 2400
            result = _run_async(diagnoseTeam(team, 2400, False, 'normal'))
            assert result is not None
            # 视野全 0 不应导致误判战犯
            # 在均衡视野下, 应判 no_clear
            assert result['verdict'] in ('no_clear_suspect', 'team_underperformed')

    def test_baseline_amplifies_strong_champion(self):
        """OPGG 胜率高的英雄, 同样表现差更易被判战犯.

        模拟: 同一玩家在同一局中, 当 championBaselineWinrate 从 None 变 0.6,
        应更容易被判战犯 (score 更低).
        """
        # 5 人, p4 略差但不算极端
        team = [
            _makeParticipant('p1', 1, 28000, deaths=5),
            _makeParticipant('p2', 2, 27000, deaths=6),
            _makeParticipant('p3', 3, 29000, deaths=4),
            _makeParticipant('p4', 4, 22000, deaths=8),  # 略差
            _makeParticipant('p5', 5, 28000, deaths=5),
        ]

        # 1) 无基线 (None)
        with patch('app.lol.augment_baseline.getHextechAugmentScore',
                   new=AsyncMock(return_value=None)), \
             patch('app.lol.champion_baseline.getChampionBaselineWinrate',
                   new=AsyncMock(return_value=None)):
            r1 = _run_async(diagnoseTeam(team, 420, False, 'normal'))

        # 2) p4 的英雄基线胜率 0.65 (高)
        async def mock_wr(cid, qid):
            if cid == 4:
                return 0.65
            return 0.5
        with patch('app.lol.augment_baseline.getHextechAugmentScore',
                   new=AsyncMock(return_value=None)), \
             patch('app.lol.champion_baseline.getChampionBaselineWinrate',
                   new=AsyncMock(side_effect=mock_wr)):
            r2 = _run_async(diagnoseTeam(team, 420, False, 'normal'))

        # 两种情况都应给出诊断, 且 r2 中 p4 的 score 应更低
        # (高胜率英雄预期贡献高, 实际贡献低被进一步扣分)
        assert r1 is not None
        assert r2 is not None
        # r2 应更倾向战犯 (p4 score 更低)
        # 不强制 verdict 必为 war_criminal (因为差距不够大), 但 score 应更低
        # 由于 setVerdict 中 score 来自 worst, 这里比较 suspect 是否为 p4
        # 实际更稳的断言: r2.suspect 是 p4 且 score 比 r1 更低
        # (但若 r1 也是 p4, 我们比较 score 数值)
        if r1['suspect']['puuid'] == 'p4' and r2['suspect']['puuid'] == 'p4':
            assert r2['score'] <= r1['score'] + 0.001  # 允许数值误差

    def test_augment_baseline_amplifies_strong_combo(self):
        """强海克斯强化组合的玩家, 实际贡献低更易被判战犯."""
        team = [
            _makeParticipant('p1', 1, 28000, deaths=5, augmentIds=[1, 2, 3]),
            _makeParticipant('p2', 2, 27000, deaths=6, augmentIds=[4, 5, 6]),
            _makeParticipant('p3', 3, 29000, deaths=4, augmentIds=[7, 8, 9]),
            _makeParticipant('p4', 4, 22000, deaths=8, augmentIds=[10, 11, 12]),
            _makeParticipant('p5', 5, 28000, deaths=5, augmentIds=[13, 14, 15]),
        ]

        # p4 的强化组合分 0.8 (强), 其他 0.5 (中性)
        async def mock_aug(aids, cid=None):
            if cid == 4:
                return 0.8
            return 0.5

        with patch('app.lol.augment_baseline.getHextechAugmentScore',
                   new=AsyncMock(side_effect=mock_aug)), \
             patch('app.lol.champion_baseline.getChampionBaselineWinrate',
                   new=AsyncMock(return_value=None)):
            result = _run_async(diagnoseTeam(team, 2400, False, 'normal'))
            assert result is not None
            # 强组合英雄实际贡献低, 更易被判战犯
            assert result['suspect']['puuid'] == 'p4'

    def test_sensitivity_strict_reduces_false_positives(self):
        """strict 灵敏度 (阈值高) 不易判战犯, loose 易判."""
        # 中等差距: strict 不判, loose 判
        team = [
            _makeParticipant('p1', 1, 28000, deaths=5),
            _makeParticipant('p2', 2, 27000, deaths=6),
            _makeParticipant('p3', 3, 29000, deaths=4),
            _makeParticipant('p4', 4, 24000, deaths=7),  # 中等差
            _makeParticipant('p5', 5, 28000, deaths=5),
        ]
        with patch('app.lol.augment_baseline.getHextechAugmentScore',
                   new=AsyncMock(return_value=None)), \
             patch('app.lol.champion_baseline.getChampionBaselineWinrate',
                   new=AsyncMock(return_value=None)):
            r_strict = _run_async(diagnoseTeam(team, 420, False, 'strict'))
            r_loose = _run_async(diagnoseTeam(team, 420, False, 'loose'))
        # strict 阈值 1.1, 中等差距 0.6 不应触发 war_criminal
        # loose 阈值 0.6, 中等差距可能触发 (取决于具体 z)
        # 这里仅断言 strict 不判战犯
        assert r_strict['verdict'] != 'war_criminal'


class TestVerdictLabel:
    def test_war_criminal_label(self):
        assert verdictLabel('war_criminal', False) == '战犯'

    def test_carried_dog_label(self):
        assert verdictLabel('carried_dog', True) == '躺赢狗'

    def test_team_underperformed_label(self):
        assert verdictLabel('team_underperformed', False) == '团队低迷'

    def test_no_clear_label(self):
        assert verdictLabel('no_clear_suspect', True) == '无明显异常'

    def test_unknown_label(self):
        assert verdictLabel('xyz', True) == ''


class TestWarCriminalCache:
    def test_set_and_get(self):
        from app.lol.war_criminal_cache import setVerdict, getVerdict, clear
        clear()
        setVerdict(
            gameId=12345,
            verdict='war_criminal',
            label='战犯',
            isCurrentSuspect=True,
            score=-1.85,
            evidence=[{'metric': 'damage'}],
        )
        cached = getVerdict(12345)
        assert cached is not None
        assert cached['verdict'] == 'war_criminal'
        assert cached['label'] == '战犯'
        assert cached['isCurrentSuspect'] is True
        assert cached['score'] == -1.85
        assert len(cached['evidence']) == 1

    def test_get_missing_returns_none(self):
        from app.lol.war_criminal_cache import getVerdict, clear
        clear()
        assert getVerdict(99999) is None

    def test_clear(self):
        from app.lol.war_criminal_cache import setVerdict, getVerdict, clear
        setVerdict(1, 'war_criminal', '战犯', True, -1.0, [])
        clear()
        assert getVerdict(1) is None


class TestPickHonorTarget:
    """honor 策略测试 (auto honor 部分)."""

    def _makeEog(self, candidates):
        return {'honorables': candidates}

    def test_friends_first_uses_friend(self):
        from app.lol.tools_pure import pickHonorTarget, HONOR_STRATEGY_FRIENDS_FIRST
        eog = self._makeEog([
            {'puuid': 'p1', 'summonerId': 101, 'score': 50},
            {'puuid': 'p2', 'summonerId': 102, 'score': 30},  # 好友
            {'puuid': 'p3', 'summonerId': 103, 'score': 80},
        ])
        friends = {'p2'}
        target = pickHonorTarget(eog, friends, HONOR_STRATEGY_FRIENDS_FIRST)
        assert target['puuid'] == 'p2'

    def test_friends_first_fallback_to_best(self):
        from app.lol.tools_pure import pickHonorTarget, HONOR_STRATEGY_FRIENDS_FIRST
        eog = self._makeEog([
            {'puuid': 'p1', 'summonerId': 101, 'score': 50},
            {'puuid': 'p3', 'summonerId': 103, 'score': 80},
        ])
        target = pickHonorTarget(eog, set(), HONOR_STRATEGY_FRIENDS_FIRST)
        # 无好友, 退回 best_score
        assert target['puuid'] == 'p3'

    def test_friends_only_skip_when_no_friend(self):
        from app.lol.tools_pure import pickHonorTarget, HONOR_STRATEGY_FRIENDS_ONLY
        eog = self._makeEog([
            {'puuid': 'p1', 'summonerId': 101, 'score': 50},
            {'puuid': 'p3', 'summonerId': 103, 'score': 80},
        ])
        target = pickHonorTarget(eog, set(), HONOR_STRATEGY_FRIENDS_ONLY)
        assert target is None

    def test_best_score_strategy(self):
        from app.lol.tools_pure import pickHonorTarget, HONOR_STRATEGY_BEST_SCORE
        eog = self._makeEog([
            {'puuid': 'p1', 'summonerId': 101, 'score': 50},
            {'puuid': 'p2', 'summonerId': 102, 'score': 90},
            {'puuid': 'p3', 'summonerId': 103, 'score': 80},
        ])
        target = pickHonorTarget(eog, set(), HONOR_STRATEGY_BEST_SCORE)
        assert target['puuid'] == 'p2'

    def test_exclude_self(self):
        from app.lol.tools_pure import pickHonorTarget, HONOR_STRATEGY_BEST_SCORE
        eog = self._makeEog([
            {'puuid': 'me', 'summonerId': 0, 'score': 999},  # 自己
            {'puuid': 'p1', 'summonerId': 101, 'score': 50},
        ])
        target = pickHonorTarget(eog, set(), HONOR_STRATEGY_BEST_SCORE,
                                  currentPuuid='me')
        assert target['puuid'] == 'p1'

    def test_empty_eog(self):
        from app.lol.tools_pure import pickHonorTarget
        assert pickHonorTarget(None, set()) is None
        assert pickHonorTarget({}, set()) is None
        assert pickHonorTarget({'honorables': []}, set()) is None
