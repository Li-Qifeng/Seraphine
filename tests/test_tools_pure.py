"""
Tests for pure parsing functions from app/lol/tools_pure.py.

Pure functions (no LCU connection required, no Qt dependency) are imported
directly from app.lol.tools_pure. Tests that require connector/Qt are placed in
separate test files with appropriate fixtures.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lol.tools_pure import (
    translateTier,
    timeStampToStr,
    timeStampToShortStr,
    secsToStr,
    separateTeams,
    parseSummonerOrder,
    sortedSummonersByGameRole,
    parseGames,
    parseRankInfo,
    parseDetailRankInfo,
)


class TestTranslateTier:
    def test_empty(self):
        assert translateTier("") == "--"

    @pytest.mark.parametrize("tier,expected_long,expected_short", [
        ("Iron", "坚韧黑铁", "黑铁"),
        ("Bronze", "英勇黄铜", "黄铜"),
        ("Silver", "不屈白银", "白银"),
        ("Gold", "荣耀黄金", "黄金"),
        ("Platinum", "华贵铂金", "铂金"),
        ("Emerald", "流光翡翠", "翡翠"),
        ("Diamond", "璀璨钻石", "钻石"),
        ("Master", "超凡大师", "大师"),
        ("Grandmaster", "傲世宗师", "宗师"),
        ("Challenger", "最强王者", "王者"),
    ])
    def test_all_tiers(self, tier, expected_long, expected_short):
        assert translateTier(tier) == expected_long
        assert translateTier(tier, short=True) == expected_short

    def test_case_insensitive(self):
        assert translateTier("gold") == "荣耀黄金"
        assert translateTier("GOLD") == "荣耀黄金"


class TestTimeStampToStr:
    def test_normal(self):
        result = timeStampToStr(1700000000000)
        assert result.startswith("2023/11/")

    def test_epoch(self):
        assert timeStampToStr(0) == "1970/01/01 08:00"


class TestTimeStampToShortStr:
    def test_normal(self):
        assert timeStampToShortStr(1700000000000) == "11/15"


class TestSecsToStr:
    def test_zero(self):
        assert secsToStr(0) == "00:00"

    def test_normal(self):
        assert secsToStr(125) == "02:05"

    def test_max_minutes(self):
        assert secsToStr(3599) == "59:59"


class TestSeparateTeams:
    def _team(self, *ids):
        return [{'summonerId': sid} for sid in ids]

    def test_current_in_team_one(self):
        data = {'teamOne': self._team(1, 2, 3), 'teamTwo': self._team(4, 5, 6)}
        ally, enemy = separateTeams(data, 1)
        assert ally == data['teamOne']
        assert enemy == data['teamTwo']

    def test_current_in_team_two(self):
        data = {'teamOne': self._team(1, 2, 3), 'teamTwo': self._team(4, 5, 6)}
        ally, enemy = separateTeams(data, 5)
        assert ally == data['teamTwo']
        assert enemy == data['teamOne']

    def test_not_found(self):
        data = {'teamOne': self._team(1, 2), 'teamTwo': self._team(3, 4)}
        ally, enemy = separateTeams(data, 99)
        assert ally is None
        assert enemy is None


class TestParseSummonerOrder:
    def test_sorted_by_cell_id(self):
        team = [
            {'summonerId': 5, 'cellId': 3},
            {'summonerId': 3, 'cellId': 1},
            {'summonerId': 7, 'cellId': 2},
        ]
        assert parseSummonerOrder(team) == [3, 7, 5]

    def test_skips_zero_id(self):
        team = [
            {'summonerId': 1, 'cellId': 1},
            {'summonerId': 0, 'cellId': 2},
            {'summonerId': 3, 'cellId': 3},
        ]
        assert parseSummonerOrder(team) == [1, 3]

    def test_empty(self):
        assert parseSummonerOrder([]) == []


class TestSortedSummonersByGameRole:
    @pytest.fixture
    def summoners(self):
        return [
            {'summonerId': 1, 'selectedPosition': 'MIDDLE'},
            {'summonerId': 2, 'selectedPosition': 'TOP'},
            {'summonerId': 3, 'selectedPosition': 'JUNGLE'},
            {'summonerId': 4, 'selectedPosition': 'BOTTOM'},
            {'summonerId': 5, 'selectedPosition': 'UTILITY'},
        ]

    def test_standard_order(self, summoners):
        result = sortedSummonersByGameRole(summoners)
        ids = [s['summonerId'] for s in result]
        assert ids == [2, 3, 1, 4, 5]

    def test_unknown_position_returns_none(self):
        assert sortedSummonersByGameRole(
            [{'summonerId': 1, 'selectedPosition': 'INVALID'}]
        ) is None


class TestParseGames:
    @pytest.fixture
    def games(self):
        return [
            {'queueId': 420, 'remake': False, 'kills': 10, 'deaths': 2, 'assists': 5, 'win': True},
            {'queueId': 420, 'remake': False, 'kills': 5, 'deaths': 5, 'assists': 3, 'win': False},
            {'queueId': 440, 'remake': False, 'kills': 8, 'deaths': 3, 'assists': 7, 'win': True},
            {'queueId': 420, 'remake': True, 'kills': 0, 'deaths': 0, 'assists': 0, 'win': False},
        ]

    def test_all_games(self, games):
        hit, kills, deaths, assists, wins, losses = parseGames(games)
        assert len(hit) == 4
        assert (kills, deaths, assists) == (23, 10, 15)
        assert (wins, losses) == (2, 1)

    def test_filter_by_queue(self, games):
        hit, kills, deaths, assists, wins, losses = parseGames(games, targetId=440)
        assert len(hit) == 1
        assert (kills, deaths, assists) == (8, 3, 7)

    def test_empty(self):
        hit, kills, deaths, assists, wins, losses = parseGames([])
        assert hit == []
        assert (kills, deaths, assists, wins, losses) == (0, 0, 0, 0, 0)


class TestParseRankInfo:
    def test_no_info(self):
        result = parseRankInfo(None)
        assert result['solo']['tier'] is not None
        assert result['flex']['tier'] is not None

    def test_ranked(self):
        info = {
            'queueMap': {
                'RANKED_SOLO_5x5': {'tier': 'Gold', 'division': 'II', 'leaguePoints': 53},
                'RANKED_FLEX_SR': {'tier': 'Silver', 'division': 'I', 'leaguePoints': 27},
            }
        }
        result = parseRankInfo(info)
        assert result['solo']['tier'] == '黄金'
        assert result['solo']['division'] == 'II'
        assert result['solo']['lp'] == 53
        assert result['flex']['tier'] == '白银'

    def test_unranked(self):
        info = {
            'queueMap': {
                'RANKED_SOLO_5x5': {'tier': '', 'division': 'NA', 'leaguePoints': ''},
                'RANKED_FLEX_SR': {'tier': '', 'division': 'NA', 'leaguePoints': ''},
            }
        }
        result = parseRankInfo(info)
        assert 'UNRANKED' in result['solo']['icon']
        assert 'UNRANKED' in result['flex']['icon']


class TestParseDetailRankInfo:
    @pytest.fixture
    def rank_info(self):
        return {
            'queueMap': {
                'RANKED_SOLO_5x5': {
                    'tier': 'Diamond', 'division': 'III',
                    'highestTier': 'Master', 'highestDivision': 'I',
                    'previousSeasonEndTier': 'Platinum',
                    'previousSeasonEndDivision': 'I',
                    'wins': 120, 'losses': 100, 'leaguePoints': 45,
                },
                'RANKED_FLEX_SR': {
                    'tier': 'Gold', 'division': 'IV',
                    'highestTier': 'Platinum', 'highestDivision': 'II',
                    'previousSeasonEndTier': 'Silver',
                    'previousSeasonEndDivision': 'I',
                    'wins': 80, 'losses': 70, 'leaguePoints': 30,
                },
            }
        }

    def test_solo_fields(self, rank_info):
        solo = parseDetailRankInfo(rank_info)[0]
        assert solo[0] is not None
        assert isinstance(solo[0], str)
        assert solo[1] == '220'
        assert solo[2] == '54 %'
        assert solo[5] == '璀璨钻石 III'
        assert solo[6] == '45'

    def test_flex_fields(self, rank_info):
        flex = parseDetailRankInfo(rank_info)[1]
        assert flex[0] is not None
        assert isinstance(flex[0], str)
        assert flex[1] == '150'
        assert flex[2] == '53 %'
        assert flex[5] == '荣耀黄金 IV'
        assert flex[6] == '30'

    def test_unranked(self):
        info = {
            'queueMap': {
                'RANKED_SOLO_5x5': {
                    'tier': '', 'division': 'NA',
                    'highestTier': '', 'highestDivision': 'NA',
                    'previousSeasonEndTier': '', 'previousSeasonEndDivision': 'NA',
                    'wins': 0, 'losses': 0, 'leaguePoints': 0,
                },
                'RANKED_FLEX_SR': {
                    'tier': '', 'division': 'NA',
                    'highestTier': '', 'highestDivision': 'NA',
                    'previousSeasonEndTier': '', 'previousSeasonEndDivision': 'NA',
                    'wins': 0, 'losses': 0, 'leaguePoints': 0,
                },
            }
        }
        result = parseDetailRankInfo(info)
        assert '--' in result[0][2]
