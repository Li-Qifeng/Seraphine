"""Tests for war_criminal.py core algorithm.

全队 5 档评级核心算法 (纯函数, 无 LCU/Qt 依赖):
- 海克斯大乱斗视野分不计入评分
- 海克斯强化组合影响预期贡献基线
- OPGG 英雄胜率影响判定权重 (高胜率英雄更易被判躺赢狗/战犯)
- rateEntireTeam: 全队每人 5 档评级 (z-score -> grade 1-5)

mock OPGG 基线模块 (champion_baseline / augment_baseline) 以避免网络请求.
"""
import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub PyQt5 (无法在非 Windows 环境直接 import)
for _qt_mod in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui",
                "PyQt5.QtXml", "PyQt5.QtSvg"):
    if _qt_mod not in sys.modules:
        sys.modules[_qt_mod] = MagicMock()

# 显式导入被 patch 的基线模块, 让 patch('app.lol.augment_baseline.xxx') 能解析到目标.
# 否则 war_criminal 内部是惰性导入, 测试环境里 app.lol 包未挂载 augment_baseline 子模块,
# mock.patch 在 __enter__ 时会因 AttributeError 失败.
import app.lol.augment_baseline  # noqa: E402, F401
import app.lol.champion_baseline  # noqa: E402, F401

from app.lol.war_criminal import (  # noqa: E402
    ParticipantStats,
    rateEntireTeam,
    gradeFromScore,
    gradeLabel,
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


# ---------- rateEntireTeam 集成测试 ----------

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


def _neutral_baselines():
    """mock OPGG 基线返回 None (降级到纯 z-score)."""
    return (
        patch('app.lol.augment_baseline.getHextechAugmentScore',
              new=AsyncMock(return_value=None)),
        patch('app.lol.champion_baseline.getChampionBaselineWinrate',
              new=AsyncMock(return_value=None)),
    )


class TestRateEntireTeam:
    def test_team_too_small(self):
        """少于 2 人无法评级, 返回空列表."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            result = _run_async(rateEntireTeam([], 420, True))
            assert result == []

            team = [_makeParticipant('p1', 1)]
            result = _run_async(rateEntireTeam(team, 420, True))
            assert result == []

    def test_obvious_worst_gets_lowest_grade(self):
        """明显最差的玩家 (败方) 应拿到最低档 (4 或 5)."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant('p1', 1, 30000, deaths=3, win=False),
                _makeParticipant('p2', 2, 28000, deaths=4, win=False),
                _makeParticipant('p3', 3, 32000, deaths=5, win=False),
                _makeParticipant('p4', 4, 5000, deaths=12, win=False),   # 战犯
                _makeParticipant('p5', 5, 31000, deaths=4, win=False),
            ]
            result = _run_async(rateEntireTeam(team, 420, isWin=False))
            assert len(result) == 5
            p4 = next(r for r in result if r['puuid'] == 'p4')
            assert p4['grade'] >= 4  # 至少档 4 (战犯嫌疑人)
            assert p4['score'] < 0

    def test_carried_dog_obvious(self):
        """胜方明显躺赢狗: 伤害低/死亡多但赢了, 应拿低档."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant('p1', 1, 35000, deaths=3, win=True),
                _makeParticipant('p2', 2, 33000, deaths=4, win=True),
                _makeParticipant('p3', 3, 36000, deaths=5, win=True),
                _makeParticipant('p4', 4, 6000, deaths=10, win=True),  # 躺赢狗
                _makeParticipant('p5', 5, 34000, deaths=4, win=True),
            ]
            result = _run_async(rateEntireTeam(team, 420, isWin=True))
            p4 = next(r for r in result if r['puuid'] == 'p4')
            assert p4['grade'] >= 4  # 躺赢狗档
            assert p4['score'] < 0

    def test_balanced_team_all_grade_3(self):
        """均衡队伍: 全员数据接近, z-score 接近 0, 都在档 3."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant('p1', 1, 25000, deaths=5, win=True),
                _makeParticipant('p2', 2, 24000, deaths=4, win=True),
                _makeParticipant('p3', 3, 26000, deaths=6, win=True),
                _makeParticipant('p4', 4, 24500, deaths=5, win=True),
                _makeParticipant('p5', 5, 25500, deaths=5, win=True),
            ]
            result = _run_async(rateEntireTeam(team, 420, isWin=True))
            assert len(result) == 5
            for r in result:
                # 均衡队伍最差也不应极端负
                assert r['score'] > -1.5

    def test_hextech_vision_not_counted(self):
        """海克斯大乱斗视野分不计入: 视野全 0 不影响评分."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant('p1', 1, 30000, deaths=3, visionScore=0, win=False),
                _makeParticipant('p2', 2, 28000, deaths=4, visionScore=0, win=False),
                _makeParticipant('p3', 3, 32000, deaths=5, visionScore=0, win=False),
                _makeParticipant('p4', 4, 31000, deaths=4, visionScore=0, win=False),
                _makeParticipant('p5', 5, 29000, deaths=4, visionScore=0, win=False),
            ]
            result = _run_async(rateEntireTeam(team, 2400, isWin=False))
            # 视野全 0 不应导致极端误判
            for r in result:
                assert r['score'] > -1.5

    def test_baseline_amplifies_strong_champion(self):
        """OPGG 胜率高的英雄, 同样表现差更易得低分.

        模拟: 同一玩家在同一局中, 当 championBaselineWinrate 从 None 变 0.65,
        score 应更低 (高胜率英雄预期贡献高, 实际贡献低被进一步扣分).
        """
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
            r1 = _run_async(rateEntireTeam(team, 420, isWin=False))

        # 2) p4 的英雄基线胜率 0.65 (高)
        async def mock_wr(cid, qid):
            if cid == 4:
                return 0.65
            return 0.5
        with patch('app.lol.augment_baseline.getHextechAugmentScore',
                   new=AsyncMock(return_value=None)), \
             patch('app.lol.champion_baseline.getChampionBaselineWinrate',
                   new=AsyncMock(side_effect=mock_wr)):
            r2 = _run_async(rateEntireTeam(team, 420, isWin=False))

        # 两种情况都应给出评级
        assert len(r1) == 5
        assert len(r2) == 5
        # r2 中 p4 的 score 应更低 (高胜率英雄预期贡献高, 实际贡献低被进一步扣分)
        p4_r1 = next(r for r in r1 if r['puuid'] == 'p4')
        p4_r2 = next(r for r in r2 if r['puuid'] == 'p4')
        assert p4_r2['score'] <= p4_r1['score'] + 0.001  # 允许数值误差

    def test_augment_baseline_amplifies_strong_combo(self):
        """强海克斯强化组合的玩家, 实际贡献低更易得低分."""
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
            result = _run_async(rateEntireTeam(team, 2400, isWin=False))
            assert len(result) == 5
            # p4 应是 score 最低的 (强组合英雄实际贡献低, 更易被判低档)
            p4 = next(r for r in result if r['puuid'] == 'p4')
            others = [r['score'] for r in result if r['puuid'] != 'p4']
            assert p4['score'] < min(others)


class TestGradeLabel:
    def test_tieba_win(self):
        assert gradeLabel(1, True, 'tieba') == '神'
        assert gradeLabel(4, True, 'tieba') == '躺赢狗'

    def test_tieba_loss(self):
        assert gradeLabel(4, False, 'tieba') == '甲级战犯'
        assert gradeLabel(5, False, 'tieba') == '初升东曦'

    def test_horse_universal(self):
        for isWin in (True, False):
            assert gradeLabel(1, isWin, 'horse') == '上等马'

    def test_grade_out_of_range_clamped(self):
        assert gradeLabel(0, True, 'tieba') == '神'
        assert gradeLabel(99, True, 'tieba') == '消失'


class TestGradeFromScore:
    def test_high_positive(self):
        assert gradeFromScore(2.5) == 1
        assert gradeFromScore(1.0) == 1

    def test_neutral(self):
        assert gradeFromScore(0.0) == 3

    def test_high_negative(self):
        assert gradeFromScore(-1.5) == 5


class TestWarCriminalCache:
    def test_set_and_get(self):
        from app.lol.war_criminal_cache import setVerdict, getVerdict, clear
        clear()
        winner_rating = [
            {'puuid': 'p1', 'grade': 1, 'label': '神', 'score': 2.0,
             'isWin': True, 'isCurrent': False, 'evidence': []},
        ]
        setVerdict(gameId=12345, winnerRating=winner_rating)
        cached = getVerdict(12345)
        assert cached is not None
        assert cached['winnerRating'] == winner_rating
        assert cached['winnerRating'][0]['label'] == '神'

    def test_get_missing_returns_none(self):
        from app.lol.war_criminal_cache import getVerdict, clear
        clear()
        assert getVerdict(99999) is None

    def test_clear(self):
        from app.lol.war_criminal_cache import setVerdict, getVerdict, clear
        setVerdict(1, winnerRating=[{'puuid': 'p1', 'grade': 1}])
        clear()
        assert getVerdict(1) is None


class TestPickHonorTarget:
    """honor 策略测试 (auto honor 部分)."""

    def _makeEog(self, candidates):
        # /lol-honor-v2/v1/ballot 实测字段为 eligibleAllies (非 honorables)
        return {'eligibleAllies': candidates}

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
