"""Tests for team rating (5-tier grade) in war_criminal.py.

全队 5 档评级 (扩展算法, 复用 z-score 贡献分):
- gradeFromScore: z-score -> 1-5 档位
- gradeLabel: 档位 -> 标签文本 (贴吧风胜败方不同, 马系风通用)
- rateEntireTeam: 全队每人评级 (按 score 降序)
- 缓存 getTeamRating/setVerdict
"""
import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub PyQt5 (非 Windows 环境无法 import)
for _qt_mod in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui"):
    if _qt_mod not in sys.modules:
        sys.modules[_qt_mod] = MagicMock()

import app.lol.augment_baseline  # noqa: E402, F401
import app.lol.champion_baseline  # noqa: E402, F401

from app.lol.war_criminal import (  # noqa: E402
    ParticipantStats,
    gradeFromScore,
    gradeLabel,
    rateEntireTeam,
    GRADE_THRESHOLDS,
    GRADE_LABELS_TIEBA,
    GRADE_LABELS_HORSE,
)
from app.lol.war_criminal_cache import (  # noqa: E402
    setVerdict,
    getVerdict,
    getTeamRating,
    clear as clearCache,
)


def _run_async(coro):
    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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


def _neutral_baselines():
    """mock OPGG 基线返回 None (降级到纯 z-score)."""
    return (
        patch('app.lol.augment_baseline.getHextechAugmentScore',
              new=AsyncMock(return_value=None)),
        patch('app.lol.champion_baseline.getChampionBaselineWinrate',
              new=AsyncMock(return_value=None)),
    )


# ---------- gradeFromScore 纯函数测试 ----------

class TestGradeFromScore:
    def test_high_positive(self):
        # z >= 1.0 -> 档 1
        assert gradeFromScore(2.5) == 1
        assert gradeFromScore(1.0) == 1

    def test_medium_positive(self):
        # 0.3 <= z < 1.0 -> 档 2
        assert gradeFromScore(0.5) == 2
        assert gradeFromScore(0.3) == 2
        assert gradeFromScore(0.999) == 2

    def test_neutral(self):
        # -0.3 < z < 0.3 -> 档 3
        assert gradeFromScore(0.0) == 3
        assert gradeFromScore(0.29) == 3
        assert gradeFromScore(-0.29) == 3

    def test_medium_negative(self):
        # -1.0 <= z <= -0.3 -> 档 4
        assert gradeFromScore(-0.3) == 4
        assert gradeFromScore(-0.5) == 4
        assert gradeFromScore(-1.0) == 4

    def test_high_negative(self):
        # z < -1.0 -> 档 5
        assert gradeFromScore(-1.5) == 5
        assert gradeFromScore(-2.0) == 5

    def test_boundary_consistency(self):
        # 阈值边界
        assert gradeFromScore(GRADE_THRESHOLDS[0]) == 1      # 1.0 -> 档 1
        assert gradeFromScore(GRADE_THRESHOLDS[1]) == 2      # 0.3 -> 档 2
        assert gradeFromScore(GRADE_THRESHOLDS[2] + 0.01) == 3   # -0.29 -> 档 3
        assert gradeFromScore(GRADE_THRESHOLDS[3]) == 4      # -1.0 -> 档 4


# ---------- gradeLabel 测试 ----------

class TestGradeLabel:
    def test_tieba_win(self):
        # 贴吧风胜方: 神/爹/小有亮点/躺赢狗/消失
        assert gradeLabel(1, True, 'tieba') == '神'
        assert gradeLabel(2, True, 'tieba') == '爹'
        assert gradeLabel(3, True, 'tieba') == '小有亮点'
        assert gradeLabel(4, True, 'tieba') == '躺赢狗'
        assert gradeLabel(5, True, 'tieba') == '消失'

    def test_tieba_loss(self):
        # 贴吧风败方: 人类/类人/战犯嫌疑人/甲级战犯/初升东曦
        assert gradeLabel(1, False, 'tieba') == '人类'
        assert gradeLabel(2, False, 'tieba') == '类人'
        assert gradeLabel(3, False, 'tieba') == '战犯嫌疑人'
        assert gradeLabel(4, False, 'tieba') == '甲级战犯'
        assert gradeLabel(5, False, 'tieba') == '初升东曦'

    def test_horse_universal(self):
        # 马系风胜败方通用: 上等马/中上等马/中等马/下等马/纯牛马
        for isWin in (True, False):
            assert gradeLabel(1, isWin, 'horse') == '上等马'
            assert gradeLabel(2, isWin, 'horse') == '中上等马'
            assert gradeLabel(3, isWin, 'horse') == '中等马'
            assert gradeLabel(4, isWin, 'horse') == '下等马'
            assert gradeLabel(5, isWin, 'horse') == '纯牛马'

    def test_default_style_is_tieba(self):
        # 不传 style 默认贴吧风
        assert gradeLabel(1, True) == '神'
        assert gradeLabel(1, False) == '人类'

    def test_grade_out_of_range_clamped(self):
        # 越界档位被 clamp 到 [1, 5]
        assert gradeLabel(0, True, 'tieba') == '神'       # 0 -> 1
        assert gradeLabel(99, True, 'tieba') == '消失'     # 99 -> 5
        assert gradeLabel(-1, True, 'tieba') == '神'       # -1 -> 1


# ---------- 阈值与标签数量一致性 ----------

class TestGradeConsistency:
    def test_tieba_has_5_labels_each_side(self):
        assert len(GRADE_LABELS_TIEBA[True]) == 5
        assert len(GRADE_LABELS_TIEBA[False]) == 5

    def test_horse_has_5_labels(self):
        assert len(GRADE_LABELS_HORSE[True]) == 5
        assert len(GRADE_LABELS_HORSE[False]) == 5

    def test_thresholds_has_4_boundaries(self):
        # 5 档需要 4 个分界点
        assert len(GRADE_THRESHOLDS) == 4


# ---------- rateEntireTeam 集成测试 ----------

class TestRateEntireTeam:
    def test_team_too_small(self):
        """少于 2 人无法评级, 返回空列表."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            result = _run_async(rateEntireTeam([], 420, True))
            assert result == []

            team = [_makeParticipant('p1', 1)]
            result = _run_async(rateEntireTeam(team, 420, True))
            assert result == []

    def test_basic_rating_5_players(self):
        """5 人队正常评级, 每人有 score/grade/label."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant('p1', 1, 30000, deaths=3),
                _makeParticipant('p2', 2, 28000, deaths=4),
                _makeParticipant('p3', 3, 32000, deaths=5),
                _makeParticipant('p4', 4, 5000, deaths=12),   # 最差
                _makeParticipant('p5', 5, 31000, deaths=4),
            ]
            result = _run_async(rateEntireTeam(team, 420, isWin=False,
                                                style='tieba'))
            assert len(result) == 5
            # 按 score 降序 (贡献最大的在前)
            scores = [r['score'] for r in result]
            assert scores == sorted(scores, reverse=True)
            # 每项字段完整
            for r in result:
                assert 'puuid' in r
                assert 'score' in r
                assert 'grade' in r and 1 <= r['grade'] <= 5
                assert 'label' in r and r['label']
                assert r['isWin'] is False

    def test_obvious_worst_gets_lowest_grade(self):
        """明显最差的玩家应该拿到最低档 (5)."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant('p1', 1, 30000, deaths=3),
                _makeParticipant('p2', 2, 28000, deaths=4),
                _makeParticipant('p3', 3, 32000, deaths=5),
                _makeParticipant('p4', 4, 5000, deaths=12),   # 战犯: 1/6 伤害, 2x 死亡
                _makeParticipant('p5', 5, 31000, deaths=4),
            ]
            result = _run_async(rateEntireTeam(team, 420, isWin=False))
            # 找到 p4 的评级
            p4_rating = next(r for r in result if r['puuid'] == 'p4')
            assert p4_rating['grade'] >= 4  # 至少是档 4 (战犯嫌疑人) 或 5 (初升东曦)
            assert p4_rating['score'] < 0   # 负分

    def test_obvious_best_gets_highest_grade(self):
        """明显最好的玩家应该拿到最高档 (1)."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant('p1', 1, 50000, deaths=2, kills=15),  # 大腿
                _makeParticipant('p2', 2, 20000, deaths=6),
                _makeParticipant('p3', 3, 22000, deaths=5),
                _makeParticipant('p4', 4, 18000, deaths=7),
                _makeParticipant('p5', 5, 21000, deaths=6),
            ]
            result = _run_async(rateEntireTeam(team, 420, isWin=True))
            p1_rating = next(r for r in result if r['puuid'] == 'p1')
            assert p1_rating['grade'] <= 2  # 档 1 (神) 或 2 (爹)
            assert p1_rating['score'] > 0

    def test_style_affects_labels(self):
        """不同风格产生不同标签."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant('p1', 1, 30000, deaths=3),
                _makeParticipant('p2', 2, 20000, deaths=6),
                _makeParticipant('p3', 3, 25000, deaths=5),
            ]
            tieba_result = _run_async(rateEntireTeam(team, 420, True,
                                                      style='tieba'))
            horse_result = _run_async(rateEntireTeam(team, 420, True,
                                                      style='horse'))
            # 同一玩家档位相同, 标签文本不同 (至少有一个不同)
            tieba_labels = {r['puuid']: r['label'] for r in tieba_result}
            horse_labels = {r['puuid']: r['label'] for r in horse_result}
            assert tieba_labels != horse_labels  # 标签不同
            # 档位应该相同 (同样的数据)
            tieba_grades = {r['puuid']: r['grade'] for r in tieba_result}
            horse_grades = {r['puuid']: r['grade'] for r in horse_result}
            assert tieba_grades == horse_grades

    def test_is_current_marked(self):
        """currentPuuid 对应的玩家被标记 isCurrent=True."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant('p1', 1, 30000, deaths=3),
                _makeParticipant('p2', 2, 20000, deaths=6),
                _makeParticipant('p3', 3, 25000, deaths=5),
            ]
            result = _run_async(rateEntireTeam(team, 420, True,
                                                currentPuuid='p2'))
            for r in result:
                assert r['isCurrent'] == (r['puuid'] == 'p2')

    def test_all_identical_stats_gets_grade_3(self):
        """全员数据相同时, z-score 全为 0, 所有人档 3 (普通人/中等马)."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant(f'p{i}', i, 25000, deaths=5)
                for i in range(1, 6)
            ]
            result = _run_async(rateEntireTeam(team, 420, True))
            assert len(result) == 5
            for r in result:
                assert r['grade'] == 3
                assert r['score'] == 0.0

    def test_hextech_ignores_vision(self):
        """海克斯模式 (queueId=2400) 视野分不计入评分."""
        with _neutral_baselines()[0], _neutral_baselines()[1]:
            team = [
                _makeParticipant('p1', 1, 25000, deaths=5, visionScore=100),
                _makeParticipant('p2', 2, 25000, deaths=5, visionScore=0),
                _makeParticipant('p3', 3, 25000, deaths=5, visionScore=50),
            ]
            # 海克斯模式: 视野差异不影响评分
            result = _run_async(rateEntireTeam(team, 2400, True))
            for r in result:
                assert r['grade'] == 3  # 全员档 3, 视野被忽略


# ---------- 缓存 getTeamRating/setVerdict 测试 ----------

class TestCacheTeamRating:
    def setup_method(self):
        clearCache()

    def teardown_method(self):
        clearCache()

    def test_set_and_get_winner_rating(self):
        winner_rating = [
            {'puuid': 'p1', 'grade': 1, 'label': '神', 'score': 2.0,
             'isWin': True, 'isCurrent': False, 'evidence': []},
            {'puuid': 'p2', 'grade': 3, 'label': '小有亮点', 'score': 0.0,
             'isWin': True, 'isCurrent': True, 'evidence': []},
        ]
        setVerdict(gameId=999, winnerRating=winner_rating)
        cached = getTeamRating(999, isWinner=True)
        assert cached == winner_rating
        assert len(cached) == 2
        assert cached[0]['label'] == '神'

    def test_set_and_get_loser_rating(self):
        loser_rating = [
            {'puuid': 'p3', 'grade': 5, 'label': '初升东曦', 'score': -2.0,
             'isWin': False, 'isCurrent': False, 'evidence': []},
        ]
        setVerdict(gameId=888, loserRating=loser_rating)
        cached = getTeamRating(888, isWinner=False)
        assert cached == loser_rating
        assert cached[0]['label'] == '初升东曦'

    def test_missing_rating_returns_none(self):
        # 未写入评级时返回 None
        setVerdict(gameId=777)  # 只写基本字段, 不写 rating
        assert getTeamRating(777, isWinner=True) is None
        assert getTeamRating(777, isWinner=False) is None

    def test_missing_game_returns_none(self):
        assert getTeamRating(123456, isWinner=True) is None

    def test_none_game_id_returns_none(self):
        assert getTeamRating(None, isWinner=True) is None

    def test_overwrite_rating(self):
        # 同一 gameId 多次写入, 后者覆盖前者
        setVerdict(gameId=111, winnerRating=[{'puuid': 'p1', 'grade': 1, 'label': '神'}])
        setVerdict(gameId=111, winnerRating=[{'puuid': 'p2', 'grade': 3, 'label': '小有亮点'}])
        cached = getVerdict(111)
        assert cached is not None
        assert cached['winnerRating'][0]['puuid'] == 'p2'
