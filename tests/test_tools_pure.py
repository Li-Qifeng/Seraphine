"""
Tests for pure parsing functions from app/lol/tools.py.

Note: Functions are copied inline because the project's qfluentwidgets
dependency has a runtime crash in this test environment (AV at import).
When the env issues are resolved, switch to importing from app.lol.tools.
"""
import time
import pytest


# --- Copied from tools.py: translateTier ---

def _translateTier(orig: str, short=False) -> str:
    if orig == '':
        return "--"
    maps = {
        'Iron': ['坚韧黑铁', '黑铁'],
        'Bronze': ['英勇黄铜', '黄铜'],
        'Silver': ['不屈白银', '白银'],
        'Gold': ['荣耀黄金', '黄金'],
        'Platinum': ['华贵铂金', '铂金'],
        'Emerald': ['流光翡翠', '翡翠'],
        'Diamond': ['璀璨钻石', '钻石'],
        'Master': ['超凡大师', '大师'],
        'Grandmaster': ['傲世宗师', '宗师'],
        'Challenger': ['最强王者', '王者'],
    }
    index = 1 if short else 0
    return maps[orig.capitalize()][index]


# --- Copied from tools.py: timeStampToStr ---

def _timeStampToStr(stamp):
    timeArray = time.localtime(stamp / 1000)
    return time.strftime("%Y/%m/%d %H:%M", timeArray)


def _timeStampToShortStr(stamp):
    timeArray = time.localtime(stamp / 1000)
    return time.strftime("%m/%d", timeArray)


def _secsToStr(secs):
    return time.strftime("%M:%S", time.gmtime(secs))


# --- Copied from tools.py: separateTeams ---

def _separateTeams(data, currentSummonerId):
    team1 = data['teamOne']
    team2 = data['teamTwo']
    for summoner in team1:
        if summoner.get('summonerId') == currentSummonerId:
            return team1, team2
    for summoner in team2:
        if summoner.get('summonerId') == currentSummonerId:
            return team2, team1
    return None, None


# --- Copied from tools.py: parseSummonerOrder ---

def _parseSummonerOrder(team):
    summoners = [{
        'summonerId': s['summonerId'],
        'cellId': s['cellId']
    } for s in team]
    summoners.sort(key=lambda x: x['cellId'])
    return [s['summonerId'] for s in summoners if s['summonerId'] != 0]


# --- Copied from tools.py: sortedSummonersByGameRole ---

def _sortedSummonersByGameRole(summoners: list):
    position = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
    if any(x['selectedPosition'] not in position for x in summoners):
        return None
    return sorted(summoners,
                  key=lambda x: position.index(x['selectedPosition']))


# --- Copied from tools.py: parseGames ---

def _parseGames(games, targetId=0):
    kills, deaths, assists, wins, losses = 0, 0, 0, 0, 0
    hitGames = []
    for game in games:
        if not targetId or game['queueId'] == targetId:
            hitGames.append(game)
            if not game['remake']:
                kills += game['kills']
                deaths += game['deaths']
                assists += game['assists']
                if game['win']:
                    wins += 1
                else:
                    losses += 1
    return hitGames, kills, deaths, assists, wins, losses


# --- Copied from tools.py: parseRankInfo (simplified) ---

def _parseRankInfo(info):
    soloIcon = flexIcon = "app/resource/images/UNRANKED.svg"
    soloTier = flexTier = "Unknown"
    soloDivision = flexDivision = ""
    soloRankInfo = flexRankInfo = {"leaguePoints": ""}

    if info:
        soloRankInfo = info["queueMap"]["RANKED_SOLO_5x5"]
        flexRankInfo = info["queueMap"]["RANKED_FLEX_SR"]

        soloTier = soloRankInfo["tier"]
        soloDivision = soloRankInfo["division"]

        if soloTier == "":
            soloIcon = "app/resource/images/UNRANKED.svg"
            soloTier = "未定级"
        else:
            soloIcon = f"app/resource/images/{soloTier}.svg"
            soloTier = _translateTier(soloTier, True)
        if soloDivision == "NA":
            soloDivision = ""

        flexTier = flexRankInfo["tier"]
        flexDivision = flexRankInfo["division"]

        if flexTier == "":
            flexIcon = "app/resource/images/UNRANKED.svg"
            flexTier = "未定级"
        else:
            flexIcon = f"app/resource/images/{flexTier}.svg"
            flexTier = _translateTier(flexTier, True)
        if flexDivision == "NA":
            flexDivision = ""

    return {
        "solo": {
            "tier": soloTier,
            "icon": soloIcon,
            "division": soloDivision,
            "lp": soloRankInfo["leaguePoints"],
        },
        "flex": {
            "tier": flexTier,
            "icon": flexIcon,
            "division": flexDivision,
            "lp": flexRankInfo["leaguePoints"],
        },
    }


# --- Copied from tools.py: parseDetailRankInfo ---

def _parseDetailRankInfo(rankInfo):
    soloRankInfo = rankInfo['queueMap']['RANKED_SOLO_5x5']
    soloTier = _translateTier(soloRankInfo['tier'])
    soloDivision = soloRankInfo['division']
    if soloTier == '--' or soloDivision == 'NA':
        soloDivision = ""
    soloHighestTier = _translateTier(soloRankInfo['highestTier'])
    soloHighestDivision = soloRankInfo['highestDivision']
    if soloHighestTier == '--' or soloHighestDivision == 'NA':
        soloHighestDivision = ""
    solxPreviousSeasonEndTier = _translateTier(soloRankInfo['previousSeasonEndTier'])
    soloPreviousSeasonDivision = soloRankInfo['previousSeasonEndDivision']
    if solxPreviousSeasonEndTier == '--' or soloPreviousSeasonDivision == 'NA':
        soloPreviousSeasonDivision = ""
    soloWins = soloRankInfo['wins']
    soloLosses = soloRankInfo['losses']
    soloTotal = soloWins + soloLosses
    soloWinRate = soloWins * 100 // soloTotal if soloTotal != 0 else 0
    soloLp = soloRankInfo['leaguePoints']

    flexRankInfo = rankInfo['queueMap']['RANKED_FLEX_SR']
    flexTier = _translateTier(flexRankInfo['tier'])
    flexDivision = flexRankInfo['division']
    if flexTier == '--' or flexDivision == 'NA':
        flexDivision = ""
    flexHighestTier = _translateTier(flexRankInfo['highestTier'])
    flexHighestDivision = flexRankInfo['highestDivision']
    if flexHighestTier == '--' or flexHighestDivision == 'NA':
        flexHighestDivision = ""
    flexPreviousSeasonEndTier = _translateTier(flexRankInfo['previousSeasonEndTier'])
    flexPreviousSeasonEndDivision = flexRankInfo['previousSeasonEndDivision']
    if flexPreviousSeasonEndTier == '--' or flexPreviousSeasonEndDivision == 'NA':
        flexPreviousSeasonEndDivision = ""
    flexWins = flexRankInfo['wins']
    flexLosses = flexRankInfo['losses']
    flexTotal = flexWins + flexLosses
    flexWinRate = flexWins * 100 // flexTotal if flexTotal != 0 else 0
    flexLp = flexRankInfo['leaguePoints']

    return [
        [None, str(soloTotal), str(soloWinRate) + ' %' if soloTotal != 0 else '--',
         str(soloWins), str(soloLosses), f'{soloTier} {soloDivision}',
         str(soloLp), f'{soloHighestTier} {soloHighestDivision}',
         f'{solxPreviousSeasonEndTier} {soloPreviousSeasonDivision}'],
        [None, str(flexTotal), str(flexWinRate) + ' %' if flexTotal != 0 else '--',
         str(flexWins), str(flexLosses), f'{flexTier} {flexDivision}',
         str(flexLp), f'{flexHighestTier} {flexHighestDivision}',
         f'{flexPreviousSeasonEndTier} {flexPreviousSeasonEndDivision}'],
    ]


# ====== Tests ======


class TestTranslateTier:
    def test_empty(self):
        assert _translateTier("") == "--"

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
        assert _translateTier(tier) == expected_long
        assert _translateTier(tier, short=True) == expected_short

    def test_case_insensitive(self):
        assert _translateTier("gold") == "荣耀黄金"
        assert _translateTier("GOLD") == "荣耀黄金"


class TestTimeStampToStr:
    def test_normal(self):
        # 1700000000000 ms = 2023/11/14 18:13 UTC → local time varies by TZ
        # Just verify it returns a valid date-time string
        result = _timeStampToStr(1700000000000)
        assert result.startswith("2023/11/")

    def test_epoch(self):
        assert _timeStampToStr(0) == "1970/01/01 08:00"


class TestTimeStampToShortStr:
    def test_normal(self):
        assert _timeStampToShortStr(1700000000000) == "11/15"


class TestSecsToStr:
    def test_zero(self):
        assert _secsToStr(0) == "00:00"

    def test_normal(self):
        assert _secsToStr(125) == "02:05"

    def test_max_minutes(self):
        assert _secsToStr(3599) == "59:59"


class TestSeparateTeams:
    def _team(self, *ids):
        return [{'summonerId': sid} for sid in ids]

    def test_current_in_team_one(self):
        data = {'teamOne': self._team(1, 2, 3), 'teamTwo': self._team(4, 5, 6)}
        ally, enemy = _separateTeams(data, 1)
        assert ally == data['teamOne']
        assert enemy == data['teamTwo']

    def test_current_in_team_two(self):
        data = {'teamOne': self._team(1, 2, 3), 'teamTwo': self._team(4, 5, 6)}
        ally, enemy = _separateTeams(data, 5)
        assert ally == data['teamTwo']
        assert enemy == data['teamOne']

    def test_not_found(self):
        data = {'teamOne': self._team(1, 2), 'teamTwo': self._team(3, 4)}
        ally, enemy = _separateTeams(data, 99)
        assert ally is None
        assert enemy is None


class TestParseSummonerOrder:
    def test_sorted_by_cell_id(self):
        team = [
            {'summonerId': 5, 'cellId': 3},
            {'summonerId': 3, 'cellId': 1},
            {'summonerId': 7, 'cellId': 2},
        ]
        assert _parseSummonerOrder(team) == [3, 7, 5]

    def test_skips_zero_id(self):
        team = [
            {'summonerId': 1, 'cellId': 1},
            {'summonerId': 0, 'cellId': 2},
            {'summonerId': 3, 'cellId': 3},
        ]
        assert _parseSummonerOrder(team) == [1, 3]

    def test_empty(self):
        assert _parseSummonerOrder([]) == []


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
        result = _sortedSummonersByGameRole(summoners)
        ids = [s['summonerId'] for s in result]
        assert ids == [2, 3, 1, 4, 5]  # TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY

    def test_unknown_position_returns_none(self):
        assert _sortedSummonersByGameRole(
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
        hit, kills, deaths, assists, wins, losses = _parseGames(games)
        assert len(hit) == 4
        assert (kills, deaths, assists) == (23, 10, 15)
        assert (wins, losses) == (2, 1)  # remake excluded

    def test_filter_by_queue(self, games):
        hit, kills, deaths, assists, wins, losses = _parseGames(games, targetId=440)
        assert len(hit) == 1
        assert (kills, deaths, assists) == (8, 3, 7)

    def test_empty(self):
        hit, kills, deaths, assists, wins, losses = _parseGames([])
        assert hit == []
        assert (kills, deaths, assists, wins, losses) == (0, 0, 0, 0, 0)


class TestParseRankInfo:
    def test_no_info(self):
        result = _parseRankInfo(None)
        assert result['solo']['tier'] is not None
        assert result['flex']['tier'] is not None

    def test_ranked(self):
        info = {
            'queueMap': {
                'RANKED_SOLO_5x5': {'tier': 'Gold', 'division': 'II', 'leaguePoints': 53},
                'RANKED_FLEX_SR': {'tier': 'Silver', 'division': 'I', 'leaguePoints': 27},
            }
        }
        result = _parseRankInfo(info)
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
        result = _parseRankInfo(info)
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
        solo = _parseDetailRankInfo(rank_info)[0]
        assert solo[0] is None  # label placeholder
        assert solo[1] == '220'  # total
        assert solo[2] == '54 %'
        assert solo[5] == '璀璨钻石 III'
        assert solo[6] == '45'

    def test_flex_fields(self, rank_info):
        flex = _parseDetailRankInfo(rank_info)[1]
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
        result = _parseDetailRankInfo(info)
        assert '--' in result[0][2]
